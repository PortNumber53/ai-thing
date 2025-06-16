import os
import json
import configparser
import argparse
import traceback
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from typing import Dict, Any, Optional, List, Union, Literal, TypedDict
from google.protobuf.struct_pb2 import Value, Struct # For manual tool call mocking
import importlib
import inspect

# Type definitions for function calling
class FunctionCall(TypedDict):
    name: str
    args: Dict[str, Any]

# Tool definition type
class Tool(TypedDict):
    function_declarations: List[Dict[str, Any]]

# Part type for chat messages
class Part(TypedDict, total=False):
    text: str
    function_response: Dict[str, Any]  # For function responses
    function_call: Dict[str, Any]  # For function calls from the model

class GoogleAIIntegration:
    """
    A class to handle Google AI Studio and Vertex AI integrations.
    Supports function calling with Gemini models.
    """
    # Define safety settings as a class-level constant
    SAFETY_SETTINGS_CONFIG = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    def __init__(self, model_name: str = "gemini-1.5-flash-preview-0514", profile_name: Optional[str] = None):
        """
        Initialize the Google AI integration.

        Args:
            model_name: The name of the model to use.
            profile_name: The name of the profile to use from secrets.ini.
        """
        self.model_name = model_name
        self.profile_name = profile_name
        self.tools: Dict[str, Any] = {}
        self.tool_definitions: List[Any] = []
        self.chroot_dir: Optional[Path] = None
        self.mcp_config_file_path: Optional[Path] = None
        self.mcp_server_configs: Dict[str, Dict[str, Any]] = {}
        self.active_profile_name: Optional[str] = None
        self.google_ai_api_key: Optional[str] = None
        
        self._configure_gemini()
        self._load_mcp_configurations()
        self._load_tools()
        self.chat_session: Optional[genai.ChatSession] = None

    def _load_tools(self):
        """Dynamically load tools from the 'tools' subdirectory."""
        tools_dir = Path(__file__).parent / "tools"
        if not tools_dir.is_dir():
            print(f"[WARNING] Tools directory not found: {tools_dir}")
            return

        for tool_file in tools_dir.glob("[!_]*.py"): # Ignore files starting with _
            module_name = f"tools.{tool_file.stem}"
            try:
                module = importlib.import_module(module_name)
                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and obj.__module__ == module_name and hasattr(obj, 'get_definition') and hasattr(obj, 'execute'):
                        # Instantiate the tool
                        # Pass user_agent if the tool's __init__ accepts it
                        tool_instance_args = {}
                        init_params = inspect.signature(obj.__init__).parameters
                        if 'user_agent' in init_params:
                            tool_instance_args['user_agent'] = f"google_ai_integration/{self.model_name}"

                        # Pass chroot_dir to file operation tools
                        if name in ['FileReadTool', 'FileFullWriteTool']:
                            if 'chroot_dir' in init_params:
                                if self.chroot_dir: # self.chroot_dir is now a Path object or None, set by _configure_gemini
                                    tool_instance_args['chroot_dir'] = self.chroot_dir
                                else:
                                    # This should not happen if _configure_gemini ran successfully, as chroot is mandatory.
                                    print(f"[CRITICAL_ERROR] Chroot directory not configured for {name} but it's required. Skipping tool loading.")
                                    continue # Skip loading this tool
                            else:
                                print(f"[WARNING] File tool {name} does not accept 'chroot_dir' in __init__. Update tool to support chroot.")
                        elif 'base_path' in init_params: # Fallback for other tools that might still use base_path
                            print(f"[INFO] Tool {name} uses 'base_path', setting to CWD. Consider updating to 'chroot_dir' if it performs file ops.")
                            tool_instance_args['base_path'] = str(Path.cwd())

                        tool_instance = obj(**tool_instance_args)

                        # Get the tool's function name from its definition
                        tool_def = tool_instance.get_definition()
                        if tool_def and tool_def.get('function_declarations'):
                            func_name = tool_def['function_declarations'][0].get('name')
                            if func_name:
                                self.tools[func_name] = tool_instance
                                print(f"[INFO] Loaded tool: {func_name} from {module_name}")
                            else:
                                print(f"[WARNING] Tool {name} in {module_name} has no function name in definition.")
                        else:
                            print(f"[WARNING] Tool {name} in {module_name} has no definition.")
                        # Removed 'break' to allow multiple tool classes per file if needed in future, though current convention is one.
            except Exception as e: # This except is now correctly associated with the try for importlib.import_module
                print(f"[ERROR] Failed to load tool from {tool_file.name}: {e}")
                traceback.print_exc()

    def _get_secrets_path(self) -> Path:
        """Get the path to the secrets.ini file."""
        return Path.home() / ".config" / "ai-thing" / "secrets.ini"

    def _load_profile_config(self, profile_name: Optional[str] = None) -> Tuple[str, str, str, str, Optional[str]]:
        """
        Load configuration from secrets.ini based on profiles.
        """
        secrets_path = self._get_secrets_path()
        if not secrets_path.exists():
            raise FileNotFoundError(f"secrets.ini not found at {secrets_path}")

        config = configparser.ConfigParser()
        config.read(secrets_path)

        if 'default' not in config:
            raise KeyError("[default] section not found in secrets.ini.")

        # Determine the logical profile name
        logical_profile_name = profile_name or config.get('default', 'profile', fallback='default')

        # Determine the actual section name in the INI file, which may have a 'profile:' prefix
        section_name = f"profile:{logical_profile_name}" if logical_profile_name != 'default' else 'default'

        # If the determined profile section doesn't exist, fall back to 'default' and print a warning.
        if section_name not in config:
            print(f"[WARNING] Profile section '[{section_name}]' not found in {secrets_path}. Falling back to '[default]' profile.", file=sys.stderr)
            section_name = 'default'
            logical_profile_name = 'default'

        # This check should now always pass, assuming a [default] section exists.
        if section_name not in config:
             raise KeyError(f"Critical error: Default profile '[default]' not found in {secrets_path} after fallback.")

        def get_value(key: str) -> Optional[str]:
            # Get value from active profile section, fall back to default profile section
            return config.get(section_name, key, fallback=config.get('default', key, fallback=None))

        api_key = get_value('google_ai_api_key')
        if not api_key:
            raise ValueError(f"Mandatory key 'google_ai_api_key' not found in profile '{logical_profile_name}' or '[default]'.")

        chroot_dir = get_value('chroot')
        if not chroot_dir:
            raise ValueError(f"Mandatory key 'chroot' not found in profile '{logical_profile_name}' or '[default]'.")

        model_name = get_value('google_ai_model') or self.model_name
        mcp_config_file_str = get_value('mcp_config_file')

        return logical_profile_name, api_key, model_name, chroot_dir, mcp_config_file_str

    def _load_mcp_configurations(self):
        """Load MCP server configurations from the JSON file specified in secrets.ini."""
        if not self.mcp_config_file_path:
            print("[INFO] MCP support disabled: No MCP configuration file path set.")
            return

        if not self.mcp_config_file_path.is_file():
            print(f"[WARNING] MCP configuration file not found: {self.mcp_config_file_path}. MCP support will be limited.")
            return

        try:
            with open(self.mcp_config_file_path, 'r') as f:
                data = json.load(f)

            if 'mcpServers' not in data or not isinstance(data['mcpServers'], dict):
                print(f"[WARNING] Invalid MCP configuration format in {self.mcp_config_file_path}. Missing 'mcpServers' dictionary. MCP support may not work correctly.")
                self.mcp_server_configs = {}
            else:
                self.mcp_server_configs = data['mcpServers']
                print(f"[INFO] Successfully loaded {len(self.mcp_server_configs)} MCP server configurations from {self.mcp_config_file_path}.")
                for server_name in self.mcp_server_configs.keys():
                    print(f"  - Found MCP server: {server_name}")

        except json.JSONDecodeError:
            print(f"[WARNING] Invalid JSON in MCP configuration file: {self.mcp_config_file_path}. MCP support may not work correctly.")
            self.mcp_server_configs = {}
        except Exception as e:
            print(f"[WARNING] Error loading MCP configuration file {self.mcp_config_file_path}: {e}. MCP support may not work correctly.")
            self.mcp_server_configs = {}

    def display_info(self):
        """Displays the current configuration, redacting sensitive information."""
        print("AI Configuration Info:")
        print("======================")
        print(f"Active Profile: {self.active_profile_name}")
        if self.google_ai_api_key:
            redacted_key = self.google_ai_api_key[:4] + "****" + self.google_ai_api_key[-4:]
        else:
            redacted_key = "Not Set"
        print(f"Google API Key: {redacted_key}")
        print(f"Model: {self.model_name}")
        print(f"Chroot Directory: {self.chroot_dir}")
        print(f"MCP Config File: {self.mcp_config_file_path}")
        if self.mcp_server_configs:
            print("Loaded MCP Servers:")
            for server_name in self.mcp_server_configs.keys():
                print(f"  - {server_name}")
        else:
            print("No MCP Servers loaded.")
        print("======================")

    def _configure_gemini(self):
        """
        Configure the Gemini API using settings from the active profile.
        """
        try:
            (
                self.active_profile_name,
                self.google_ai_api_key,
                self.model_name,
                chroot_dir_str,
                mcp_config_file_str
            ) = self._load_profile_config(profile_name=self.profile_name)

            if chroot_dir_str:
                self.chroot_dir = Path(chroot_dir_str).resolve()
                if not self.chroot_dir.exists() or not self.chroot_dir.is_dir():
                    raise FileNotFoundError(f"Chroot directory '{self.chroot_dir}' does not exist or is not a directory.")
            else:
                raise ValueError("Chroot directory not configured.")

            if mcp_config_file_str:
                self.mcp_config_file_path = Path(mcp_config_file_str).expanduser().resolve()
            else:
                self.mcp_config_file_path = None

            genai.configure(api_key=self.google_ai_api_key)
            mcp_info = f", MCP Config: {self.mcp_config_file_path}" if self.mcp_config_file_path else ", MCP Config: Not set"
            print(f"[INFO] Configured with profile. Model: {self.model_name}, Chroot: {self.chroot_dir}{mcp_info}")
        except Exception as e:
            error_message = (
                f"Failed to configure Gemini API with profile system: {str(e)}\n"
                f"Please ensure your ~/.config/ai-thing/secrets.ini is formatted correctly with profiles.\n"
                "Mandatory keys 'google_ai_api_key' and 'chroot' must be present in the active profile or [default]."
            )
            print(f"[ERROR] {error_message}", file=sys.stderr)
            raise RuntimeError(error_message) from e

    def _get_safety_settings(self) -> list[dict]:
        """Returns the safety settings for the model."""
        return self.SAFETY_SETTINGS_CONFIG

    def _get_system_instruction(self) -> str:
        """
        Get the system instruction for the model, dynamically including tool information.

        Returns:
            str: The system instruction
        """
        base_instruction = (
            "You are a helpful AI assistant. "
            "When a user asks for an action that can be performed by a tool, "
            "you MUST respond with a tool call in the specified JSON format. "
            "Do not add any explanatory text before or after the tool call itself. "
            "If a query requires multiple steps or information from multiple tools, "
            "you can make a sequence of tool calls. After each tool call, I will provide you with the result, "
            "and you can then decide if another tool call is needed or if you can now answer the user's query. "
            "If you are unsure or the action cannot be performed by a tool, respond naturally."
        )

        tool_descriptions = []
        tool_invocation_instructions = []

        if not self.tools:
            tool_descriptions.append("No tools are currently available.")
        else:
            tool_descriptions.append("Available tools:")
            for tool_name, tool_instance in self.tools.items():
                summary = getattr(tool_instance, 'get_summary', lambda: 'No summary available.')()
                tool_descriptions.append(f"- {tool_name}: {summary}")

                invocation_instr = getattr(tool_instance, 'get_invocation_instructions', lambda: None)()
                if invocation_instr:
                    tool_invocation_instructions.append(f"Instructions for {tool_name}:\n{invocation_instr}")

            tool_descriptions.append("\nTo get detailed help for a specific tool, you can say: /help <tool_name> (This will be handled by the application, not the AI model directly). Example: /help get_weather")

        system_instruction_parts = [base_instruction]
        system_instruction_parts.extend(tool_descriptions)
        system_instruction_parts.append("\nTool Invocation Details:")
        system_instruction_parts.extend(tool_invocation_instructions)

        system_instruction = "\n\n".join(filter(None, system_instruction_parts))

        # print(f"[DEBUG] System Instruction:\n{system_instruction}") # For debugging
        return system_instruction

    def _extract_tool_call(self, text: str) -> Optional[dict]:
        """
        Extract tool call from text in the format: /tool name({"key": "value"})

        Args:
            text: The text to parse

        Returns:
            dict: Parsed tool call with 'name' and 'args' or None if no match
        """
        import re
        import json

        # Look for /tool name({...}) pattern
        match = re.match(r'/tool\s+(\w+)\(({.*})\)', text.strip())
        if not match:
            return None

        try:
            name = match.group(1)
            args_json = match.group(2)
            args = json.loads(args_json)
            return {'name': name, 'args': args}
        except (json.JSONDecodeError, IndexError) as e:
            print(f"[ERROR] Failed to parse tool call: {str(e)}")
            return None

    def initialize_model(self):
        """Initialize the Gemini model with tools and safety settings."""
        self._configure_gemini()

        tool_definitions = [tool.get_definition() for tool in self.tools.values() if hasattr(tool, 'get_definition')]

        model = genai.GenerativeModel(
            model_name=self.model_name,
            tools=tool_definitions if tool_definitions else None, # Pass None if no tools
            safety_settings=self._get_safety_settings(),
            system_instruction=self._get_system_instruction()
        )

        return model
        # Create model with system instruction and tools
        tool_definitions = [tool.get_definition() for tool in self.tools.values() if hasattr(tool, 'get_definition')]

        model = genai.GenerativeModel(
            model_name=self.model_name,
            tools=tool_definitions if tool_definitions else None, # Pass None if no tools
            safety_settings=self._get_safety_settings(),
            system_instruction=self._get_system_instruction()
        )

        return model

    def _extract_args_from_proto(self, args_proto) -> dict:
        """
        Extract arguments from Protocol Buffers Message format.

        Args:
            args_proto: The Protocol Buffers Message containing the arguments

        Returns:
            dict: The extracted arguments as a dictionary
        """
        extracted_args = {}

        try:
            print(f"[DEBUG] Extracting args from type: {type(args_proto)}")
            # Handle MapComposite type directly
            if hasattr(args_proto, 'items') and callable(args_proto.items): # For MapComposite from Gemini
                print("[DEBUG] Processing MapComposite")
                for key, value in args_proto.items():
                    # Values from MapComposite.items() are already Python native types.
                    print(f"[DEBUG] Processing key: {key}, value: {value} (type: {type(value)})")
                    extracted_args[key] = value
            # Handle direct fields access
            elif hasattr(args_proto, 'fields'):
                print("[DEBUG] Processing direct fields")
                for key, value in args_proto.fields.items(): # type: ignore
                    print(f"[DEBUG] Processing field: {key} = {value}")
                    if hasattr(value, 'string_value'):
                        extracted_args[key] = value.string_value
                        print(f"[DEBUG] Extracted string: {key} = {value.string_value}")
                    elif hasattr(value, 'number_value'):
                        extracted_args[key] = value.number_value
                        print(f"[DEBUG] Extracted number: {key} = {value.number_value}")
                    elif hasattr(value, 'bool_value'):
                        extracted_args[key] = value.bool_value
                        print(f"[DEBUG] Extracted bool: {key} = {value.bool_value}")
                    else:
                        print(f"[DEBUG] Unhandled field value type for {key}: {type(value)}")
            else:
                print(f"[DEBUG_WARN] args_proto is not a recognized type for extraction: {type(args_proto)}")

            print(f"[DEBUG] Extracted args: {extracted_args}")

        except Exception as e:
            print(f"[ERROR] Error extracting arguments: {e}")
            traceback.print_exc()
            # Depending on desired behavior, you might want to return empty dict or re-raise
        return extracted_args

    def _extract_value_from_proto(self, value_proto):
        """Extract a single value from a protobuf Value."""
        # Try direct attribute access first
        if hasattr(value_proto, 'string_value'):
            return value_proto.string_value
        elif hasattr(value_proto, 'number_value'):
            return value_proto.number_value
        elif hasattr(value_proto, 'bool_value'):
            return value_proto.bool_value
        elif hasattr(value_proto, 'struct_value'):
            return self._extract_args_from_proto(value_proto.struct_value)
        elif hasattr(value_proto, 'list_value'):
            return [self._extract_value_from_proto(item) for item in value_proto.list_value.values]

        # Try to use ListFields if direct access doesn't work
        if hasattr(value_proto, 'ListFields'):
            for field_descriptor, value in value_proto.ListFields():
                field_name = field_descriptor.name
                if field_name in ['string_value', 'number_value', 'bool_value']:
                    return value
                elif field_name == 'struct_value':
                    return self._extract_args_from_proto(value)
                elif field_name == 'list_value':
                    return [self._extract_value_from_proto(item) for item in value.values]

        return None

    def _send_function_error(self, chat: Any, function_name: str, error_msg: str) -> Any:
        """Send an error message back to the model."""
        print(f"[ERROR] Sending function error: {function_name} - {error_msg}")
        try:
            # Send a structured error message back to the model using dictionary format
            return chat.send_message([{
                'function_response': {
                    'name': function_name or 'unknown_tool_error',
                    'response': {'error': error_msg}
                }
            }])
        except Exception as e:
            print(f"[ERROR] Failed to send error message: {str(e)}")
            # Fallback to a simple text response if the function call fails
            return chat.send_message(f"Error in {function_name or 'unknown'}: {error_msg}")

    def chat(self, prompt: str, max_tool_calls: int = 5) -> str:
        """
        Process a user's message and return the model's response, supporting multi-turn tool calls.

        Args:
            prompt: The user's message.
            max_tool_calls: Maximum number of consecutive tool calls allowed.

        Returns:
            The model's final response.
        """
        print(f"\n[User] {prompt}")

        # Handle /help command locally
        if prompt.strip().lower().startswith("/help"):
            parts = prompt.strip().split()
            if len(parts) == 2:
                help_tool_name = parts[1]
                tool_instance = None
                # Iterate to find tool by its defined function name
                for t_inst in self.tools.values():
                    if hasattr(t_inst, 'get_definition'):
                        tool_def = t_inst.get_definition()
                        if tool_def and tool_def.get('function_declarations'):
                            func_name = tool_def['function_declarations'][0].get('name')
                            if func_name == help_tool_name:
                                tool_instance = t_inst
                                break
                if tool_instance and hasattr(tool_instance, 'get_help'):
                    return f"[Help for {help_tool_name}]\n{tool_instance.get_help()}"
                else:
                    available_tools_str = ', '.join(
                        t.get_definition()['function_declarations'][0]['name']
                        for t in self.tools.values() if hasattr(t, 'get_definition') and
                        t.get_definition().get('function_declarations') and
                        t.get_definition()['function_declarations'][0].get('name')
                    )
                    return f"Sorry, I couldn't find help for '{help_tool_name}'. Available tools are: {available_tools_str if available_tools_str else 'None'}."
            else:
                return "Usage: /help <tool_name>\nExample: /help get_weather"

        try:
            if self.chat_session is None:
                model = self.initialize_model()
                # Start chat with an empty history, system instruction is part of the model
                self.chat_session = model.start_chat(history=[])

            chat_session = self.chat_session
            current_prompt_or_tool_response: Union[str, List[Part]] = prompt
            tool_call_count = 0

            while tool_call_count < max_tool_calls:
                print(f"[DEBUG] Sending to model (Loop {tool_call_count + 1}): {current_prompt_or_tool_response}")

                # Ensure current_prompt_or_tool_response is in the correct format for send_message
                # If it's a string, it's a user prompt. If it's a list of Parts (for tool response), it's already formatted.
                message_content = current_prompt_or_tool_response
                if isinstance(current_prompt_or_tool_response, str):
                    # For a direct string prompt, ensure it's correctly passed.
                    # The history is managed by the chat_session object itself.
                    pass # String is fine as is for the first turn or if model responds with text

                response = chat_session.send_message(
                    message_content,
                    generation_config={'temperature': 0.2}
                )

                function_call_to_process = None
                # Check for structured function call from the model
                if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                    for part_content in response.candidates[0].content.parts:
                        if hasattr(part_content, 'function_call') and part_content.function_call:
                            function_call_to_process = part_content.function_call
                            break # Process first function call found

                if function_call_to_process:
                    tool_call_count += 1
                    tool_name = function_call_to_process.name
                    tool_args = self._extract_args_from_proto(function_call_to_process.args)
                    print(f"\n[AI] Tool requested: {tool_name} with args: {tool_args}")

                    tool_instance = self.tools.get(tool_name)
                    tool_response_content_dict: Dict[str, Any] = {}

                    if tool_instance and hasattr(tool_instance, 'execute'):
                        try:
                            # Tool execute method should return a dictionary
                            tool_output = tool_instance.execute(**tool_args)
                            if not isinstance(tool_output, dict):
                                print(f"[WARN] Tool {tool_name} did not return a dict. Wrapping: {tool_output}")
                                tool_response_content_dict = {"result": str(tool_output)}
                            else:
                                tool_response_content_dict = tool_output
                            print(f"[DEBUG] Tool {tool_name} executed. Response: {tool_response_content_dict}")
                        except Exception as e:
                            error_msg = f"Error executing tool {tool_name}: {str(e)}"
                            print(f"\n[ERROR] {error_msg}")
                            traceback.print_exc()
                            tool_response_content_dict = {'error': error_msg}
                    else:
                        error_msg = f"Unknown or non-executable tool: {tool_name}"
                        print(f"\n[ERROR] {error_msg}")
                        tool_response_content_dict = {'error': error_msg}

                    # Prepare the tool response to send back to the model
                    # It must be a list of Part objects (TypedDicts)
                    current_prompt_or_tool_response = [
                        Part(function_response={'name': tool_name, 'response': tool_response_content_dict})
                    ]
                    # Continue loop to let model process tool response
                    continue
                else:
                    # No function call, extract direct text response
                    response_text = ""
                    if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                        response_text = "".join(p.text for p in response.candidates[0].content.parts if hasattr(p, 'text')).strip()

                    if not response_text: # Fallback
                        if hasattr(response, 'text') and response.text:
                            response_text = response.text
                        elif response.candidates and response.candidates[0].finish_reason == 'STOP' and not response.text:
                            response_text = "(Model generated no text content before stopping)"
                        else:
                            finish_reason_str = str(response.candidates[0].finish_reason) if (response.candidates and response.candidates[0].finish_reason) else 'N/A'
                            response_text = f"(No textual response. Finish reason: {finish_reason_str})"

                    print(f"\n[AI] {response_text}")
                    return response_text # End of conversation or final answer

            # Max tool calls reached. Send the last tool response to the model to get a final summary.
            if tool_call_count >= max_tool_calls:
                print(f"[WARN] Maximum tool call limit ({max_tool_calls}) reached. Sending last tool response for a final summary.")

                # Send the last tool's response to the model
                response = chat_session.send_message(
                    current_prompt_or_tool_response,
                    generation_config={'temperature': 0.2}
                )

                # Try to extract a final text response
                response_text = ""
                function_call_in_final_response = None

                if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, 'text') and part.text:
                            response_text += part.text
                        if hasattr(part, 'function_call') and part.function_call:
                            function_call_in_final_response = part.function_call

                response_text = response_text.strip()

                if response_text:
                    print(f"\n[AI] {response_text}")
                    return response_text
                elif function_call_in_final_response:
                    final_response = f"(Task ended after reaching tool call limit. The model wanted to perform one more action: call `{function_call_in_final_response.name}`.)"
                    print(f"\n[AI] {final_response}")
                    return final_response
                else:
                    final_response = "(Task completed, but model provided no final summary after reaching tool call limit.)"
                    print(f"\n[AI] {final_response}")
                    return final_response

        except Exception as e:
            error_msg = f"An error occurred in the chat method: {str(e)}"
            print(f"\n[ERROR] {error_msg}")
            print(f"\n[ERROR] Details: {traceback.format_exc()}")
            return f"I'm sorry, but I encountered a critical error: {str(e)}"

