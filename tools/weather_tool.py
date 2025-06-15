import json
import requests
from geopy.geocoders import Nominatim
import traceback
from typing import Dict, Any, Optional, List

class WeatherTool:
    def __init__(self, user_agent: str = "weather_tool_module"):
        """
        Initializes the WeatherTool.

        Args:
            user_agent: The user agent string to use for the geocoder.
        """
        self.geolocator = Nominatim(user_agent=user_agent)

    def get_definition(self) -> Dict[str, Any]:
        """Returns the tool definition for the Gemini model."""
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

    def get_invocation_instructions(self) -> str:
        """Returns the specific instructions for how the LLM should invoke this tool."""
        return """When the user asks about the weather, you MUST respond with a tool call in this exact format:
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
- Do NOT include any other text when you want to execute a tool"""

    def execute(self, location: str, unit: str = "celsius") -> Dict[str, Any]:
        """
        Get weather information from Open-Meteo API.

        Args:
            location: The location to get weather for (city name or coordinates).
            unit: The temperature unit (celsius or fahrenheit).

        Returns:
            Dictionary with weather information or error details.
        """
        try:
            location_data = self.geolocator.geocode(location, timeout=10)
            if not location_data:
                return {
                    "location": location,
                    "error": "Could not find coordinates for the specified location."
                }

            temperature_unit = "celsius"
            if unit and unit.lower() in ['celsius', 'fahrenheit']:
                temperature_unit = unit.lower()

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

            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()  # Raises HTTPError for bad responses (4XX or 5XX)
            data = response.json()

            result = {
                "location_name": f"{location_data.address}",
                "coordinates": {
                    "latitude": location_data.latitude,
                    "longitude": location_data.longitude
                },
                "current": data.get("current", {}),
                "hourly_forecast": {
                    "time": data.get("hourly", {}).get("time", [])[:24],
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
            return result

        except requests.exceptions.Timeout:
            return {
                "location": location,
                "error": "Request to weather API timed out."
            }
        except requests.exceptions.RequestException as e:
            return {
                "location": location,
                "error": f"Failed to fetch weather data: {str(e)}"
            }
        except Exception as e:
            return {
                "location": location,
                "error": f"An unexpected error occurred while fetching weather: {str(e)}",
                "traceback": traceback.format_exc()
            }
