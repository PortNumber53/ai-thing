import os
import subprocess
from pathlib import Path
from typing import List, Dict, Any
from core.ai_type_definitions import AITool

def apply_file_patches(patches: List[Dict[str, str]], chroot_path: str = None) -> Dict[str, Any]:
    """
    Applies a series of diff patches to files using the 'patch' command.
    The filepaths are relative to the chroot path.

    Args:
        patches: A list of dictionaries, where each dictionary contains:
                 'filepath': The relative path to the file to be patched.
                 'diff': The diff content to apply.
        chroot_path: The root directory to which filepaths are relative.

    Returns:
        A dictionary with 'success' (boolean) and 'output' (string) keys.
    """
    if not chroot_path:
        return {"success": False, "output": "Security context not provided (chroot_path is missing)."}

    outputs = []
    any_failures = False
    for patch_info in patches:
        filepath = patch_info.get("filepath")
        diff_content = patch_info.get("diff")

        if not filepath or not diff_content:
            outputs.append("Skipping a patch: Each patch object must contain 'filepath' and 'diff' keys.")
            any_failures = True
            continue

        try:
            chroot_p = Path(chroot_path).resolve()
            full_path_p = (chroot_p / filepath).resolve()

            if not full_path_p.is_relative_to(chroot_p):
                outputs.append(f"Skipping {filepath}: Access denied (path is outside the allowed directory).")
                any_failures = True
                continue

            full_path = str(full_path_p)

            dir_name = os.path.dirname(full_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)

        except Exception as e:
            outputs.append(f"Error processing file path or creating directory for {filepath}: {e}")
            any_failures = True
            continue

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
                outputs.append(error_output)
                any_failures = True
            else:
                outputs.append(result.stdout)

        except FileNotFoundError:
            outputs.append("The 'patch' command was not found. Please ensure it is installed and in your PATH. Aborting.")
            any_failures = True
            break
        except Exception as e:
            outputs.append(f"An unexpected error occurred while patching {filepath}: {e}")
            any_failures = True

    return {"success": not any_failures, "output": "\n".join(outputs)}

file_patch_tool = AITool(
    name="file_patch",
    description="Applies a diff patch to one or more files using the 'patch' command.",
    func=apply_file_patches,
    parameters={
        "type": "OBJECT",
        "properties": {
            "patches": {
                "type": "ARRAY",
                "description": "A list of patch objects to apply.",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "filepath": {"type": "STRING", "description": "The relative path to the file to be patched."},
                        "diff": {"type": "STRING", "description": "The diff content to apply."}
                    },
                    "required": ["filepath", "diff"]
                }
            }
        },
        "required": ["patches"]
    }
)
