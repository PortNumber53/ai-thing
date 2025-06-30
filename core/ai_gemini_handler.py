import asyncio
import datetime
import inspect
import json
import re
import traceback
from typing import Optional, Dict, Any, List, Union

import google.generativeai as genai
import time
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from .ai_type_definitions import Part
from .ai_config_manager import AIConfigManager
from .ai_tool_manager import AIToolManager

class GeminiChatHandler:
    SAFETY_SETTINGS_CONFIG = [
        {"category": HarmCategory.HARM_CATEGORY_HARASSMENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
        {"category": HarmCategory.HARM_CATEGORY_HATE_SPEECH, "threshold": HarmBlockThreshold.BLOCK_NONE},
        {"category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, "threshold": HarmBlockThreshold.BLOCK_NONE},
        {"category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
    ]

    def __init__(self, config_manager: AIConfigManager, tool_manager: AIToolManager):
        self.config_manager = config_manager
        self.tool_manager = tool_manager
        self.chat_session: Optional[genai.ChatSession] = None
        self.model: Optional[genai.GenerativeModel] = None
        self._initialize_model_and_session()

    def _log(self, level: str, message: str):
        """Prints a formatted log message with a timestamp."""
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        print(f"[{timestamp}] [{level.upper()}] {message}")

    def _initialize_model_and_session(self):
        """Initialize the Gemini model and chat session."""
        self._configure_genai()
        if not self.config_manager.google_ai_api_key:
            raise ValueError("Google AI API key not configured. Cannot initialize model.")
        tool_definitions = self.tool_manager.get_all_tool_definitions()


        self.model = genai.GenerativeModel(
            model_name=self.config_manager.model_name,
            tools=tool_definitions,
            safety_settings=self._get_safety_settings(),
            system_instruction=self._get_system_instruction()
        )
        self.chat_session = self.model.start_chat(history=[])
        self._log("INFO", f"Gemini model '{self.config_manager.model_name}' initialized and chat session started.")

    def _configure_genai(self):
        """Configures the Google AI API key."""
        if not self.config_manager.google_ai_api_key:
            raise ValueError("Google AI API key not configured.")
        genai.configure(api_key=self.config_manager.google_ai_api_key)

    def _get_safety_settings(self) -> List[Dict[str, Any]]:
        """Returns the safety settings for the model."""
        return self.SAFETY_SETTINGS_CONFIG

    def _get_system_instruction(self) -> str:
        """Get the system instruction for the model, dynamically including tool information."""
        base_instruction = (
            "You are a helpful AI assistant. "
            "When a user asks for an action that can be performed by a tool, "
            "you MUST respond with a tool call using the provided function declarations. "
            "Do not add any explanatory text before or after the tool call itself. "
            "If a query requires multiple steps or information from multiple tools, "
            "you can make a sequence of tool calls. After each tool call, I will provide you with the result, "
            "and you can then decide if another tool call is needed or if you can now answer the user's query. "
            "If you are unsure or the action cannot be performed by a tool, respond naturally."
        )

        tool_descriptions = []
        tool_invocation_instructions = []
        local_tools = self.tool_manager.get_all_tools()

        if not local_tools:
            tool_descriptions.append("No local tools are currently available.")
        else:
            tool_descriptions.append("Available local tools:")
            for tool_name, tool_instance in local_tools.items():
                summary = getattr(tool_instance, 'get_summary', lambda: 'No summary available.')()
                tool_descriptions.append(f"- {tool_name}: {summary}")
                invocation_instr = getattr(tool_instance, 'get_invocation_instructions', lambda: None)()
                if invocation_instr:
                    tool_invocation_instructions.append(f"Instructions for {tool_name}:\n{invocation_instr}")

        # MCP Tool descriptions (if any)
        if self.config_manager.mcp_server_tools_info:
            tool_descriptions.append("\nAvailable MCP server tools:")
            for server_name, mcp_tools in self.config_manager.mcp_server_tools_info.items():
                tool_descriptions.append(f"  Server '{server_name}':")
                if mcp_tools:
                    for mcp_tool_info in mcp_tools:
                        tool_descriptions.append(f"    - {mcp_tool_info['name']}: {mcp_tool_info['description']}")
                else:
                    tool_descriptions.append("    (No tools listed for this server)")

        tool_descriptions.append("\nTo get detailed help for a specific local tool, you can say: /help <tool_name> (This will be handled by the application). Example: /help get_weather")

        system_instruction_parts = [base_instruction]
        system_instruction_parts.extend(tool_descriptions)
        if tool_invocation_instructions:
             system_instruction_parts.append("\nTool Invocation Details (for local tools):")
             system_instruction_parts.extend(tool_invocation_instructions)

        system_instruction = "\n\n".join(filter(None, system_instruction_parts))
        # print(f"[DEBUG] System Instruction:\n{system_instruction}")
        return system_instruction

    def _extract_args_from_proto(self, args_proto: Any) -> Dict[str, Any]:
        """Extract arguments from the function call proto."""
        # Handle MapComposite objects (common in newer Protobuf versions)
        if hasattr(args_proto, 'items') and callable(args_proto.items):
            try:
                return {k: self._extract_value_from_proto(v) for k, v in args_proto.items()}
            except Exception as e:
                self._log("ERROR", f"Error extracting from MapComposite: {e}")
        
        # Handle standard proto format
        if hasattr(args_proto, 'fields'):
            args_dict = {}
            for key, value in args_proto.fields.items():
                args_dict[key] = self._extract_value_from_proto(value)
            return args_dict
        
        # Try to convert to a dictionary if it's a JSON string
        if isinstance(args_proto, str):
            try:
                return json.loads(args_proto)
            except json.JSONDecodeError:
                pass
        
        # Last resort - try to convert the object to a string and parse it
        try:
            args_str = str(args_proto)
            if '{' in args_str and '}' in args_str:
                # Try to extract a JSON-like structure
                json_part = args_str[args_str.find('{'):args_str.rfind('}')+1]
                return json.loads(json_part)
        except Exception:
            pass
            
        self._log("ERROR", f"Failed to parse function arguments: {args_proto} of type {type(args_proto)}")
        return {}
                
    def _extract_text_from_response(self, response: Any) -> str:
        """Extract text content from a model response."""
        if not response or not response.candidates or not response.candidates[0].content:
            return "I couldn't generate a response. Please try again."
            
        text_parts = []
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'text') and part.text:
                text_parts.append(part.text)
                
        return '\n'.join(text_parts) if text_parts else "I couldn't generate a text response."

    def _extract_value_from_proto(self, value_proto: Any) -> Any:
        """Extract a value from a protobuf value object."""
        # Handle primitive types
        if hasattr(value_proto, 'string_value'): return value_proto.string_value
        if hasattr(value_proto, 'number_value'): return value_proto.number_value
        if hasattr(value_proto, 'bool_value'): return value_proto.bool_value
        if hasattr(value_proto, 'null_value'): return None
        
        # Handle list types
        if hasattr(value_proto, 'list_value'):
            if hasattr(value_proto.list_value, 'values'):
                return [self._extract_value_from_proto(v) for v in value_proto.list_value.values]
            return []
            
        # Handle struct/map types
        if hasattr(value_proto, 'struct_value'):
            if hasattr(value_proto.struct_value, 'fields'):
                return {k: self._extract_value_from_proto(v) for k, v in value_proto.struct_value.fields.items()}
            return {}
            
        # Handle MapComposite objects
        if hasattr(value_proto, 'items') and callable(value_proto.items):
            try:
                return {k: self._extract_value_from_proto(v) for k, v in value_proto.items()}
            except Exception:
                pass
                
        # Handle direct values
        if isinstance(value_proto, (str, int, float, bool, list, dict)):
            return value_proto
            
        # Last resort - convert to string
        return str(value_proto)

    def _send_function_error(self, function_name: str, error_msg: str) -> Any:
        print(f"[ERROR] Sending function error: {function_name} - {error_msg}")
        if not self.chat_session:
            print("[CRITICAL] Chat session not initialized, cannot send function error.")
            return "Error: Chat session not available."
        try:
            return self.chat_session.send_message([
                Part(function_response={'name': function_name or 'unknown_tool_error', 'response': {'error': error_msg}})
            ])
        except Exception as e:
            print(f"[ERROR] Failed to send error message via chat_session: {str(e)}")
            return f"Error in {function_name or 'unknown'}: {error_msg}" # Fallback text

    def _get_tool_list_summary(self) -> str:
        summary_lines = ["Available Tools Summary:"]
        local_tools = self.tool_manager.get_all_tools()
        summary_lines.append("\nLocal Tools:")
        if local_tools:
            for func_name, tool_instance in local_tools.items():
                tool_desc = "(No description available)"
                if hasattr(tool_instance, 'get_summary') and callable(tool_instance.get_summary):
                    try: tool_desc = tool_instance.get_summary()
                    except Exception as e: tool_desc = f"(Error getting summary: {e})"
                elif hasattr(tool_instance, 'get_definition') and callable(tool_instance.get_definition):
                    try:
                        definition = tool_instance.get_definition()
                        if definition and definition.get('function_declarations'):
                            desc_from_def = definition['function_declarations'][0].get('description')
                            if desc_from_def: tool_desc = desc_from_def
                    except Exception as e: tool_desc = f"(Error getting description from definition: {e})"
                summary_lines.append(f"  - {func_name}: {tool_desc}")
        else:
            summary_lines.append("  (No local tools loaded)")

        if self.config_manager.mcp_server_tools_info:
            summary_lines.append("\nMCP Server Tools:")
            for server_name, tools_list in self.config_manager.mcp_server_tools_info.items():
                summary_lines.append(f"  Server '{server_name}':")
                if tools_list:
                    for tool_info in tools_list:
                        summary_lines.append(f"    - {tool_info['name']}: {tool_info['description']}")
                else:
                    summary_lines.append("    (No tools listed for this server)")
        else:
            summary_lines.append("  (No MCP server tools configured or loaded)")
        return "\n".join(summary_lines)

    async def chat(self, prompt: str, max_tool_calls: int = 5) -> str:
        if not prompt or not prompt.strip():
            self._log("AI", "Please enter a message to continue.")
            return

        if not self.chat_session or not self.model:
            return "Error: Chat session or model not initialized."

        self._log("USER", f"User entered: {prompt}")

        if prompt.strip().lower().startswith("/help"):
            parts = prompt.strip().split()
            if len(parts) == 2:
                help_tool_name = parts[1]
                tool_instance = self.tool_manager.get_tool_instance(help_tool_name)
                if tool_instance and hasattr(tool_instance, 'get_help'):
                    return f"[Help for {help_tool_name}]\n{tool_instance.get_help()}"
                else:
                    available_tools_str = ', '.join(self.tool_manager.get_all_tools().keys())
                    return f"Sorry, I couldn't find help for '{help_tool_name}'. Available local tools are: {available_tools_str if available_tools_str else 'None'}."
            else:
                return "Usage: /help <tool_name>\nExample: /help get_weather"
        elif prompt.strip().lower() == "/tool list":
            return self._get_tool_list_summary()

        current_message_content: Union[str, List[Part]] = prompt
        tool_call_count = 0
        # Track previous tool calls to detect repetition
        previous_tool_calls = []
        repeated_call_count = {}

        try:
            while tool_call_count < max_tool_calls:
                self._log("DEBUG", f"Sending to model (Loop {tool_call_count + 1}): {current_message_content}")
                response = self.chat_session.send_message(
                    current_message_content,
                    generation_config=genai.types.GenerationConfig(temperature=0.2) # Updated to new API
                )

                function_call_to_process = None
                if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                    for part_content in response.candidates[0].content.parts:
                        if hasattr(part_content, 'function_call') and part_content.function_call:
                            function_call_to_process = part_content.function_call
                            break

                if function_call_to_process:
                    tool_call_count += 1
                    tool_name = function_call_to_process.name
                    tool_args = self._extract_args_from_proto(function_call_to_process.args)
                    self._log("AI", f"Tool requested: {tool_name} with args: {tool_args}")
                    
                    # Check for repeated tool calls
                    tool_call_key = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                    if tool_call_key in previous_tool_calls:
                        # Increment the count for this specific tool call
                        repeated_call_count[tool_call_key] = repeated_call_count.get(tool_call_key, 1) + 1
                        
                        # If the same tool with the same args has been called 3+ times, break the loop
                        if repeated_call_count[tool_call_key] >= 3:
                            self._log("WARN", f"Detected repeated tool call: {tool_name} with same args. Breaking loop.")
                            # Send a special message to help the model understand the task is complete
                            final_response = self.chat_session.send_message(
                                f"The tool {tool_name} has been called multiple times with the same arguments and has completed successfully. Please provide a final response to the user without calling any more tools.",
                                generation_config=genai.types.GenerationConfig(temperature=0.2)
                            )
                            return self._extract_text_from_response(final_response)
                    
                    # Add this tool call to the history
                    previous_tool_calls.append(tool_call_key)
                    
                    tool_instance = self.tool_manager.get_tool_instance(tool_name)

                    # Handle legacy class-based tools with an .execute() method
                    if tool_instance and hasattr(tool_instance, 'execute') and callable(getattr(tool_instance, 'execute')):
                        try:
                            tool_output = await tool_instance.execute(**tool_args)
                            if not isinstance(tool_output, dict):
                                self._log("WARN", f"Tool {tool_name} did not return a dict. Wrapping: {tool_output}")
                                tool_response_content_dict = {"result": str(tool_output)}
                            else:
                                tool_response_content_dict = tool_output
                        except Exception as e:
                            error_msg = f"Error executing tool {tool_name}: {str(e)}"
                            self._log("ERROR", error_msg)
                            traceback.print_exc()
                            tool_response_content_dict = {'error': error_msg}
                    # Handle new AITool functions which are directly callable
                    elif tool_instance and callable(tool_instance):
                        try:
                            # Check if the tool function is async
                            if inspect.iscoroutinefunction(tool_instance):
                                tool_output = await tool_instance(**tool_args)
                            else:
                                tool_output = tool_instance(**tool_args)

                            if not isinstance(tool_output, dict):
                                self._log("WARN", f"Tool {tool_name} did not return a dict. Wrapping: {tool_output}")
                                tool_response_content_dict = {"result": str(tool_output)}
                            else:
                                tool_response_content_dict = tool_output
                        except Exception as e:
                            error_msg = f"Error executing callable tool {tool_name}: {str(e)}"
                            self._log("ERROR", error_msg)
                            traceback.print_exc()
                            tool_response_content_dict = {'error': error_msg}
                    else:
                        error_msg = f"Unknown or non-executable tool: {tool_name}"
                        self._log("ERROR", error_msg)
                        tool_response_content_dict = {'error': error_msg}

                    current_message_content = [Part(function_response={'name': tool_name, 'response': tool_response_content_dict})]
                    continue # Next loop iteration with tool response
                else: # No function call, model should respond with text
                    response_text = "".join(p.text for p in response.candidates[0].content.parts if hasattr(p, 'text')).strip()
                    if not response_text: # Fallback for various empty response scenarios
                        if response.candidates and response.candidates[0].finish_reason == genai.types.FinishReason.STOP and not response.text:
                            response_text = "(Model generated no text content before stopping)"
                        else:
                            finish_reason_str = str(response.candidates[0].finish_reason) if (response.candidates and response.candidates[0].finish_reason) else 'N/A'
                            response_text = f"(No textual response. Finish reason: {finish_reason_str})"
                    self._log("AI", response_text)

                    return response_text

            # Max tool calls reached
            if tool_call_count >= max_tool_calls:
                self._log("WARN", f"Maximum tool call limit ({max_tool_calls}) reached. Sending last tool response for a final summary.")
                response = self.chat_session.send_message(
                    current_message_content, # This is the last tool's response
                    generation_config=genai.types.GenerationConfig(temperature=0.2)
                )
                response_text = "".join(p.text for p in response.candidates[0].content.parts if hasattr(p, 'text')).strip()
                function_call_in_final_response = None
                if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            function_call_in_final_response = part.function_call
                            break
                if response_text:
                    self._log("AI", response_text)

                    return response_text
                elif function_call_in_final_response:
                    return f"(Task ended after reaching tool call limit. Model wanted to call: {function_call_in_final_response.name})"
                else:
                    return "(Task completed, but model provided no final summary after reaching tool call limit.)"

        except Exception as e:
            error_msg = f"An error occurred in the chat method: {str(e)}"
            self._log("ERROR", error_msg)
            self._log("ERROR", f"Details: {traceback.format_exc()}")
            return f"I'm sorry, but I encountered a critical error: {str(e)}"
        return "(Should not be reached - error in chat logic)" # Should not happen
