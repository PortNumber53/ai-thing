import os
import json
import configparser
import argparse
import traceback
import sys
from pathlib import Path
from typing import Optional

from core.ai_config_manager import AIConfigManager
from core.ai_tool_manager import AIToolManager

class GoogleAIIntegration:
    """
    Orchestrates AI integration using modular components for configuration,
    tool management, and Gemini model interaction.
    """
    def __init__(self, profile_name: Optional[str] = None, model_name_override: Optional[str] = None):
        """
        Initialize the Google AI integration.

        Args:
            profile_name: The name of the profile to use from secrets.ini.
            model_name_override: Optional model name to override the one from config or default.
        """
        default_model_for_config = "gemini-1.5-flash-preview-0514"
        if model_name_override:
            default_model_for_config = model_name_override

        self.config_manager = AIConfigManager(profile_name=profile_name, model_name_default=default_model_for_config)

        final_model_name = model_name_override if model_name_override else self.config_manager.model_name

        if model_name_override and self.config_manager.model_name != model_name_override:
            print(f"[INFO] Overriding model from config ('{self.config_manager.model_name}') with CLI argument: '{model_name_override}'")
            self.config_manager.model_name = model_name_override

        self.tool_manager: Optional[AIToolManager] = None
        self.gemini_handler: Optional['GeminiChatHandler'] = None

        print("[INFO] GoogleAIIntegration initialized successfully.")

    def _initialize_chat_components(self):
        """Initializes the components required for chat and tool operations."""
        if self.gemini_handler is not None:
            return

        from core.ai_gemini_handler import GeminiChatHandler

        print("[INFO] Initializing chat and tool components...")
        self.tool_manager = AIToolManager(
            config_manager=self.config_manager,
            chroot_dir=self.config_manager.chroot_dir,
            model_name=self.config_manager.model_name,
            mcp_server_configs=self.config_manager.mcp_server_configs,
            brave_api_key=self.config_manager.brave_api_key
        )
        self.gemini_handler = GeminiChatHandler(
            config_manager=self.config_manager,
            tool_manager=self.tool_manager
        )

    def display_info(self):
        """Displays the current configuration via the AIConfigManager."""
        self.config_manager.display_info()

    def list_tools(self):
        """Prints the summary of available tools via the GeminiChatHandler."""
        self._initialize_chat_components()
        tool_summary = self.gemini_handler._get_tool_list_summary()
        print(tool_summary)

    def chat(self, prompt: str, max_tool_calls: int = 10) -> str:
        """
        Process a user's message and return the model's response.

        Args:
            prompt: The user's message.
            max_tool_calls: Maximum number of consecutive tool calls allowed.

        Returns:
            The model's final response.
        """
        self._initialize_chat_components()
        return self.gemini_handler.chat(prompt, max_tool_calls=max_tool_calls)

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
  - List available tools: python google_ai_integration.py tools list
"""
    )

    parser.add_argument(
        'args',
        nargs='*',
        help="A command ('info', 'tools list') or a query to send to the AI. If omitted, starts an interactive session."
    )

    parser.add_argument(
        '--profile',
        type=str,
        default=None,
        help='Specify a configuration profile to use from secrets.ini.'
    )

    parser.add_argument(
        '--model',
        type=str,
        default=None,
        help='Specify the AI model name to use (e.g., gemini-1.5-pro-latest). Overrides profile setting if provided.'
    )

    args = parser.parse_args()

    try:
        ai = GoogleAIIntegration(profile_name=args.profile, model_name_override=args.model)

        if args.args and args.args[0] == 'info':
            if len(args.args) > 1:
                print(f"[ERROR] The 'info' command does not take additional arguments. You provided: {' '.join(args.args[1:])}", file=sys.stderr)
                sys.exit(1)
            ai.display_info()
        elif args.args and len(args.args) >= 2 and args.args[0] == 'tools' and args.args[1] == 'list':
            if len(args.args) > 2:
                print(f"[ERROR] The 'tools list' command does not take additional arguments. You provided: {' '.join(args.args[2:])}", file=sys.stderr)
                sys.exit(1)
            ai.list_tools()
        elif args.args and args.args[0] == 'chat':
            if len(args.args) > 1:
                print(f"[WARNING] The 'chat' command does not take additional arguments. You provided: {' '.join(args.args[1:])}. These will be ignored.", file=sys.stderr)
            # This block will now intentionally fall through to the interactive chat session
            pass
        elif args.args:
            query_text = " ".join(args.args)
            response = ai.chat(query_text)
        if not args.args or (args.args and args.args[0] == 'chat'):
            print("\n==================================================")
            print("Entering interactive chat mode. Press Ctrl+C to exit.")
            print("==================================================")
            try:
                while True:
                    query = input("[User] ")
                    if query.lower() in ['exit', 'quit']:
                        break
                    response = ai.chat(query)
            except (KeyboardInterrupt, EOFError):
                print("\nExiting chat.")

    except (FileNotFoundError, KeyError, ValueError, RuntimeError) as e:
        print(f"[ERROR] Initialization or operational error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[CRITICAL] An unexpected error occurred: {str(e)}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
