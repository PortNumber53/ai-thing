import importlib
import inspect
import functools
import traceback
import atexit
from pathlib import Path
import json
from typing import Dict, Any, List, Optional
from google.generativeai.types import Tool

from .mcp_client import MCPClient
from .ai_type_definitions import AITool
from .ai_config_manager import AIConfigManager


class RemoteToolExecutor:
    """A proxy for executing a tool on a remote MCP server."""
    def __init__(self, client: MCPClient, tool_name: str, supports_streaming: bool = False):
        self.client = client
        self.tool_name = tool_name
        self.supports_streaming = supports_streaming

    def execute(self, **kwargs):
        """Executes the remote tool by calling the client."""
        print(f"[INFO] Executing remote tool '{self.tool_name}' via MCP client for '{self.client.server_name}'.")
        # Pass the streaming preference to the client.
        return self.client.execute_tool(self.tool_name, kwargs, use_streaming=self.supports_streaming)


class AIToolManager:
    def __init__(self, config_manager: AIConfigManager, chroot_dir: Optional[Path], model_name: str, mcp_server_configs: Optional[Dict[str, Any]] = None, brave_api_key: Optional[str] = None):
        self.config_manager = config_manager
        self.chroot_dir = chroot_dir
        self.model_name = model_name
        self.brave_api_key = brave_api_key
        self.tools: Dict[str, Any] = {}
        self.function_declarations: List[Dict[str, Any]] = []
        self.mcp_server_configs = mcp_server_configs
        self.mcp_clients: Dict[str, MCPClient] = {}
        self.remote_tools_loaded = False

        self._load_local_tools()
        self._create_mcp_clients()

    def _load_local_tools(self):
        """Dynamically load tools from the 'tools' subdirectory."""
        tools_dir = Path(__file__).parent.parent / "tools"
        if not tools_dir.is_dir():
            print(f"[WARNING] Tools directory not found: {tools_dir}")
            return

        for tool_file in tools_dir.glob("[!_]*.py"):  # Ignore files starting with _
            module_name = f"tools.{tool_file.stem}"
            try:
                module = importlib.import_module(module_name)
                for name, obj in inspect.getmembers(module):
                    # Handle AITool objects
                    if isinstance(obj, AITool):
                        tool_name = obj.name
                        tool_func = obj.func
                        tool_params = inspect.signature(tool_func).parameters

                        wrapped_func = tool_func
                        if 'chroot_path' in tool_params:
                            if self.chroot_dir:
                                def create_chroot_wrapper(func):
                                    @functools.wraps(func)
                                    def wrapper(**kwargs):
                                        return func(chroot_path=str(self.chroot_dir), **kwargs)
                                    return wrapper
                                wrapped_func = create_chroot_wrapper(tool_func)
                            else:
                                print(f"[CRITICAL_ERROR] Chroot directory not configured for {tool_name} but it's required. Skipping tool loading.")
                                continue
                        
                        self.tools[tool_name] = wrapped_func
                        declaration = {
                            "name": tool_name,
                            "description": obj.description,
                            "parameters": obj.parameters
                        }
                        self.function_declarations.append(declaration)
                        print(f"[INFO] Loaded AITool: {tool_name} from {module_name}")

                    # Handle legacy class-based tools
                    elif inspect.isclass(obj) and obj.__module__ == module_name and hasattr(obj, 'get_definition') and hasattr(obj, 'execute'):
                        tool_instance_args = {}
                        init_params = inspect.signature(obj.__init__).parameters
                        if 'user_agent' in init_params:
                            tool_instance_args['user_agent'] = f"google_ai_integration/{self.model_name}"
                        if 'chroot_dir' in init_params:
                            if self.chroot_dir:
                                tool_instance_args['chroot_dir'] = str(self.chroot_dir)
                            else:
                                print(f"[CRITICAL_ERROR] Chroot directory not configured for {name} but it's required. Skipping tool loading.")
                                continue
                        if 'brave_api_key' in init_params:
                            if self.brave_api_key:
                                tool_instance_args['brave_api_key'] = self.brave_api_key

                        if hasattr(obj, 'requires_brave_api_key') and obj.requires_brave_api_key:
                            if self.brave_api_key:
                                tool_instance_args['api_key'] = self.brave_api_key
                            else:
                                print(f"[WARNING] Tool {name} requires a Brave API key, but it's not configured. Skipping.")
                                continue
                        
                        tool_instance = obj(**tool_instance_args)
                        definition = tool_instance.get_definition()
                        if definition:
                            declarations = definition.get('function_declarations', [])
                            if declarations:
                                func_name = declarations[0].get('name')
                                if func_name:
                                    self.tools[func_name] = tool_instance
                                    self.function_declarations.append(declarations[0])
                                    print(f"[INFO] Loaded tool: {func_name} from {module_name}")
                                else:
                                    print(f"[WARNING] Tool {name} in {module_name} has no function name in definition.")
                        else:
                            print(f"[WARNING] Tool {name} in {module_name} has no definition.")
            except ModuleNotFoundError:
                print(f"[ERROR] Could not import module {module_name}. Ensure 'tools' directory is in PYTHONPATH or structured correctly.")
                traceback.print_exc()
            except Exception as e:
                print(f"[ERROR] Failed to load tool from {tool_file.name}: {e}")
                traceback.print_exc()

    def _create_mcp_clients(self):
        """Creates MCPClient instances and starts their proxies without listing tools."""
        if not self.mcp_server_configs:
            return

        enabled_servers = {name: config for name, config in self.mcp_server_configs.items() if not config.get('disabled')}
        
        if not enabled_servers:
            print("[INFO] No enabled MCP servers found in configuration.")
            return

        print(f"[INFO] Creating {len(enabled_servers)} MCP client(s)...")
        for server_name, config in enabled_servers.items():
            try:
                client = MCPClient(server_name, config, self.config_manager)
                self.mcp_clients[server_name] = client
            except (ValueError, RuntimeError) as e:
                print(f"[ERROR] Failed to create MCP client for '{server_name}': {e}")
            except Exception as e:
                print(f"[ERROR] An unexpected error occurred while initializing MCP client '{server_name}': {e}")
                traceback.print_exc()

    def _load_remote_tools(self):
        """Lists tools from all MCP clients and registers them. This is the blocking part."""
        if self.remote_tools_loaded or not self.mcp_clients:
            return

        print("[INFO] Loading remote tools from MCP clients...")
        for server_name, client in self.mcp_clients.items():
            try:
                remote_tools = client.list_tools()

                if remote_tools:
                    for tool_def in remote_tools:
                        tool_name = tool_def.get('name')
                        if not tool_name:
                            print(f"[WARNING] Skipping a remote tool from '{server_name}' because it has no name.")
                            continue



                        input_schema = tool_def.get('inputSchema', {'type': 'object', 'properties': {}})
                        # The Gemini API doesn't support 'additionalProperties' or '$schema' in the schema, so we remove them.
                        if 'additionalProperties' in input_schema:
                            del input_schema['additionalProperties']
                        if '$schema' in input_schema:
                            del input_schema['$schema']

                        self._sanitize_schema(input_schema)

                        # Sanitize top-level description by removing backticks
                        description_raw = tool_def.get('description', '')
                        description_sanitized = description_raw.replace('`', '')

                        declaration = {
                            "name": tool_name,
                            "description": description_sanitized,
                            "parameters": input_schema
                        }
                        self.function_declarations.append(declaration)

                        supports_streaming = tool_def.get('supportsStreaming', False)
                        if supports_streaming:
                            print(f"[INFO] Remote tool '{tool_name}' from '{server_name}' supports streaming.")

                        if tool_name in self.tools:
                            print(f"[WARNING] Tool name collision: A tool named '{tool_name}' is already loaded. The one from MCP server '{server_name}' will overwrite it.")
                        
                        self.tools[tool_name] = RemoteToolExecutor(client, tool_name, supports_streaming)
                        print(f"[INFO] Loaded remote tool: {tool_name} from MCP server '{server_name}'")
            except Exception as e:
                print(f"[ERROR] Failed to load tools from MCP client '{server_name}': {e}")
        
        self.remote_tools_loaded = True

    def _sanitize_schema(self, schema: Dict[str, Any]):
        """Recursively removes unsupported fields from the schema for Gemini API compatibility."""
        # Fields to remove at any level
        unsupported_keys = ['minimum', 'maximum', 'example', 'additionalProperties', '$schema', 'default', 'format', 'nullable']
        for key in unsupported_keys:
            if key in schema:
                del schema[key]

        # Sanitize description fields by removing backticks, which can confuse the model.
        if 'description' in schema and isinstance(schema['description'], str):
            schema['description'] = schema['description'].replace('`', '')

        # Recurse into nested properties
        if 'properties' in schema and isinstance(schema['properties'], dict):
            for prop_name, prop_schema in list(schema['properties'].items()):
                if isinstance(prop_schema, dict):
                    self._sanitize_schema(prop_schema)

        # Recurse into array items
        if 'items' in schema and isinstance(schema['items'], dict):
            self._sanitize_schema(schema['items'])

    def get_tool_instance(self, tool_name: str) -> Optional[Any]:
        return self.tools.get(tool_name)

    def get_all_tool_definitions(self) -> List[Tool]:
        if not self.remote_tools_loaded:
            self._load_remote_tools()

        if not self.function_declarations:
            return []
        return [Tool(function_declarations=self.function_declarations)]

    def get_all_tools(self) -> Dict[str, Any]:
        """Returns all tools, loading remote ones if necessary."""
        if not self.remote_tools_loaded:
            self._load_remote_tools()
        return self.tools
