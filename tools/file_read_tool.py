import json
import os
from typing import Dict, Any, Optional, List
from pathlib import Path

def read_file_safely(file_path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> Dict[str, Any]:
    """
    Safely read a file with optional line range.

    Args:
        file_path: Path to the file to read
        start_line: Optional 1-based starting line number (inclusive)
        end_line: Optional 1-based ending line number (inclusive)

    Returns:
        Dictionary containing file content and metadata
    """
    try:
        # Validate file path
        if not os.path.exists(file_path):
            return {
                "file_path": file_path,
                "error": "File not found",
                "exists": False
            }

        if not os.path.isfile(file_path):
            return {
                "file_path": file_path,
                "error": "Path is not a file",
                "exists": True,
                "is_file": False
            }

        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            total_lines = len(lines)

            # Handle line range
            if start_line is not None or end_line is not None:
                start = max(0, (start_line or 1) - 1)  # Convert to 0-based
                end = min(total_lines, end_line) if end_line is not None else total_lines

                if start >= end or start >= total_lines:
                    return {
                        "file_path": file_path,
                        "error": "Invalid line range",
                        "total_lines": total_lines,
                        "requested_range": {"start": start_line, "end": end_line}
                    }

                content = ''.join(lines[start:end])
                line_range = {"start": start + 1, "end": end, "total": total_lines}
            else:
                content = ''.join(lines)
                line_range = {"start": 1, "end": total_lines, "total": total_lines}

        # Get file stats
        stats = os.stat(file_path)

        return {
            "file_path": file_path,
            "content": content,
            "line_range": line_range,
            "file_info": {
                "size_bytes": stats.st_size,
                "modified_time": stats.st_mtime,
                "is_readable": os.access(file_path, os.R_OK)
            },
            "exists": True,
            "is_file": True
        }

    except PermissionError:
        return {
            "file_path": file_path,
            "error": "Permission denied",
            "exists": True,
            "is_file": True
        }
    except Exception as e:
        return {
            "file_path": file_path,
            "error": f"Error reading file: {str(e)}",
            "exists": os.path.exists(file_path) if 'file_path' in locals() else None
        }

class FileReadTool:
    def __init__(self, chroot_dir: str):
        """
        Initialize the FileReadTool.

        Args:
            chroot_dir: The mandatory chroot directory. All file paths will be relative to this.
        """
        if not chroot_dir:
            raise ValueError("chroot_dir cannot be empty or None for FileReadTool.")
        self.chroot_dir = Path(chroot_dir).resolve()
        if not self.chroot_dir.is_dir():
            # Or raise an error, depending on desired behavior if chroot isn't pre-existing
            print(f"[WARNING] Chroot directory {self.chroot_dir} for FileReadTool does not exist or is not a directory.")

    def get_definition(self) -> Dict[str, Any]:
        """Returns the tool definition for the Gemini model."""
        return {
            'function_declarations': [{
                'name': 'read_file',
                'description': 'Reads contents of a file from a secure directory (chroot jail) with optional line range. Attempts to access files outside this directory will be denied.',
                'parameters': {
                    'type': 'OBJECT',
                    'properties': {
                        'file_path': {
                            'type': 'STRING',
                            'description': 'Path to the file to read, relative to the configured secure chroot directory. Do not use absolute paths or try to escape the chroot (e.g., with `../`).'
                        },
                        'start_line': {
                            'type': 'INTEGER',
                            'description': 'Optional 1-based starting line number (inclusive). If not provided, starts from the beginning.'
                        },
                        'end_line': {
                            'type': 'INTEGER',
                            'description': 'Optional 1-based ending line number (inclusive). If not provided, reads to the end.'
                        }
                    },
                    'required': ['file_path']
                }
            }]
        }

    def get_summary(self) -> str:
        """Returns a brief summary of the tool's capabilities."""
        return "Reads the content of a specified file, optionally within a given line range."

    def get_help(self) -> str:
        """Returns detailed help information for the tool."""
        return self.get_invocation_instructions() # Updated to reflect chroot

    def get_invocation_instructions(self) -> str:
        """Returns the specific instructions for how the LLM should invoke this tool."""
        return f"""When you need to read a file, you MUST respond with a tool call in this exact format:
/tool read_file({{"file_path": "path/to/file.txt"}})

The 'file_path' can be:
1. Relative to the secure working directory (e.g., "my_notes.txt", "project_alpha/data.csv").
2. An absolute path (e.g., "/home/grimlock/tmp/important_data.txt"), but ONLY if this path resolves to a location *inside* the secure working directory ({self.chroot_dir}). Access to paths outside this secure directory will be denied.

Examples:
User: Show me the contents of config.json
You: /tool read_file({{"file_path": "config.json"}})

User: Read the file at {self.chroot_dir}/locations.txt
You: /tool read_file({{"file_path": "{self.chroot_dir}/locations.txt"}})

User: What's in lines 5-10 of script.py?
You: /tool read_file({{"file_path": "script.py", "start_line": 5, "end_line": 10}})

Important:
- All file access is restricted to the secure directory: {self.chroot_dir}
- Do NOT attempt to access files outside this secure directory (e.g., using '../' to go to a parent directory of the secure root, or specifying an absolute path outside it).
- The response MUST start with '/tool read_file('
- The arguments MUST be valid JSON.
- The 'file_path' parameter is REQUIRED.
- 'start_line' and 'end_line' are OPTIONAL.
- Do NOT include any other text when you want to execute a tool."""

    def execute(self, file_path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> Dict[str, Any]:
        """
        Execute the file read operation within the chroot jail.

        Args:
            file_path: Path to the file to read, relative to the chroot directory.
            start_line: Optional 1-based starting line number (inclusive).
            end_line: Optional 1-based ending line number (inclusive).

        Returns:
            Dictionary containing file content and metadata or an error message.
        """
        if not self.chroot_dir or not self.chroot_dir.is_dir():
            return {
                "file_path": file_path,
                "error": "Chroot directory not configured or is invalid for this tool."
            }

        try:
            # Treat file_path as relative to chroot_dir. Path.resolve() makes it absolute and canonical.
            # This also helps prevent issues with '..' if not handled by is_relative_to correctly, though is_relative_to should be robust.
            resolved_path = (self.chroot_dir / file_path).resolve()

            # Security check: Ensure the resolved path is strictly within the chroot_dir.
            # This check is crucial to prevent path traversal attacks (e.g., ../../etc/passwd).
            if not resolved_path.is_relative_to(self.chroot_dir):
                return {
                    "file_path": file_path,
                    "error": "Access denied: Path is outside the allowed directory (chroot jail)."
                }
        except Exception as e: # Catch potential errors during path resolution (e.g., malformed file_path string)
            return {
                "file_path": file_path,
                "error": f"Invalid file path for chroot resolution: {str(e)}"
            }
        
        # Pass the string representation of the validated, absolute path to the actual file reader
        return read_file_safely(str(resolved_path), start_line, end_line)
