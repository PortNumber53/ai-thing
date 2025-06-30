# Multi-Tool AI Agent

A sophisticated, conversational AI agent powered by Google's Gemini model. This agent can understand complex, multi-step requests and use a variety of tools—including weather forecasting and secure file system operations—to fulfill them.

## Key Features

- **Advanced Conversational AI**: Utilizes Google's Gemini models for natural and intelligent dialogue.
- **Multi-Turn Tool Calling**: Can sequentially call multiple tools to solve complex problems that require several steps.
- **Dynamic & Extensible Toolset**:
    - `coder_task`: A specialized sub-agent for resolving coding tasks.
    - `ShellCommandTool`: Executes shell commands asynchronously within a chroot environment.
    - `WebSearchTool`: Performs web searches using Brave Search.
    - Integration with external Model Context Protocol (MCP) servers like Cloudflare for extended capabilities.
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
    brave_api_key = your_brave_api_key_here

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

- **Coding Task**:
  `"Refactor the `main` function in `google_ai_integration.py` to handle asynchronous operations more robustly."`

- **Shell Command Execution**:
  `"List all Python files in the `core/` directory."`

- **Web Search**:
  `"Search the web for 'latest advancements in large language models'."`

- **Get Help for a Tool**:
  `"/help coder_task"`

## Project Structure

-   `google_ai_integration.py`: Main entry point for the AI agent, handling CLI, chat, and orchestration of configuration, tools, and model interaction.
-   `requirements.txt`: Python package dependencies.
-   `core/`: Contains core functionalities of the agent.
    -   `ai_config_manager.py`: Manages application configuration, API keys, and MCP server settings.
    -   `ai_gemini_handler.py`: Encapsulates Gemini model and chat session logic, including tool call orchestration.
    -   `ai_tool_manager.py`: Dynamically loads local and remote tools, managing their registration and execution.
    -   `mcp_client.py`: Handles OAuth authentication and JSON-RPC communication with MCP servers.
    -   `ai_type_definitions.py`: Defines standard data structures for function calls, tools, and chat messages.
-   `tools/`: A directory for all agent-usable tools.
    -   `coder_tool.py`: Implements the `coder_task` for resolving coding tasks.
    -   `shell_command_tool.py`: Provides `ShellCommandTool` for asynchronous command execution.
    -   `web_search_tool.py`: Implements the `WebSearchTool` for performing web searches.
-   `~/.config/ai-thing/secrets.ini`: Local configuration for API keys and settings (not in repository).

## Notes

-   The chroot jail environment is a mandatory security feature. The AI's file and shell operations are strictly confined to the directory specified in your `secrets.ini`.
-   The agent's capabilities are highly modular and extensible through the `tools/` directory and integration with external MCP servers.
