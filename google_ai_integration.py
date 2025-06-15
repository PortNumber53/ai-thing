import os
import json
import configparser
import traceback
from pathlib import Path
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

    def __init__(self, model_name: str = "gemini-1.5-pro-latest"):
        """
        Initialize the Google AI integration.

        Args:
            model_name: The name of the model to use (default: gemini-1.5-pro-latest)
        """
        self.model_name = model_name
        self._configure_gemini()
        self.tools: Dict[str, Any] = {}
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
                        if 'base_path' in init_params: # For FileTool
                             # You might want to make base_path configurable or derive it
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
                        break # Assuming one tool class per file
            except Exception as e:
                print(f"[ERROR] Failed to load tool from {tool_file.name}: {e}")
                traceback.print_exc()

    def _get_secrets_path(self) -> Path:
        """Get the path to the secrets.ini file."""
        return Path.home() / ".config" / "secrets.ini"

    def _read_api_key(self) -> tuple[str, str]:
        """
        Read the Google API key and model name from the secrets.ini file.

        Returns:
            tuple: (api_key, model_name)
        """
        secrets_path = self._get_secrets_path()
        if not secrets_path.exists():
            raise FileNotFoundError(
                f"Secrets file not found at {secrets_path}. "
                "Please create it with your Google API key in the [google] section as 'api_key'."
            )

        config = configparser.ConfigParser()
        config.read(secrets_path)

        if 'google' not in config:
            raise KeyError(
                "[google] section not found in secrets.ini. "
                "Please add your Google API key in the [google] section as 'api_key'."
            )

        api_key = config['google'].get('api_key')
        if not api_key:
            raise ValueError(
                "'api_key' not found in the [google] section of secrets.ini. "
                "Please add your Google API key."
            )

        # Get model name with fallback to the instance's default
        model_name = config['google'].get('model', self.model_name)

        return api_key, model_name

    def _configure_gemini(self) -> None:
        """
        Configure the Gemini API with the API key and model from ~/.config/secrets.ini.

        The secrets.ini file should have the following format:
        [google]
        api_key = your_google_api_key_here
        model = gemini-1.5-pro-latest  # optional
        """
        try:
            api_key, model_name = self._read_api_key()
            self.model_name = model_name  # Update model name if specified in config
            genai.configure(api_key=api_key)
        except Exception as e:
            raise RuntimeError(
                f"Failed to configure Gemini API: {str(e)}\n"
                "Please ensure you have a valid Google API key in ~/.config/secrets.ini\n"
                "with the following format:\n\n"
                "[google]\n"
                "api_key = your_google_api_key_here\n"
                "model = gemini-1.5-pro-latest  # optional"
            ) from e

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
    """Example usage of the GoogleAIIntegration class."""
    try:
        # Initialize the integration
        ai = GoogleAIIntegration()

        # Example queries
        queries = [
            # "What's the weather like in Tokyo today?",
            # "How about San Francisco, in fahrenheit?",
            # "Show me the contents of the file '/home/grimlock/tmp/snake_game.html'",
            # "Write a joke about computers to this file '/home/grimlock/tmp/computer_joke.txt'",
            "What are the temperatures in the locations listed in the '/home/grimlock/tmp/locations.txt', write the response to '/home/grimlock/tmp/temps.txt'",
            # "Please make the snake of the game be made of circles instead of squares, the file is '/home/grimlock/tmp/snake_game.html'"
            # "Tell me a joke about computers."
        ]

        for query in queries:
            print("\n" + "="*50)
            print(f"[Query] {query}")
            response = ai.chat(query, max_tool_calls=10)
            print(f"[Response] {response}")

    except Exception as e:
        print(f"An error occurred: {str(e)}")


if __name__ == "__main__":
    main()
