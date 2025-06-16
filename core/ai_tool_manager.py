import importlib
import inspect
import traceback
from pathlib import Path
from typing import Dict, Any, List, Optional

class AIToolManager:
    def __init__(self, chroot_dir: Optional[Path], model_name: str):
        self.chroot_dir = chroot_dir
        self.model_name = model_name
        self.tools: Dict[str, Any] = {}  # Stores tool_name -> tool_instance
        self.tool_definitions: List[Any] = []  # Stores raw tool definitions for Gemini

        self._load_local_tools()

    def _load_local_tools(self):
        """Dynamically load tools from the 'tools' subdirectory."""
        # Assumes this file (ai_tool_manager.py) is in the project root alongside the 'tools' directory.
        tools_dir = Path(__file__).parent.parent / "tools"
        if not tools_dir.is_dir():
            print(f"[WARNING] Tools directory not found: {tools_dir}")
            return

        for tool_file in tools_dir.glob("[!_]*.py"):  # Ignore files starting with _
            module_name = f"tools.{tool_file.stem}"
            try:
                module = importlib.import_module(module_name)
                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and obj.__module__ == module_name and hasattr(obj, 'get_definition') and hasattr(obj, 'execute'):
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

                        tool_instance = obj(**tool_instance_args)
                        tool_def = tool_instance.get_definition()

                        if tool_def and tool_def.get('function_declarations'):
                            func_name = tool_def['function_declarations'][0].get('name')
                            if func_name:
                                self.tools[func_name] = tool_instance
                                self.tool_definitions.append(tool_def)
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

    def get_all_tool_definitions(self) -> List[Any]:
        return self.tool_definitions

    def get_all_tools(self) -> Dict[str, Any]:
        return self.tools
