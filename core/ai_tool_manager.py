import importlib
import inspect
import functools
import traceback
import atexit
from pathlib import Path
from typing import Dict, Any, List, Optional

from .mcp_client import MCPClient
from .ai_type_definitions import AITool


class RemoteToolExecutor:
    """A proxy for executing a tool on a remote MCP server."""
    def __init__(self, client: MCPClient, tool_name: str):
        self.client = client
        self.tool_name = tool_name

    def execute(self, **kwargs):
        """Executes the remote tool by calling the client."""
        print(f"[INFO] Executing remote tool '{self.tool_name}' via MCP client for '{self.client.server_name}'.")
        return self.client.execute_tool(self.tool_name, kwargs)


class AIToolManager:
    def __init__(self, chroot_dir: Optional[Path], model_name: str, mcp_server_configs: Optional[Dict[str, Any]] = None, brave_api_key: Optional[str] = None):
        self.chroot_dir = chroot_dir
        self.model_name = model_name
        self.brave_api_key = brave_api_key
        self.tools: Dict[str, Any] = {}  # Stores tool_name -> tool_instance or callable
        self.function_declarations: List[Dict[str, Any]] = []  # Stores individual function declarations
        self.mcp_clients: Dict[str, MCPClient] = {}

        self._load_local_tools()
        self._initialize_mcp_clients(mcp_server_configs)

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
                                # Create a closure to capture the current tool_func
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

                        if name in ['FileReadTool', 'FileFullWriteTool']:
                            if 'chroot_dir' in init_params:
                                if self.chroot_dir:
                                    tool_instance_args['chroot_dir'] = self.chroot_dir
                                else:
                                    print(f"[CRITICAL_ERROR] Chroot directory not configured for {name} but it's required. Skipping tool loading.")
                                    continue
                            else:
                                print(f"[WARNING] File tool {name} does not accept 'chroot_dir' in __init__. Update tool to support chroot.")
                        elif 'base_path' in init_params:
                            print(f"[INFO] Tool {name} uses 'base_path', setting to CWD. Consider updating to 'chroot_dir' if it performs file ops.")
                            tool_instance_args['base_path'] = str(Path.cwd())

                        if name == 'WebSearchTool':
                            if 'brave_api_key' in init_params:
                                if self.brave_api_key:
                                    tool_instance_args['brave_api_key'] = self.brave_api_key
                                else:
                                    print(f"[WARNING] WebSearchTool requires a Brave API key, but it was not provided. Skipping tool.")
                                    continue

                        tool_instance = obj(**tool_instance_args)
                        tool_def = tool_instance.get_definition()

                        if tool_def and tool_def.get('function_declarations'):
                            for declaration in tool_def['function_declarations']:
                                func_name = declaration.get('name')
                                if func_name:
                                    self.tools[func_name] = tool_instance
                                    self.function_declarations.append(declaration)
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

    def get_tool_instance(self, tool_name: str) -> Optional[Any]:
        return self.tools.get(tool_name)

    def get_all_tool_definitions(self) -> Optional[List[Any]]:
        """Returns a list containing a single Tool object, if any functions are declared."""
        if not self.function_declarations:
            return None
        return [{'function_declarations': self.function_declarations}]

    def get_all_tools(self) -> Dict[str, Any]:
        return self.tools

    def _initialize_mcp_clients(self, mcp_server_configs: Optional[Dict[str, Any]]):
        if not mcp_server_configs:
            return

        print(f"[INFO] Initializing {len(mcp_server_configs)} MCP client(s)...")
        for server_name, config in mcp_server_configs.items():
            try:
                client = MCPClient(server_name, config)
                # Authenticate using the new direct authentication flow
                if client.authenticate():
                    self.mcp_clients[server_name] = client
                    remote_tools = client.list_tools()
                    for tool_def in remote_tools:
                        tool_name = tool_def.get('name')
                        if not tool_name:
                            print(f"[WARNING] Remote tool from '{server_name}' is missing a name. Skipping.")
                            continue

                        declaration = {
                            "name": tool_name,
                            "description": tool_def.get('description', ''),
                            "parameters": tool_def.get('inputSchema', {'type': 'object', 'properties': {}})
                        }
                        self.function_declarations.append(declaration)

                        if tool_name in self.tools:
                            print(f"[WARNING] Tool name collision: A tool named '{tool_name}' is already loaded. The one from MCP server '{server_name}' will overwrite it.")
                        self.tools[tool_name] = RemoteToolExecutor(client, tool_name)
                        print(f"[INFO] Loaded remote tool: {tool_name} from MCP server '{server_name}'")
                else:
                    print(f"[ERROR] Failed to authenticate with MCP server '{server_name}'. It will be unavailable.")
            except ValueError as e:
                print(f"[ERROR] Failed to initialize MCP client for '{server_name}': {e}")
            except Exception as e:
                print(f"[ERROR] An unexpected error occurred while setting up MCP client for '{server_name}': {e}")
