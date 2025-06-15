import os
import json
import datetime
from typing import Dict, Any, Optional
from pathlib import Path

class FileFullWriteTool:
    def __init__(self, chroot_dir: str):
        """
        Initialize the FileFullWriteTool.

        Args:
            chroot_dir: The mandatory chroot directory. All file paths will be relative to this.
        """
        if not chroot_dir:
            raise ValueError("chroot_dir cannot be empty or None for FileFullWriteTool.")
        self.chroot_dir = Path(chroot_dir).resolve()
        if not self.chroot_dir.is_dir():
            # Or raise an error, depending on desired behavior if chroot isn't pre-existing
            print(f"[WARNING] Chroot directory {self.chroot_dir} for FileFullWriteTool does not exist or is not a directory.")

    def get_definition(self) -> Dict[str, Any]:
        """Returns the tool definition for the Gemini model."""
        return {
            'function_declarations': [{
                'name': 'write_file_full',
                'description': 'Writes content to a specified file within a secure directory (chroot jail). Can override existing files or preserve them. Attempts to access files outside this directory will be denied.',
                'parameters': {
                    'type': 'OBJECT',
                    'properties': {
                        'file_path': {
                            'type': 'STRING',
                            'description': 'Path to the file to write, relative to the configured secure chroot directory. Do not use absolute paths or try to escape the chroot (e.g., with `../`).'
                        },
                        'file_contents': {
                            'type': 'STRING',
                            'description': 'The content to write to the file.'
                        },
                        'override': {
                            'type': 'BOOLEAN',
                            'description': 'If true, allows overwriting an existing file. Defaults to false. If preserve_original is true, this is effectively ignored for the preservation step.'
                        },
                        'preserve_original': {
                            'type': 'BOOLEAN',
                            'description': 'If true and the file exists, renames the original file with a timestamp (e.g., file.ext.YYYYMMDDHHMMSS.bak) before writing. Defaults to false.'
                        }
                    },
                    'required': ['file_path', 'file_contents']
                }
            }]
        }

    def get_summary(self) -> str:
        """Returns a brief summary of the tool's capabilities."""
        return "Writes content to a file within a chroot jail, with options to override or preserve existing files."

    def get_help(self) -> str:
        """Returns detailed help information for the tool."""
        return self.get_invocation_instructions() # Updated to reflect chroot

    def get_invocation_instructions(self) -> str:
        """Returns the specific instructions for how the LLM should invoke this tool."""
        return """When you need to write content to a file, you MUST respond with a tool call in this exact format:
/tool write_file_full({"file_path": "relative/path/to/your/file.txt", "file_contents": "This is the content...", "override": false, "preserve_original": true})

Important:
- The 'file_path' MUST be relative to a pre-configured secure directory (chroot jail).
- Do NOT use absolute paths (e.g., /home/user/file.txt).
- Do NOT attempt to access files outside this secure directory (e.g., using '../' to go up levels).
- 'file_path' and 'file_contents' are REQUIRED.
- 'override' (default: false): Set to true to overwrite an existing file if 'preserve_original' is false.
- 'preserve_original' (default: false): Set to true to rename an existing file with a timestamp before writing.
- If the file does not exist, it will be created (within the chroot jail).
- If the file exists, 'preserve_original' takes precedence. If true, the original is renamed.
- If 'preserve_original' is false and 'override' is false (default), an error occurs if the file exists.
- If 'preserve_original' is false and 'override' is true, the existing file is overwritten.
"""

    def execute(self, file_path: str, file_contents: str, override: Optional[bool] = False, preserve_original: Optional[bool] = False) -> Dict[str, Any]:
        """
        Execute the file write operation within the chroot jail.

        Args:
            file_path: Path to the file to write, relative to the chroot directory.
            file_contents: The content to write to the file.
            override: If true, allows overwriting an existing file if preserve_original is false.
            preserve_original: If true and the file exists, renames the original before writing.

        Returns:
            Dictionary containing the operation status.
        """
        if not self.chroot_dir or not self.chroot_dir.is_dir():
            return {
                "file_path": file_path,
                "status": "error",
                "message": "Chroot directory not configured or is invalid for this tool."
            }

        try:
            # Treat file_path as relative to chroot_dir. Path.resolve() makes it absolute and canonical.
            resolved_file_path_obj = (self.chroot_dir / file_path).resolve()

            # Security check: Ensure the resolved path is strictly within the chroot_dir.
            if not resolved_file_path_obj.is_relative_to(self.chroot_dir):
                return {
                    "file_path": file_path,
                    "status": "error",
                    "message": "Access denied: Path is outside the allowed directory (chroot jail)."
                }
            resolved_file_path = str(resolved_file_path_obj) # Convert to string for os functions
        except Exception as e: # Catch potential errors during path resolution
            return {
                "file_path": file_path,
                "status": "error",
                "message": f"Invalid file path for chroot resolution: {str(e)}"
            }
        
        # Ensure the parent directory exists within the chroot jail
        try:
            # os.makedirs needs a string path
            parent_dir = os.path.dirname(resolved_file_path)
            if parent_dir: # Ensure parent_dir is not empty (e.g. for top-level files in chroot)
                 # We must also ensure the parent_dir itself is within the chroot
                if not Path(parent_dir).resolve().is_relative_to(self.chroot_dir):
                    return {
                        "file_path": file_path,
                        "status": "error",
                        "message": "Access denied: Cannot create directory outside chroot jail."
                    }
                os.makedirs(parent_dir, exist_ok=True)
        except Exception as e:
            return {
                "file_path": resolved_file_path,
                "status": "error",
                "message": f"Error creating directory for file: {str(e)}"
            }

        original_path_preserved = None
        file_exists = os.path.exists(resolved_file_path)

        if file_exists:
            if preserve_original:
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                base, ext = os.path.splitext(resolved_file_path)
                backup_path = f"{base}{ext}.{timestamp}.bak"
                try:
                    os.rename(resolved_file_path, backup_path)
                    original_path_preserved = backup_path
                    file_exists = False # Treat as if file doesn't exist for the write operation now
                except Exception as e:
                    return {
                        "file_path": resolved_file_path,
                        "status": "error",
                        "message": f"Error renaming original file to {backup_path}: {str(e)}"
                    }
            elif not override:
                return {
                    "file_path": resolved_file_path,
                    "status": "error",
                    "message": "File exists and override is false. Set override to true or preserve_original to true to proceed."
                }

        try:
            with open(resolved_file_path, 'w', encoding='utf-8') as f:
                f.write(file_contents)
            
            result = {
                "file_path": file_path, # Report the relative path as requested by user
                "resolved_path": resolved_file_path, # For internal reference
                "status": "success",
                "message": "File written successfully."
            }
            if original_path_preserved:
                result["original_preserved_as"] = original_path_preserved
            return result

        except PermissionError:
            return {
                "file_path": file_path,
                "resolved_path": resolved_file_path,
                "status": "error",
                "message": "Permission denied."
            }
        except Exception as e:
            return {
                "file_path": file_path,
                "resolved_path": resolved_file_path,
                "status": "error",
                "message": f"Error writing file: {str(e)}"
            }

