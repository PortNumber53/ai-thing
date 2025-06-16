# Multi-Tool AI Agent

A sophisticated, conversational AI agent powered by Google's Gemini model. This agent can understand complex, multi-step requests and use a variety of tools—including weather forecasting and secure file system operations—to fulfill them.

## Key Features

- **Advanced Conversational AI**: Utilizes Google's Gemini models for natural and intelligent dialogue.
- **Multi-Turn Tool Calling**: Can sequentially call multiple tools to solve complex problems that require several steps (e.g., read from a file, process data, write to another file).
- **Dynamic & Extensible Toolset**:
    - `WeatherTool`: Provides real-time weather data from the Open-Meteo API.
    - `FileReadTool`: Reads the contents of files.
    - `FileFullWriteTool`: Writes content to files, with options to override or preserve existing files.
- **Chroot Jail Security**: All file operations are strictly confined to a pre-configured "chroot" directory, preventing the AI from accessing or modifying any files outside its designated workspace. This provides a critical layer of security.
- **Profile-Based Configuration**: Manages API keys and settings like the `chroot_dir` through a `secrets.ini` file with support for multiple profiles.
- **Dynamic System Prompts**: The agent's core instructions are dynamically built from the capabilities of the loaded tools, making the system modular and easy to extend.
- **Interactive Help**: Users can get on-demand instructions for any tool by typing `/help <tool_name>`.

## Setup

1.  **Clone the Repository**:
    ```bash
    git clone <repository_url>
    cd <repository_directory>
    ```

2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure Secrets**:
    -   Create or edit the configuration file at `~/.config/ai-thing/secrets.ini`.
    -   Add your Google API key and define a secure working directory for the AI.

    **Example `secrets.ini`:**
    ```ini
    [default]
    # The active profile to use.
    profile = development

    [profile:development]
    # Get an API key from Google AI Studio: https://makersuite.google.com/
    google_api_key = your_google_api_key_here

    # The secure directory where the AI can read and write files.
    # This path MUST exist.
    chroot_dir = /path/to/your/safe/working/directory
    ```
    -   Make sure the file has secure permissions: `chmod 600 ~/.config/secrets.ini`

## Usage

Run the main integration script:

```bash
python google_ai_integration.py
```

The script will load the configured profile and start a chat session where you can interact with the AI.

## Example Queries

- **Simple Weather Query**:
  `"What's the weather like in Tokyo today?"`

- **File I/O**:
  `"Read the content of 'my_notes.txt' and summarize it for me."`

- **Multi-Step Tool Use**:
  `"What are the temperatures for the cities listed in 'locations.txt'? Write the results into a new file named 'weather_report.txt'."`

- **Get Help for a Tool**:
  `"/help write_file_full"`

## Project Structure

-   `google_ai_integration.py`: The main application logic, handling AI chat, tool loading, and multi-turn execution.
-   `requirements.txt`: Python package dependencies.
-   `tools/`: A directory for all agent-usable tools.
    -   `weather_tool.py`: Fetches weather data.
    -   `file_read_tool.py`: Handles reading files within the chroot jail.
    -   `file_full_write_tool.py`: Handles writing files within the chroot jail.
-   `~/.config/ai-thing/secrets.ini`: Local configuration for API keys and settings (not in repository).

## Notes

-   The weather tool uses the Open-Meteo API and OpenStreetMap's Nominatim geocoding service.
-   The chroot jail for file tools is a mandatory security feature. The AI cannot operate outside the directory specified in your `secrets.ini`.
