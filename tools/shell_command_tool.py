import asyncio
import json
import os
import shlex
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List

class ShellCommandTool:
    """A tool for securely executing shell commands within a chroot jail."""

    def __init__(self, chroot_dir: str):
        """
        Initialize the ShellCommandTool.

        Args:
            chroot_dir: The mandatory chroot directory. All commands will run in this directory.
        """
        if not chroot_dir:
            raise ValueError("chroot_dir cannot be empty or None for ShellCommandTool.")
        self.chroot_dir = Path(chroot_dir).resolve()
        if not self.chroot_dir.is_dir():
            print(f"[WARNING] Chroot directory {self.chroot_dir} for ShellCommandTool does not exist or is not a directory.")

        self.active_jobs: Dict[str, Any] = {}

    def get_definition(self) -> Dict[str, Any]:
        """Returns the tool definitions for the Gemini model."""
        return {
            'function_declarations': [
                {
                    'name': 'start_shell_command',
                    'description': 'Starts a shell command in the background within a secure directory. Returns a job_id.',
                    'parameters': {
                        'type': 'OBJECT',
                        'properties': {
                            'command': {'type': 'STRING', 'description': 'The shell command to execute.'},
                            'timeout': {'type': 'INTEGER', 'description': 'Timeout in seconds for the command to run.'}
                        },
                        'required': ['command']
                    }
                },
                {
                    'name': 'check_shell_command',
                    'description': 'Checks the status of a running command, returning its output and status.',
                    'parameters': {
                        'type': 'OBJECT',
                        'properties': {
                            'job_id': {'type': 'STRING', 'description': 'The job_id of the command to check.'}
                        },
                        'required': ['job_id']
                    }
                },
                {
                    'name': 'kill_shell_command',
                    'description': 'Terminates a running shell command.',
                    'parameters': {
                        'type': 'OBJECT',
                        'properties': {
                            'job_id': {'type': 'STRING', 'description': 'The job_id of the command to kill.'}
                        },
                        'required': ['job_id']
                    }
                }
            ]
        }

    async def start_shell_command(self, command: str, timeout: int = 60) -> Dict[str, Any]:
        job_id = str(uuid.uuid4())
        try:
            # SECURITY: Use shlex to split the command and avoid shell injection.
            cmd_parts = shlex.split(command)
            if not cmd_parts:
                return {"status": "error", "error": "Empty command provided."}

            proc = await asyncio.create_subprocess_exec(
                *cmd_parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.chroot_dir
            )

            async def _read_stream(stream, buffer):
                while True:
                    data = await stream.read(4096)
                    if not data:
                        break
                    buffer += data

            stdout_buffer = bytearray()
            stderr_buffer = bytearray()

            stdout_task = asyncio.create_task(_read_stream(proc.stdout, stdout_buffer))
            stderr_task = asyncio.create_task(_read_stream(proc.stderr, stderr_buffer))

            self.active_jobs[job_id] = {
                'process': proc,
                'start_time': time.time(),
                'timeout': timeout,
                'status': 'running',
                'stdout': stdout_buffer,
                'stderr': stderr_buffer,
                'stdout_task': stdout_task,
                'stderr_task': stderr_task
            }
            return {"status": "started", "job_id": job_id}
        except Exception as e:
            return {"status": "error", "error": f"Failed to start command: {e}"}

    async def check_shell_command(self, job_id: str) -> Dict[str, Any]:
        if job_id not in self.active_jobs:
            return {"status": "error", "error": "Job ID not found."}

        job = self.active_jobs[job_id]
        proc = job['process']



        # Now, update the status based on the process state.
        if proc.returncode is not None:
            # Cancel the background reader tasks
            job['stdout_task'].cancel()
            job['stderr_task'].cancel()
            # Wait for tasks to finish cancelling (optional, but good practice)
            await asyncio.gather(job['stdout_task'], job['stderr_task'], return_exceptions=True)
            job['status'] = 'completed'
            job['exit_code'] = proc.returncode
        elif time.time() - job['start_time'] > job['timeout']:
            proc.kill()
            # Cancel the background reader tasks
            job['stdout_task'].cancel()
            job['stderr_task'].cancel()
            # Wait for tasks to finish cancelling (optional, but good practice)
            await asyncio.gather(job['stdout_task'], job['stderr_task'], return_exceptions=True)
            job['status'] = 'timed_out'
            job['exit_code'] = -1 # Custom code for timeout

        return {
            "job_id": job_id,
            "status": job['status'],
            "exit_code": job.get('exit_code'),
            "stdout": job['stdout'].decode(errors='ignore'),
            "stderr": job['stderr'].decode(errors='ignore')
        }

    async def kill_shell_command(self, job_id: str) -> Dict[str, Any]:
        if job_id not in self.active_jobs:
            return {"status": "error", "error": "Job ID not found."}

        job = self.active_jobs[job_id]
        proc = job['process']

        if proc.returncode is None:
            proc.kill()
            job['stdout_task'].cancel()
            job['stderr_task'].cancel()
            await asyncio.gather(job['stdout_task'], job['stderr_task'], return_exceptions=True)
            job['status'] = 'killed'
            return {"status": "killed", "job_id": job_id}
        else:
            return {"status": "already_completed", "job_id": job_id, "exit_code": proc.returncode}
