import json
import os
from typing import Dict, Any, Optional, List

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

class FileTool:
    def __init__(self, base_path: str = None):
        """
        Initialize the FileTool.

        Args:
            base_path: Optional base path to resolve relative paths against
        """
        self.base_path = os.path.abspath(base_path) if base_path else None

    def get_definition(self) -> Dict[str, Any]:
        """Returns the tool definition for the Gemini model."""
        return {
            'function_declarations': [{
                'name': 'read_file',
                'description': 'Read contents of a file from the filesystem with optional line range.',
                'parameters': {
                    'type': 'OBJECT',
                    'properties': {
                        'file_path': {
                            'type': 'STRING',
                            'description': 'Path to the file to read. Can be absolute or relative to the base path.'
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
        # For now, get_help can reuse get_invocation_instructions.
        # It can be expanded later if more detailed, distinct help is needed.
        return self.get_invocation_instructions()

    def get_invocation_instructions(self) -> str:
        """Returns the specific instructions for how the LLM should invoke this tool."""
        return """When you need to read a file, you MUST respond with a tool call in this exact format:
/tool read_file({"file_path": "/path/to/file"})

Examples:
User: Show me the contents of config.json
You: /tool read_file({"file_path": "config.json"})

User: What's in lines 5-10 of script.py?
You: /tool read_file({"file_path": "script.py", "start_line": 5, "end_line": 10})

Important:
- The response MUST start with '/tool read_file('
- The arguments MUST be valid JSON
- The 'file_path' parameter is REQUIRED
- 'start_line' and 'end_line' are OPTIONAL
- Do NOT include any other text when you want to execute a tool"""

    def execute(self, file_path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> Dict[str, Any]:
        """
        Execute the file read operation.

        Args:
            file_path: Path to the file to read
            start_line: Optional 1-based starting line number (inclusive)
            end_line: Optional 1-based ending line number (inclusive)

        Returns:
            Dictionary containing file content and metadata
        """
        # Resolve path relative to base_path if provided
        if self.base_path and not os.path.isabs(file_path):
            file_path = os.path.join(self.base_path, file_path)

        return read_file_safely(file_path, start_line, end_line)
