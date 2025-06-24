import os
import subprocess
from typing import List, Dict, Any
from core.ai_type_definitions import AITool

def apply_file_patch(filepath: str, diff_content: str, chroot_path: str = None) -> Dict[str, Any]:
    """
    Applies a single diff patch to a file using the 'patch' command.
    The filepath is relative to the chroot path.

    Args:
        filepath: The relative path to the file to be patched.
        diff_content: The diff content to apply.
        chroot_path: The root directory to which filepaths are relative.

    Returns:
        A dictionary with 'success' (boolean) and 'output' (string) keys.
    """
    if not filepath or not diff_content:
        return {"success": False, "output": "'filepath' and 'diff_content' are required."}

    full_path = os.path.join(chroot_path, filepath) if chroot_path else filepath

    # Ensure the directory exists, as 'patch' may not create it.
    try:
        dir_name = os.path.dirname(full_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
    except Exception as e:
        return {"success": False, "output": f"Error creating directory for {filepath}: {e}"}

    command = ['patch', full_path]
    try:
        result = subprocess.run(
            command,
            input=diff_content,
            text=True,
            capture_output=True,
            check=False  # Manually check the return code
        )

        if result.returncode != 0:
            error_output = f"Failed to apply patch to {filepath}.\n"
            error_output += f"STDOUT:\n{result.stdout}\n"
            error_output += f"STDERR:\n{result.stderr}\n"
            return {"success": False, "output": error_output}
        
        return {"success": True, "output": result.stdout}

    except FileNotFoundError:
        return {"success": False, "output": "The 'patch' command was not found. Please ensure it is installed and in your PATH."}
    except Exception as e:
        return {"success": False, "output": f"An unexpected error occurred while patching {filepath}: {e}"}

file_patch_tool = AITool(
    name="file_patch",
    description="Applies a single diff patch to a file using the 'patch' command.",
    func=apply_file_patch,
    parameters={
        "type": "OBJECT",
        "properties": {
            "filepath": {
                "type": "STRING",
                "description": "The relative path to the file to be patched."
            },
            "diff_content": {
                "type": "STRING",
                "description": "The diff content to apply."
            }
        },
        "required": ["filepath", "diff_content"]
    }
)
