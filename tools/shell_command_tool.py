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
            self.active_jobs[job_id] = {
                'process': proc,
                'start_time': time.time(),
                'timeout': timeout,
                'status': 'running',
                'stdout': bytearray(),
                'stderr': bytearray()
            }
            return {"status": "started", "job_id": job_id}
        except Exception as e:
            return {"status": "error", "error": f"Failed to start command: {e}"}

    async def check_shell_command(self, job_id: str) -> Dict[str, Any]:
        if job_id not in self.active_jobs:
            return {"status": "error", "error": "Job ID not found."}

        job = self.active_jobs[job_id]
        proc = job['process']

        # If the process is still running, try to read partial output from streams.
        if proc.returncode is None:
            try:
                # Read up to 4KB from stdout with a very small timeout to avoid blocking.
                stdout_data = await asyncio.wait_for(proc.stdout.read(4096), timeout=0.01)
                job['stdout'] += stdout_data
            except asyncio.TimeoutError:
                pass  # No new output, which is fine.
            try:
                # Read up to 4KB from stderr.
                stderr_data = await asyncio.wait_for(proc.stderr.read(4096), timeout=0.01)
                job['stderr'] += stderr_data
            except asyncio.TimeoutError:
                pass  # No new output, which is fine.

        # Now, update the status based on the process state.
        if proc.returncode is not None:
            # Process has finished. Do one final communicate() call to drain the streams.
            if not job.get('final_read_done'):
                stdout, stderr = await proc.communicate()
                job['stdout'] += stdout
                job['stderr'] += stderr
                job['final_read_done'] = True
            job['status'] = 'completed'
            job['exit_code'] = proc.returncode
        elif time.time() - job['start_time'] > job['timeout']:
            proc.kill()
            # After killing, get all remaining output.
            stdout, stderr = await proc.communicate()
            job['stdout'] += stdout
            job['stderr'] += stderr
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
            job['status'] = 'killed'
            return {"status": "killed", "job_id": job_id}
        else:
            return {"status": "already_completed", "job_id": job_id, "exit_code": proc.returncode}
