import os
import json
import configparser
import traceback
from pathlib import Path
import google.generativeai as genai
from typing import Dict, Any, Optional, List, Union, Literal, TypedDict

# Type definitions for function calling
class FunctionCall(TypedDict):
    name: str
    args: Dict[str, Any]

class FunctionResponse(TypedDict):
    name: str
    response: Dict[str, Any]

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

    def __init__(self, model_name: str = "gemini-1.5-pro-latest"):
        """
        Initialize the Google AI integration.

        Args:
            model_name: The name of the model to use (default: gemini-1.5-pro-latest)
        """
        self.model_name = model_name
        self._configure_gemini()

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

    def get_weather(self, location: str, unit: str = "celsius") -> str:
        """
        Get weather information from Open-Meteo API.

        Args:
            location: The location to get weather for (city name or coordinates)
            unit: The temperature unit (celsius or fahrenheit)

        Returns:
            JSON string with weather information
        """
        import requests
        from geopy.geocoders import Nominatim

        try:
            # Initialize geocoder
            geolocator = Nominatim(user_agent="google_ai_integration")

            # Get location coordinates
            location_data = geolocator.geocode(location)
            if not location_data:
                return json.dumps({
                    "location": location,
                    "error": "Could not find coordinates for the specified location."
                })

            # Convert unit to Open-Meteo format, default to celsius if not provided
            temperature_unit = "celsius"
            if unit and unit.lower() in ['celsius', 'fahrenheit']:
                temperature_unit = unit.lower()

            # Build the API URL
            base_url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": location_data.latitude,
                "longitude": location_data.longitude,
                "current": ["temperature_2m", "wind_speed_10m", "relative_humidity_2m", "weather_code"],
                "hourly": ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "weather_code"],
                "temperature_unit": temperature_unit,
                "wind_speed_unit": "kmh",
                "timezone": "auto",
                "forecast_days": 1
            }

            # Make the API request
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()

            # Format the response
            result = {
                "location": f"{location_data.address}",
                "coordinates": {
                    "latitude": location_data.latitude,
                    "longitude": location_data.longitude
                },
                "current": data.get("current", {}),
                "hourly_forecast": {
                    "time": data.get("hourly", {}).get("time", [])[:24],  # Next 24 hours
                    "temperature_2m": data.get("hourly", {}).get("temperature_2m", [])[:24],
                    "relative_humidity_2m": data.get("hourly", {}).get("relative_humidity_2m", [])[:24],
                    "wind_speed_10m": data.get("hourly", {}).get("wind_speed_10m", [])[:24],
                    "weather_code": data.get("hourly", {}).get("weather_code", [])[:24]
                },
                "unit": {
                    "temperature": temperature_unit,
                    "wind_speed": "km/h"
                }
            }

            return json.dumps(result, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "location": location,
                "error": f"Failed to fetch weather data: {str(e)}"
            })
        except Exception as e:
            import traceback
            return json.dumps({
                "location": location,
                "error": f"An error occurred: {str(e)}",
                "traceback": traceback.format_exc()
            })

    def _get_weather_tool(self) -> dict:
        """
        Get the weather tool definition for Gemini.

        Returns:
            dict: The tool definition
        """
        return {
            'function_declarations': [{
                'name': 'get_weather',
                'description': 'Get the current weather and forecast for a given location using Open-Meteo API.',
                'parameters': {
                    'type': 'OBJECT',
                    'properties': {
                        'location': {
                            'type': 'STRING',
                            'description': 'The city name, address, or coordinates (e.g., "New York, NY" or "40.7128,-74.0060")'
                        },
                        'unit': {
                            'type': 'STRING',
                            'enum': ['celsius', 'fahrenheit'],
                            'description': 'The unit for temperature, either celsius or fahrenheit. Default is celsius.'
                        }
                    },
                    'required': ['location']
                }
            }]
        }

    def _get_safety_settings(self) -> list[dict]:
        """Define safety settings for the model."""
        return [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

    def _get_system_instruction(self) -> str:
        """
        Get the system instruction for the model.

        Returns:
            str: The system instruction
        """
        return """You are a helpful AI assistant with access to weather information.

        When the user asks about the weather, you MUST respond with a tool call in this exact format:
        /tool get_weather({"location": "City Name"})

        Examples:
        User: What's the weather like in Tokyo?
        You: /tool get_weather({"location": "Tokyo"})

        User: What's the temperature in New York in Fahrenheit?
        You: /tool get_weather({"location": "New York", "unit": "fahrenheit"})

        Important:
        - The response MUST start with '/tool get_weather('
        - The arguments MUST be valid JSON
        - The 'location' parameter is REQUIRED
        - The 'unit' parameter is optional (defaults to 'celsius')
        - Do NOT include any other text when you want to execute a tool
        - For all other queries, respond normally
        - 'unit' is optional (default: 'celsius')

        When providing weather information, include relevant details like:
        - Current temperature and conditions
        - Wind speed and direction
        - Humidity
        - Any notable weather alerts or warnings

        If the location is ambiguous, ask for clarification.
        """

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
            tools=[self._get_weather_tool()],
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
        args = {}

        try:
            print(f"[DEBUG] Extracting args from type: {type(args_proto)}")

            # Handle MapComposite type directly
            if 'MapComposite' in str(type(args_proto)):
                print("[DEBUG] Processing MapComposite")
                for key, value in args_proto.items():
                    print(f"[DEBUG] Processing key: {key}, value: {value}")
                    if hasattr(value, 'string_value'):
                        args[key] = value.string_value
                        print(f"[DEBUG] Extracted string: {key} = {value.string_value}")
                    elif hasattr(value, 'number_value'):
                        args[key] = value.number_value
                        print(f"[DEBUG] Extracted number: {key} = {value.number_value}")
                    elif hasattr(value, 'bool_value'):
                        args[key] = value.bool_value
                        print(f"[DEBUG] Extracted bool: {key} = {value.bool_value}")
                    else:
                        print(f"[DEBUG] Unhandled value type for {key}: {type(value)}")
            # Handle direct fields access
            elif hasattr(args_proto, 'fields'):
                print("[DEBUG] Processing direct fields")
                for key, value in args_proto.fields.items():
                    print(f"[DEBUG] Processing field: {key} = {value}")
                    if hasattr(value, 'string_value'):
                        args[key] = value.string_value
                        print(f"[DEBUG] Extracted string: {key} = {value.string_value}")
                    elif hasattr(value, 'number_value'):
                        args[key] = value.number_value
                        print(f"[DEBUG] Extracted number: {key} = {value.number_value}")
                    elif hasattr(value, 'bool_value'):
                        args[key] = value.bool_value
                        print(f"[DEBUG] Extracted bool: {key} = {value.bool_value}")
                    else:
                        print(f"[DEBUG] Unhandled value type for {key}: {type(value)}")

            print(f"[DEBUG] Extracted args: {args}")

        except Exception as e:
            print(f"[ERROR] Error extracting arguments: {str(e)}")
            import traceback
            traceback.print_exc()

        return args

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
            return chat.send_message({
                'role': 'function',
                'parts': [{
                    'function_response': {
                        'name': function_name or 'unknown',
                        'response': {'error': error_msg}
                    }
                }]
            })
        except Exception as e:
            print(f"[ERROR] Failed to send error message: {str(e)}")
            # Fallback to a simple text response if the function call fails
            return chat.send_message(f"Error in {function_name or 'unknown'}: {error_msg}")

    def process_tool_call(self, function_call: Any, chat: Any) -> Any:
        """
        Process a function call from the model.

        Args:
            function_call: The function call from the model
            chat: The chat session

        Returns:
            The model's response after processing the function call
        """
        try:
            print(f"\n[DEBUG] Raw function call: {function_call}")
            print(f"[DEBUG] Function call type: {type(function_call)}")

            # Debug: Print all attributes of the function call
            print("[DEBUG] Function call attributes:", dir(function_call))

            # Extract function name
            tool_name = None
            if hasattr(function_call, 'name') and function_call.name:
                tool_name = function_call.name
            elif hasattr(function_call, 'function'):
                tool_name = function_call.function
                print(f"[DEBUG] Found function name in 'function' attribute: {tool_name}")

            if not tool_name:
                error_msg = "Could not determine function name from function call"
                print(f"[ERROR] {error_msg}")
                return self._send_function_error(chat, "unknown", error_msg)

            print(f"[DEBUG] Processing tool call: {tool_name}")

            # Extract arguments
            tool_args = {}

            # Handle dictionary args directly (from our MockFunctionCall)
            if hasattr(function_call, 'args') and isinstance(function_call.args, dict):
                tool_args = function_call.args
                print(f"[DEBUG] Using direct dict args: {tool_args}")
            # Handle protobuf args
            elif hasattr(function_call, 'args'):
                print(f"[DEBUG] Args type: {type(function_call.args)}")
                print(f"[DEBUG] Args dir: {dir(function_call.args)}")

                # Try to extract arguments using our improved method
                tool_args = self._extract_args_from_proto(function_call.args)

                # If we still don't have args, try direct access as a last resort
                if not tool_args and hasattr(function_call.args, 'fields'):
                    print("[DEBUG] Trying direct field access as fallback")
                    for key, value in function_call.args.fields.items():
                        print(f"[DEBUG] Processing field: {key} = {value}")
                        if hasattr(value, 'string_value'):
                            tool_args[key] = value.string_value
                            print(f"[DEBUG]   Extracted string: {key} = {value.string_value}")
                        elif hasattr(value, 'number_value'):
                            tool_args[key] = value.number_value
                            print(f"[DEBUG]   Extracted number: {key} = {value.number_value}")
                        elif hasattr(value, 'bool_value'):
                            tool_args[key] = value.bool_value
                            print(f"[DEBUG]   Extracted bool: {key} = {value.bool_value}")
                        else:
                            print(f"[DEBUG]   Unhandled value type for {key}: {type(value)}")

            # Try to get args from 'arguments' attribute as fallback
            if not tool_args and hasattr(function_call, 'arguments') and function_call.arguments:
                print("[DEBUG] Found 'arguments' attribute, trying to parse as JSON")
                try:
                    import json
                    tool_args = json.loads(function_call.arguments)
                    print(f"[DEBUG] Successfully parsed arguments: {tool_args}")
                except Exception as e:
                    print(f"[ERROR] Failed to parse arguments: {str(e)}")

            print(f"[AI] Tool requested: {tool_name} with args: {tool_args}")

            # Process the tool call
            if tool_name == 'get_weather':
                return self._handle_weather_tool(tool_args, chat)
            else:
                error_msg = f"Unknown tool: {tool_name}"
                print(f"[ERROR] {error_msg}")
                return self._send_function_error(chat, tool_name, error_msg)

        except Exception as e:
            error_msg = f"Error processing tool call: {str(e)}"
            print(f"\n[ERROR] {error_msg}")
            import traceback
            traceback.print_exc()
            return self._send_function_error(chat, tool_name if 'tool_name' in locals() else "unknown", error_msg)

    def _handle_weather_tool(self, tool_args: dict, chat: Any) -> Any:
        """
        Handle the weather tool call.

        Args:
            tool_args: Dictionary containing the tool arguments
            chat: The chat session

        Returns:
            The response from the weather API
        """
        try:
            print(f"[DEBUG] Handling weather tool with args: {tool_args}")

            # Extract location from args
            location = tool_args.get('location')
            if not location:
                error_msg = "No location provided for weather check"
                print(f"[ERROR] {error_msg}")
                return self._send_function_error(chat, "get_weather", error_msg)

            # Get weather data
            weather_data = self.get_weather(location)

            # Parse the weather data
            weather_json = json.loads(weather_data)

            # Create a structured response
            current = weather_json['current']
            response_data = {
                'location': weather_json['location'],
                'temperature': f"{current['temperature_2m']}°{weather_json['unit']['temperature']}",
                'wind': f"{current['wind_speed_10m']} {weather_json['unit']['wind_speed']}",
                'humidity': f"{current['relative_humidity_2m']}%"
            }

            print(f"[DEBUG] Weather response data: {response_data}")

            # Format the tool response as a system message
            system_message = (
                f"Here's the tool response for the weather in {response_data['location']}:\n"
                f"- Temperature: {response_data['temperature']}\n"
                f"- Wind: {response_data['wind']}\n"
                f"- Humidity: {response_data['humidity']}\n\n"
                "Please provide a friendly and concise response to the user's original query "
                "based on this weather information."
            )

            # Send the system message and get the model's response
            model_response = chat.send_message(
                content=system_message,
                generation_config={
                    'temperature': 0.2,
                },
                stream=False
            )

            # Return the model's response text
            return model_response.text

        except Exception as e:
            error_msg = f"Error getting weather: {str(e)}"
            print(f"[ERROR] {error_msg}")

            traceback.print_exc()
            return self._send_function_error(chat, "get_weather", error_msg)

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

            # Initialize the model with system instruction and start a chat session
            model = self.initialize_model()
            chat = model.start_chat(enable_automatic_function_calling=False)

            print(f"\n{'='*50}")

            # Send the initial message
            response = chat.send_message(
                prompt,
                generation_config={
                    'temperature': 0.2,
                },
                safety_settings=[
                    {
                        'category': 'HARM_CATEGORY_HARASSMENT',
                        'threshold': 'BLOCK_ONLY_HIGH'
                    },
                    {
                        'category': 'HARM_CATEGORY_HATE_SPEECH',
                        'threshold': 'BLOCK_ONLY_HIGH'
                    },
                    {
                        'category': 'HARM_CATEGORY_SEXUALLY_EXPLICIT',
                        'threshold': 'BLOCK_ONLY_HIGH'
                    },
                    {
                        'category': 'HARM_CATEGORY_DANGEROUS_CONTENT',
                        'threshold': 'BLOCK_ONLY_HIGH'
                    },
                ]
            )

            # Get the response text
            if hasattr(response, 'text'):
                response_text = response.text
            elif hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    response_text = '\n'.join(part.text for part in candidate.content.parts if hasattr(part, 'text'))
            else:
                response_text = str(response) if response else "No response generated"

            print(f"\n[DEBUG] Response text: {response_text}")

            # Check for tool call in the response
            tool_call = self._extract_tool_call(response_text)
            if tool_call:
                print(f"[DEBUG] Extracted tool call: {tool_call}")

                # Create a mock function call object
                class MockFunctionCall:
                    def __init__(self, name, args):
                        self.name = name
                        self.args = args

                try:
                    mock_call = MockFunctionCall(
                        name=tool_call['name'],
                        args=tool_call['args']
                    )

                    # Process the tool call
                    response = self.process_tool_call(mock_call, chat)
                    print(f"\n[Response] {response}")

                    # Get the final response text after tool call
                    if hasattr(response, 'text'):
                        return response.text
                    return str(response) if response else "No response from tool"

                except Exception as e:
                    error_msg = f"Error processing tool call: {str(e)}"
                    print(f"\n[ERROR] {error_msg}")
                    import traceback
                    traceback.print_exc()
                    return f"Error processing your request: {str(e)}"

            # If no tool call was found, return the original response
            return response_text

        except Exception as e:
            error_msg = f"An error occurred: {str(e)}"
            print(f"\n[ERROR] {error_msg}")
            import traceback
            print(f"\n[ERROR] Details: {traceback.format_exc()}")
            return f"I'm sorry, but I encountered an error: {str(e)}"


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