def main():
    """Main function to run the AI chat or CLI commands."""
    parser = argparse.ArgumentParser(
        description="A command-line interface for the Google AI integration.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Examples:
  - Start interactive chat: python google_ai_integration.py
  - Run a single query: python google_ai_integration.py "What is the weather in London?"
  - Show config info: python google_ai_integration.py info
"""
    )
    
    parser.add_argument(
        'args',
        nargs='*',
        help="A command ('info') or a query to send to the AI. If omitted, starts an interactive session."
    )
    
    parser.add_argument(
        '--profile', 
        type=str, 
        default=None, 
        help='Specify a configuration profile to use from secrets.ini.'
    )

    args = parser.parse_args()

    try:
        ai = GoogleAIIntegration(profile_name=args.profile)

        if args.args and args.args[0] == 'info':
            if len(args.args) > 1:
                print(f"[ERROR] The 'info' command does not take additional arguments. You provided: {' '.join(args.args[1:])}", file=sys.stderr)
                sys.exit(1)
            ai.display_info()
        elif args.args:
            query_text = " ".join(args.args)
            print(f"[User] {query_text}")
            response = ai.chat(query_text, max_tool_calls=10)
            print(f"[AI] {response}")
        else:
            # Interactive mode
            print("\n==================================================")
            print("Entering interactive chat mode. Press Ctrl+C to exit.")
            print("==================================================")
            try:
                while True:
                    query = input("[User] ")
                    if query.lower() in ['exit', 'quit']:
                        break
                    response = ai.chat(query, max_tool_calls=10)
                    print(f"[AI] {response}")
            except (KeyboardInterrupt, EOFError):
                print("\nExiting chat.")

    except (FileNotFoundError, KeyError, RuntimeError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
