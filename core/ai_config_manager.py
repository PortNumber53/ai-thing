import configparser
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

import google.generativeai as genai

class AIConfigManager:
    def __init__(self, profile_name: Optional[str] = None, model_name_default: str = "gemini-1.5-flash-preview-0514"):
        self.profile_name = profile_name
        self.model_name_default = model_name_default

        self.active_profile_name: Optional[str] = None
        self.google_ai_api_key: Optional[str] = None
        self.brave_api_key: Optional[str] = None
        self.model_name: str = model_name_default
        self.chroot_dir: Optional[Path] = None
        self.mcp_config_file_path: Optional[Path] = None
        self.mcp_server_configs: Dict[str, Dict[str, Any]] = {}
        self.mcp_server_tools_info: Dict[str, List[Dict[str, str]]] = {}

        self._initialize_configurations()
        self._load_mcp_configurations()

    def _get_secrets_path(self) -> Path:
        """Get the path to the secrets.ini file."""
        return Path.home() / ".config" / "ai-thing" / "secrets.ini"

    def _load_profile_config(self, profile_name: Optional[str] = None) -> Tuple[str, str, Optional[str], str, str, Optional[str]]:
        """Load configuration from secrets.ini based on the provided or default profile."""
        secrets_path = self._get_secrets_path()
        if not secrets_path.exists():
            raise FileNotFoundError(f"secrets.ini not found at {secrets_path}")

        config = configparser.ConfigParser()
        config.read(secrets_path)

        if 'default' not in config:
            raise KeyError("[default] section not found in secrets.ini.")

        logical_profile_name = profile_name or config.get('default', 'profile', fallback='default')
        section_name = f"profile:{logical_profile_name}" if logical_profile_name != 'default' else 'default'

        if section_name not in config:
            print(f"[WARNING] Profile section '[{section_name}]' not found in {secrets_path}. Falling back to '[default]' profile.", file=sys.stderr)
            section_name = 'default'
            logical_profile_name = 'default'

        if section_name not in config:
             raise KeyError(f"Critical error: Default profile '[default]' not found in {secrets_path} after fallback.")

        def get_value(key: str) -> Optional[str]:
            return config.get(section_name, key, fallback=config.get('default', key, fallback=None))

        api_key = get_value('google_ai_api_key')
        if not api_key:
            raise ValueError(f"Mandatory key 'google_ai_api_key' not found in profile '{logical_profile_name}' or '[default]'.")

        chroot_dir_str = get_value('chroot')
        if not chroot_dir_str:
            raise ValueError(f"Mandatory key 'chroot' not found in profile '{logical_profile_name}' or '[default]'.")

        model_name_from_config = get_value('google_ai_model') or self.model_name_default
        mcp_config_file_str = get_value('mcp_config_file')
        brave_api_key = get_value('brave_api_key')

        return logical_profile_name, api_key, brave_api_key, model_name_from_config, chroot_dir_str, mcp_config_file_str

    def _initialize_configurations(self):
        """
        Initialize core configurations like API key, model name, chroot, and MCP path.
        """
        try:
            (
                self.active_profile_name,
                self.google_ai_api_key,
                self.brave_api_key,
                self.model_name,
                chroot_dir_str,
                mcp_config_file_str
            ) = self._load_profile_config(profile_name=self.profile_name)

            if not self.google_ai_api_key:
                 raise ValueError("Google AI API key not configured.")
            genai.configure(api_key=self.google_ai_api_key)

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

            mcp_info = f", MCP Config: {self.mcp_config_file_path}" if self.mcp_config_file_path else ", MCP Config: Not set"
            print(f"[INFO] Configured with profile. Model: {self.model_name}, Chroot: {self.chroot_dir}{mcp_info}")

        except Exception as e:
            error_message = (
                f"Failed to initialize configurations: {str(e)}\n"
                f"Please ensure your ~/.config/ai-thing/secrets.ini is formatted correctly.\n"
                "Mandatory keys 'google_ai_api_key' and 'chroot' must be present in the active profile or [default]."
            )
            print(f"[ERROR] {error_message}", file=sys.stderr)
            raise RuntimeError(error_message) from e

    def _load_mcp_configurations(self):
        """Load MCP server configurations from the JSON file."""
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
                self.mcp_server_tools_info = {}
                for server_name, server_config in self.mcp_server_configs.items():
                    print(f"  - Found MCP server: {server_name}")
                    if 'provided_tools' in server_config and isinstance(server_config['provided_tools'], list):
                        server_tools = []
                        for tool_info in server_config['provided_tools']:
                            if isinstance(tool_info, dict) and 'name' in tool_info and 'description' in tool_info:
                                server_tools.append({'name': str(tool_info['name']), 'description': str(tool_info['description'])})
                            else:
                                print(f"    [WARNING] Invalid tool info format for server '{server_name}': {tool_info}. Skipping.")
                        if server_tools:
                            self.mcp_server_tools_info[server_name] = server_tools
                            print(f"    - Loaded {len(server_tools)} tools for MCP server '{server_name}'.")
                    elif 'provided_tools' in server_config:
                        print(f"    [WARNING] 'provided_tools' for server '{server_name}' is not a list. Skipping MCP tool loading for this server.")

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

        if self.brave_api_key:
            redacted_brave_key = self.brave_api_key[:4] + "****" + self.brave_api_key[-4:]
        else:
            redacted_brave_key = "Not Set"
        print(f"Brave API Key: {redacted_brave_key}")
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