# Example usage (for testing):
if __name__ == '__main__':
    # Ensure the test chroot directory exists
    test_chroot_path = './test_files_chroot'
    os.makedirs(test_chroot_path, exist_ok=True)
    writer_tool = FileFullWriteTool(chroot_dir=test_chroot_path)

    # Adjust example file paths to be relative to the new chroot_dir for testing
    # Example: file_path="new_file.txt" will be test_files_chroot/new_file.txt

    # Test 1: Create a new file
    print("Test 1: Create new file")
    res1 = writer_tool.execute(file_path="new_file.txt", file_contents="Hello from new_file.txt")
    print(json.dumps(res1, indent=2))
    if res1['status'] == 'success' and os.path.exists(os.path.join(test_chroot_path, 'new_file.txt')):
        with open(os.path.join(test_chroot_path, 'new_file.txt'), 'r') as f:
            print(f"Content: {f.read()}")
    print("-"*20)

    # Test 2: Try to overwrite without override/preserve (should fail)
    print("Test 2: Overwrite without flags (fail)")
    res2 = writer_tool.execute(file_path="new_file.txt", file_contents="Attempting overwrite (fail)")
    print(json.dumps(res2, indent=2))
    print("-"*20)

    # Test 3: Overwrite with override=True
    print("Test 3: Overwrite with override=True")
    res3 = writer_tool.execute(file_path="new_file.txt", file_contents="Overwritten content!", override=True)
    print(json.dumps(res3, indent=2))
    if res3['status'] == 'success':
        with open(os.path.join(test_chroot_path, 'new_file.txt'), 'r') as f:
            print(f"Content: {f.read()}")
    print("-"*20)

    # Test 4: Write with preserve_original=True (original should be renamed)
    print("Test 4: Write with preserve_original=True")
    res4 = writer_tool.execute(file_path="new_file.txt", file_contents="New content, original preserved.", preserve_original=True)
    print(json.dumps(res4, indent=2))
    if res4['status'] == 'success':
        with open(os.path.join(test_chroot_path, 'new_file.txt'), 'r') as f:
            print(f"New Content: {f.read()}")
        if res4.get('original_preserved_as') and os.path.exists(res4['original_preserved_as']):
            print(f"Original preserved at: {res4['original_preserved_as']}")
            with open(res4['original_preserved_as'], 'r') as f:
                print(f"Preserved Content: {f.read()}")
    print("-"*20)

    # Test 5: Write to a new file with preserve_original=True (should just write)
    print("Test 5: Write new file with preserve_original=True")
    res5 = writer_tool.execute(file_path="another_new_file.txt", file_contents="Content for another_new_file.", preserve_original=True)
    print(json.dumps(res5, indent=2))
    if res5['status'] == 'success' and os.path.exists(os.path.join(test_chroot_path, 'another_new_file.txt')):
        with open(os.path.join(test_chroot_path, 'another_new_file.txt'), 'r') as f:
            print(f"Content: {f.read()}")
    print("-"*20)

    # Test 6: Write to a path requiring directory creation
    print("Test 6: Write to new subdirectory")
    res6 = writer_tool.execute(file_path="subdir/deep_file.txt", file_contents="Hello from deep_file.txt")
    print(json.dumps(res6, indent=2))
    if res6['status'] == 'success' and os.path.exists(os.path.join(test_chroot_path, 'subdir/deep_file.txt')):
        with open(os.path.join(test_chroot_path, 'subdir/deep_file.txt'), 'r') as f:
            print(f"Content: {f.read()}")
    print("-"*20)

    # Cleanup test files (optional)
    # import shutil
    # if os.path.exists(test_chroot_path):
    #     shutil.rmtree(test_chroot_path)
    # print(f"Cleaned up {test_chroot_path} directory.")
