import os
import json
import configparser
import traceback
from pathlib import Path
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from typing import Dict, Any, Optional, List, Union, Literal, TypedDict
from tools.weather_tool import WeatherTool
from google.protobuf.struct_pb2 import Value, Struct # For manual tool call mocking

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
        self.weather_tool = WeatherTool(user_agent=f"google_ai_integration/{self.model_name}")

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
        Get the system instruction for the model.

        Returns:
            str: The system instruction
        """
        base_prompt = "You are a helpful AI assistant. You have access to the following tools:"

        tool_instructions = []
        # In the future, if you have multiple tools, you would iterate through them here.
        # For now, we just have the weather tool.
        if hasattr(self, 'weather_tool') and hasattr(self.weather_tool, 'get_invocation_instructions'):
            tool_instructions.append(self.weather_tool.get_invocation_instructions())

        # Combine instructions
        full_tool_instructions = "\n\n".join(tool_instructions)

        # General instructions for after tool use, or non-tool queries
        general_behavior = """For all other queries not related to the tools above, respond normally.

When providing weather information (after a successful tool call), include relevant details like:
- Current temperature and conditions
- Wind speed and direction
- Humidity levels
- A brief forecast for the next few hours or the day
- Any relevant weather alerts or warnings

Always be friendly and helpful!"""

        return f"{base_prompt}\n\n{full_tool_instructions}\n\n{general_behavior}"

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

        # Create model with system instruction and tools
        model = genai.GenerativeModel(
            model_name=self.model_name,
            tools=[self.weather_tool.get_definition()],
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

    def process_tool_call(self, function_call: Any, chat_session: Any) -> str:
        """
        Process a function call from the model, execute the tool, and return the model's
        textual response after consuming the tool's output.

        Args:
            function_call: The function call object from the model (e.g., part.function_call).
            chat_session: The active chat session with the model.

        Returns:
            The model's final text response after the tool interaction.
        """
        try:
            tool_name = function_call.name
            tool_args = self._extract_args_from_proto(function_call.args)

            print(f"\n[AI] Tool requested: {tool_name} with args: {tool_args}")

            api_response_data = None
            if tool_name == 'get_weather':
                if hasattr(self, 'weather_tool'):
                    api_response_data = self.weather_tool.execute(**tool_args)
                    print(f"[DEBUG] Weather tool raw response: {api_response_data}")
                else:
                    error_msg = "Weather tool not initialized internally."
                    print(f"[ERROR] {error_msg}")
                    api_response_data = {'error': error_msg}
            else:
                error_msg = f"Unknown tool: {tool_name}"
                print(f"[ERROR] {error_msg}")
                api_response_data = {'error': error_msg}

            # Send the tool's response (success or error) back to the model using dictionary format
            model_response_after_tool = chat_session.send_message(
                [{
                    'function_response': {
                        'name': tool_name,
                        'response': api_response_data
                    }
                }],
                stream=False
            )

            # The model's response to the function_response should be text
            final_text = ""
            if model_response_after_tool.candidates and model_response_after_tool.candidates[0].content and model_response_after_tool.candidates[0].content.parts:
                final_text = "".join(p.text for p in model_response_after_tool.candidates[0].content.parts if hasattr(p, 'text')).strip()
            elif hasattr(model_response_after_tool, 'text'): # Fallback
                final_text = model_response_after_tool.text

            if not final_text:
                final_text = "(Tool executed, but model provided no further text response.)"
                print("[WARN] Model provided no text after tool execution.")

            return final_text

        except Exception as e:
            error_msg = f"Critical error in process_tool_call for '{getattr(function_call, 'name', 'unknown_tool')}': {str(e)}"
            print(f"\n[ERROR] {error_msg}")
            print(f"\n[ERROR] Details: {traceback.format_exc()}")
            # Try to send a structured error back to the model if possible
            # This uses the _send_function_error helper which should be defined elsewhere
            # or implemented here if it's simple enough.
            # For now, returning a simple error string to the user if _send_function_error is complex.
            # return f"Error processing tool: {str(e)}" # This would go to the end user directly
            # Let's assume _send_function_error exists and handles sending error to model via chat_session
            current_fn_name = getattr(function_call, 'name', 'unknown_tool_in_exception')
            return self._send_function_error(chat_session, current_fn_name, error_msg)

    def chat(self, prompt: str) -> str:
        """
        Process a user's message and return the model's response.

        Args:
            prompt: The user's message

        Returns:
            The model's final response
        """
        try:
            print(f"\n[User] {prompt}")

            model = self.initialize_model() # This already incorporates tools
            # Start chat without automatic function calling, as we handle it manually
            chat_session = model.start_chat(enable_automatic_function_calling=False)

            print(f"\n{'='*50}")
            # Send the initial message
            response = chat_session.send_message(
                prompt,
                generation_config={'temperature': 0.2},
                safety_settings=self.SAFETY_SETTINGS_CONFIG # Use class constant
            )

            # Check if the model responded with a structured function call
            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.function_call:
                        args_for_debug = "(unable to display args)"
                        try:
                            args_for_debug = self._extract_args_from_proto(part.function_call.args)
                        except Exception as debug_ex:
                            print(f"[DEBUG_WARN] Could not parse args for debug print: {debug_ex}")
                        print(f"[DEBUG] Model wants to call function: {part.function_call.name} with args: {args_for_debug}")
                        # Process the structured function call
                        return self.process_tool_call(part.function_call, chat_session)

            # If no structured function call, extract direct text response
            response_text = ""
            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                response_text = "".join(p.text for p in response.candidates[0].content.parts if hasattr(p, 'text')).strip()

            if not response_text: # Fallback if parts didn't yield text
                if hasattr(response, 'text') and response.text:
                    response_text = response.text
                elif response.candidates and response.candidates[0].finish_reason == 'STOP' and not response_text:
                    response_text = "(Model generated no text content before stopping)"
                else:
                    # More informative message if no text and not a simple STOP
                    finish_reason = response.candidates[0].finish_reason if response.candidates and response.candidates[0] else 'N/A'
                    response_text = f"(No textual response. Finish reason: {finish_reason})"

            print(f"\n[DEBUG] Direct response text (no structured tool call or after fallback): {response_text}")

            # Fallback: Check for manually formatted tool call in the response text (e.g., /tool ...)
            manual_tool_call_data = self._extract_tool_call(response_text)
            if manual_tool_call_data:
                print(f"[DEBUG] Extracted manual tool call from text: {manual_tool_call_data}")

                args_struct = Struct()
                if isinstance(manual_tool_call_data.get('args'), dict):
                    for k, v_val in manual_tool_call_data['args'].items():
                        val_obj = Value()
                        if isinstance(v_val, str):
                            val_obj.string_value = v_val
                        elif isinstance(v_val, (int, float)):
                            val_obj.number_value = v_val
                        elif isinstance(v_val, bool):
                            val_obj.bool_value = v_val
                        else: # Default to string for other types
                            val_obj.string_value = str(v_val)
                        args_struct.fields[k].CopyFrom(val_obj)

                # Mimic genai.types.FunctionCall structure for process_tool_call
                class MockGeminiFunctionCall:
                    def __init__(self, name, arguments_struct):
                        self.name = name
                        self.args = arguments_struct # process_tool_call expects .args to be the Struct

                mock_call = MockGeminiFunctionCall(
                    name=manual_tool_call_data['name'],
                    arguments_struct=args_struct
                )
                try:
                    return self.process_tool_call(mock_call, chat_session)
                except Exception as e:
                    error_msg = f"Error processing manual tool call '{mock_call.name}': {str(e)}"
                    print(f"\n[ERROR] {error_msg}")
                    traceback.print_exc()
                    # Send a structured error back to the model
                    return self._send_function_error(chat_session, mock_call.name, error_msg)

            return response_text

        except Exception as e:
            error_msg = f"An error occurred in chat method: {str(e)}"
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
            "What's the weather like in Tokyo today?",
            "How about San Francisco, in fahrenheit?",
            "Tell me a joke."
        ]

        for query in queries:
            print("\n" + "="*50)
            print(f"[Query] {query}")
            response = ai.chat(query)
            print(f"[Response] {response}")

    except Exception as e:
        print(f"An error occurred: {str(e)}")


if __name__ == "__main__":
    main()
