# AI Weather Assistant

A conversational AI assistant that provides real-time weather information using Google's Gemini model and Open-Meteo weather API.

## Features

- Google AI Studio integration with Gemini models
- Function calling with Gemini for dynamic tool usage
- Real-time weather data from Open-Meteo API
- Location-based weather queries with city name or coordinates
- Support for both Celsius and Fahrenheit temperature units
- Secure API key management

## Setup

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up your API key:
   - Create or edit `~/.config/secrets.ini`
   - Add your Google API key in the `[google]` section:
     ```ini
     [google]
     api_key = your_google_api_key_here
     ```
   - Get an API key from [Google AI Studio](https://makersuite.google.com/)
   - Make sure the file has secure permissions (chmod 600 ~/.config/secrets.ini)

## Usage

Run the Google AI integration example:

```bash
python google_ai_integration.py
```

This will demonstrate function calling with the Gemini model, including a weather tool example.

## Example Queries

- "What's the weather like in Tokyo today?"
- "How about San Francisco, in fahrenheit?"
- "Tell me a joke."

## Project Structure

- `google_ai_integration.py`: Main Google AI integration with function calling
- `requirements.txt`: Python dependencies
- `~/.config/secrets.ini`: Configuration file for API keys (not included in the repository for security)

## Notes

- The weather tool uses the Open-Meteo API for real-time weather data.
- Location lookup is powered by OpenStreetMap's Nominatim geocoding service.
- API keys are stored securely in `~/.config/secrets.ini`.
