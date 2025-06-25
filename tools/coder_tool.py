import os
from pathlib import Path
from typing import List, Dict, Any, Optional

from google.generativeai import GenerativeModel

from core.ai_type_definitions import AITool
from core.ai_config_manager import AIConfigManager

def run_coder_task(prompt: str, filepaths: Optional[List[str]] = None, summary: Optional[str] = None, feedback: Optional[str] = None, chroot_path: str = None, config_manager: Optional[AIConfigManager] = None) -> Dict[str, Any]:
    """
    Resolves a coding task by generating a diff.

    Args:
        prompt: The task description.
        filepaths: Optional list of file paths for context.
        summary: A summary of what has been done so far.
        feedback: Feedback on previous execution attempts.
        chroot_path: The root directory for file operations.
        config_manager: The application's configuration manager.

    Returns:
        A dictionary with 'success' (boolean) and 'output' (string) keys.
    """
    if not chroot_path or not config_manager:
        return {"success": False, "output": "Security context (chroot_path) or config_manager not provided."}

    # 1. Read file contents
    file_contents = []
    chroot_p = Path(chroot_path).resolve()
    if filepaths:
        for filepath in filepaths:
            try:
                full_path_p = (chroot_p / filepath).resolve()
                if not full_path_p.is_relative_to(chroot_p):
                    return {"success": False, "output": f"Access denied for filepath: {filepath}"}
                
                if full_path_p.exists() and full_path_p.is_file():
                    content = full_path_p.read_text()
                    file_contents.append(f"## File: {filepath}\n\n```\n{content}\n```")
                else:
                    file_contents.append(f"## File: {filepath}\n\n(File does not exist or is not a regular file)")
            except Exception as e:
                return {"success": False, "output": f"Error reading file {filepath}: {e}"}

    # 2. Construct the prompts for the sub-agent
    coder_system_prompt = ( """
        You are an expert software developer. Your task is to solve a coding problem by providing a diff in the unified format.
        - Analyze the user's request, the provided file contents, and any other context.
        - If a file exists, the diff should modify the existing content. Do not generate a diff that replaces the entire file. Integrate your changes with the existing code.
        - Generate a single diff that correctly implements the required changes.
        - The diff must be directly applicable with the `patch` command.
        - Do NOT include any explanations, comments, or any text other than the diff itself.
        - Ensure the file paths in the diff are relative to the project root.
        - For new files, use `/dev/null` for the 'from' part of the diff.
        - For deleted files, use `/dev/null` for the 'to' part.
        - The diff for each file should start with `--- a/path/to/old_file` and `+++ b/path/to/new_file`.
        """
    )

    user_prompt_parts = [
        "# Coding Task", prompt,
        "\n# Work Summary", summary or "No summary provided.",
        "\n# Previous Feedback", feedback or "No feedback provided."
    ]

    if file_contents:
        user_prompt_parts.append("\n# Relevant File Contents\n---")
        user_prompt_parts.extend(file_contents)
        user_prompt_parts.append("\n---")
    
    user_prompt_parts.append("\nNow, generate the diff to accomplish the task.")
    final_user_prompt = "\n".join(user_prompt_parts)

    # 3. Call the model
    try:
        model = GenerativeModel(
            model_name=config_manager.model_name,
            safety_settings=config_manager.safety_settings,
            system_instruction=coder_system_prompt
        )
        response = model.generate_content(final_user_prompt)
        
        diff_output = response.text.strip()
        # Basic validation to ensure it looks like a diff
        if not diff_output.startswith('--- a/'):
            return {"success": False, "output": f"The model did not produce a valid diff. Output:\n{diff_output}"}

        return {"success": True, "output": diff_output}

    except Exception as e:
        return {"success": False, "output": f"An unexpected error occurred during AI generation: {e}"}


coder_tool = AITool(
    name="coder_task",
    description="Resolves a coding task by generating a diff based on a prompt and context.",
    func=run_coder_task,
    parameters={
        "type": "OBJECT",
        "properties": {
            "prompt": {"type": "STRING", "description": "The detailed description of the coding task."},
            "filepaths": {
                "type": "ARRAY",
                "description": "An optional list of filepaths to provide context for the task.",
                "items": {"type": "STRING"}
            },
            "summary": {"type": "STRING", "description": "A summary of the work already completed."},
            "feedback": {"type": "STRING", "description": "Feedback from any previous execution of the task."}
        },
        "required": ["prompt"]
    }
)
