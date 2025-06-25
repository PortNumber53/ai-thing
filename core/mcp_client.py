import json
import requests
import uuid
import select
import subprocess
import sys
import threading
import atexit
import os
import signal
import time
import webbrowser
import hashlib
import base64
from urllib.parse import urlencode, urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Any, List, Optional
from core.ai_config_manager import AIConfigManager

class MCPClient:
    """
    Manages a connection to an MCP server.
    It can connect to a remote server via HTTP or
    start a local proxy and communicate via stdio.
    """
    def __init__(self, server_name: str, config: Dict[str, Any], config_manager: AIConfigManager):
        self.server_name = server_name
        self.config = config
        self.command = config.get('command')
        self.url = config.get('url')
        self.config_manager = config_manager
        self.process: Optional[subprocess.Popen] = None
        self.tools: List[Dict[str, Any]] = []
        self._lock = threading.Lock() # Lock for thread-safe stdio access
        self.access_token: Optional[str] = None
        self.auth_code: Optional[str] = None
        self.received_state: Optional[str] = None

        self._register_client_if_needed()
        self._perform_oauth_if_needed()

        if self.command:
            self._start_stdio_proxy()
        elif not self.url:
            raise ValueError(f"MCP configuration for '{server_name}' is missing 'url' or 'command'.")

    def _register_client_if_needed(self):
        """Registers this client with the MCP server if not already registered."""
        if self.server_name != 'jira-thing':
            return

        client_id = self.config_manager.get_mcp_client_id(self.server_name)
        if client_id:
            print(f"[INFO] Client for '{self.server_name}' is already registered. Using client_id: {client_id}", flush=True)
            if 'args' in self.config and '--client-id' not in self.config['args']:
                 self.config['args'].extend(['--client-id', client_id])
            return

        print(f"[INFO] Client for '{self.server_name}' not registered. Attempting registration...", flush=True)

        base_url = ""
        if 'args' in self.config and len(self.config['args']) > 1:
            sse_url = self.config['args'][1]
            if sse_url.endswith('/sse'):
                base_url = sse_url[:-4]

        if not base_url:
            print(f"[ERROR] Could not determine base URL for '{self.server_name}' registration from args: {self.config.get('args')}", flush=True)
            return

        registration_url = f"{base_url}/register"
        payload = {
            "client_name": "ai-thing Python Client",
            "software_id": "ai-thing",
            "software_version": "0.1.0",
            "redirect_uris": ["http://127.0.0.1:8080/"]
        }

        try:
            print(f"[INFO] Registering client with '{self.server_name}' at {registration_url}", flush=True)
            response = requests.post(registration_url, json=payload, timeout=15)
            print(f"--- Raw registration response for '{self.server_name}' ---", flush=True)
            print(response.text)
            print("-----------------------------------------------------", flush=True)
            response.raise_for_status()

            response_data = response.json()
            if 'client_id' in response_data:
                new_client_id = response_data['client_id']
                self.config_manager.set_mcp_client_id(self.server_name, new_client_id)
                if 'args' in self.config:
                    self.config['args'].extend(['--client-id', new_client_id])

                if 'client_secret' in response_data:
                    client_secret = response_data['client_secret']
                    self.config_manager.set_mcp_client_secret(self.server_name, client_secret)
                    print(f"[INFO] Successfully registered and saved client_secret for '{self.server_name}'.", flush=True)
            else:
                print(f"[ERROR] Registration response for '{self.server_name}' did not contain a 'client_id'.", flush=True)

        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Failed to register client for '{self.server_name}': {e}", flush=True)
        except json.JSONDecodeError:
            print(f"[ERROR] Failed to decode JSON from registration response for '{self.server_name}'.", flush=True)

    def _get_base_url(self) -> str | None:
        """Determines the base URL for the MCP server from its configuration."""
        if self.url:
            # If a direct URL is provided, derive base URL from it.
            parsed_url = urlparse(self.url)
            return f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        if 'args' in self.config and len(self.config['args']) > 1:
            sse_url = self.config['args'][1]
            if sse_url.endswith('/sse'):
                return sse_url[:-4]
        
        print(f"[ERROR] Could not determine base URL for '{self.server_name}' from config: {self.config}", flush=True)
        return None

    def _perform_oauth_if_needed(self):
        """Checks for an access token and initiates OAuth flow if needed."""
        if self.server_name != 'jira-thing':
            return

        token = self.config_manager.get_mcp_access_token(self.server_name)
        if token:
            print(f"[INFO] Using existing access token for '{self.server_name}'.", flush=True)
            self.access_token = token
            return

        print(f"[INFO] No access token for '{self.server_name}', starting OAuth 2.1 flow.", flush=True)
        self._perform_oauth_flow()

    def _perform_oauth_flow(self):
        """Executes the full OAuth 2.1 Authorization Code Flow with PKCE."""
        base_url = self._get_base_url()
        client_id = self.config_manager.get_mcp_client_id(self.server_name)
        if not base_url or not client_id:
            print("[ERROR] Cannot start OAuth flow: Missing base_url or client_id.", flush=True)
            return

        # PKCE setup
        code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=').decode('utf-8')
        code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode('utf-8')).digest()).rstrip(b'=').decode('utf-8')
        
        redirect_uri = 'http://127.0.0.1:8080/'
        state = str(uuid.uuid4())

        auth_params = {
            'response_type': 'code',
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'scope': 'tools:read tools:execute',
            'state': state,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256'
        }
        auth_url = f"{base_url}/authorize?{urlencode(auth_params)}"

        server_address = ('127.0.0.1', 8080)
        handler_class = self._create_oauth_handler()
        
        try:
            httpd = HTTPServer(server_address, handler_class)
        except OSError as e:
            print(f"[ERROR] Could not start local server on {server_address}. Is port 8080 in use? Error: {e}", flush=True)
            return

        print(f"\n[ACTION] Please open this URL in your browser to authorize '{self.server_name}':\n{auth_url}\n", flush=True)
        webbrowser.open(auth_url)

        print("[INFO] Waiting for authorization code...", flush=True)
        httpd.handle_request()
        httpd.server_close()

        if not self.auth_code or self.received_state != state:
            print("[ERROR] OAuth flow failed: Did not receive a valid authorization code or state mismatch.", flush=True)
            return

        token_url = f"{base_url}/token"
        token_payload = {
            'grant_type': 'authorization_code',
            'code': self.auth_code,
            'redirect_uri': redirect_uri,
            'client_id': client_id,
            'code_verifier': code_verifier
        }

        client_secret = self.config_manager.get_mcp_client_secret(self.server_name)
        if client_secret:
            print(f"[INFO] Found client_secret for '{self.server_name}'. Adding to token request.", flush=True)
            token_payload['client_secret'] = client_secret

        token_headers = {
            'Accept': 'application/json'
        }
        
        try:
            response = requests.post(token_url, data=token_payload, headers=token_headers, timeout=20)

            if response.status_code != 200:
                print(f"[ERROR] Token exchange failed with status {response.status_code}.", flush=True)
                try:
                    error_details = response.json()
                    print(f"[ERROR] Server response: {json.dumps(error_details, indent=2)}", flush=True)
                except json.JSONDecodeError:
                    print(f"[ERROR] Server response (not JSON): {response.text}", flush=True)
                response.raise_for_status()

            token_data = response.json()
            
            if 'access_token' in token_data:
                self.access_token = token_data['access_token']
                self.config_manager.set_mcp_access_token(self.server_name, self.access_token)
                print(f"[INFO] Successfully obtained and saved access token for '{self.server_name}'.", flush=True)
            else:
                print(f"[ERROR] Token endpoint response did not include 'access_token'. Response: {token_data}", flush=True)

        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Failed to exchange authorization code for token: {e}", flush=True)
            if e.response:
                print(f"Response status: {e.response.status_code}", flush=True)
                print(f"Response body: {e.response.text}", flush=True)

    def _create_oauth_handler(self):
        """Factory to create the OAuth callback handler with a reference to this client instance."""
        mcp_client_instance = self

        class OAuthCallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed_path = urlparse(self.path)
                query_params = parse_qs(parsed_path.query)
                
                mcp_client_instance.auth_code = query_params.get('code', [None])[0]
                mcp_client_instance.received_state = query_params.get('state', [None])[0]

                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"<h1>Authorization successful!</h1><p>You can close this window now.</p>")
                print("[INFO] Received authorization code successfully.", flush=True)
            
            def log_message(self, format, *args):
                # Suppress logging of successful requests to keep the console clean
                pass

        return OAuthCallbackHandler

    def _start_stdio_proxy(self):
        """Starts the MCP proxy as a subprocess for stdio communication."""
        server_env = os.environ.copy()
        if 'env' in self.config and self.config['env']:
            print(f"[INFO] Passing custom environment variables to '{self.server_name}' proxy: {list(self.config['env'].keys())}", flush=True)
            server_env.update(self.config['env'])

        if hasattr(self, 'access_token') and self.access_token:
            print(f"[INFO] Passing MCP_ACCESS_TOKEN to '{self.server_name}' proxy.", flush=True)
            server_env['MCP_ACCESS_TOKEN'] = self.access_token

        args = self.config.get('args', [])
        command = self.command if isinstance(self.command, list) else [self.command]
        command_with_args = command + args
        print(f"[INFO] Starting MCP server '{self.server_name}' with command: {' '.join(command_with_args)}")

        try:
            self.process = subprocess.Popen(
                command_with_args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True, # Use text streams
                env=server_env,
                bufsize=1, # Line-buffered
                preexec_fn=os.setsid # To kill the process group
            )
            atexit.register(self.shutdown)

        except Exception as e:
            raise RuntimeError(f"Failed to start MCP server '{self.server_name}': {e}")

        # Start a background thread to monitor stderr for any out-of-band errors
        stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        stderr_thread.start()

    def _read_stderr(self):
        """Logs stderr from the proxy process."""
        if not self.process or not self.process.stderr:
            return
        
        suppressing_timeout_error = False
        try:
            for line in iter(self.process.stderr.readline, ''):
                if not line:
                    continue
                
                line_stripped = line.strip()

                if "Body Timeout Error" in line_stripped and not suppressing_timeout_error:
                    print(f"[{self.server_name}-proxy-stderr] Connection to remote server timed out. The proxy may attempt to reconnect automatically.", file=sys.stderr)
                    suppressing_timeout_error = True
                    continue

                if suppressing_timeout_error:
                    # The stack trace pretty-print ends with a closing brace on its own line.
                    if line_stripped == '}':
                        suppressing_timeout_error = False
                    continue # Suppress the line
                
                print(f"[{self.server_name}-proxy-stderr] {line_stripped}", file=sys.stderr)
        except ValueError:
            # This can happen if the process is killed and stderr is closed
            pass

    def shutdown(self):
        """Terminates the local MCP proxy subprocess if it's running."""
        if self.process and self.process.poll() is None:
            print(f"[INFO] Shutting down MCP server '{self.server_name}' (PID: {self.process.pid})...")
            # Terminate the process group to ensure all children (like npx) are killed
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            self.process.wait(timeout=5)
            print(f"[INFO] MCP server '{self.server_name}' shut down successfully.")

    def _make_request(self, payload: Dict[str, Any], timeout: int = 60) -> Dict[str, Any]:
        """Routes the request to the appropriate handler based on configuration."""
        if self.command:
            return self._stdio_request(payload, timeout)
        else:
            return self._http_request(payload, timeout)

    def _stdio_request(self, payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
        """Sends a request and reads a line of response from a text stream."""
        request_str = json.dumps(payload)
        
        with self._lock:
            if not self.process or not self.process.stdin or not self.process.stdout:
                raise IOError("MCP proxy stdin or stdout is not available.")
            
            # Send request as a newline-terminated JSON string
            self.process.stdin.write(f"{request_str}\n")
            self.process.stdin.flush()

            # Wait for the stdout to have data to read
            ready, _, _ = select.select([self.process.stdout], [], [], timeout)
            if not ready:
                raise TimeoutError("Timeout waiting for response from MCP proxy.")

            # Read one line of response
            response_line = self.process.stdout.readline()
            if not response_line:
                raise IOError("MCP proxy connection closed unexpectedly or sent empty response.")

            try:
                # The stream is in text mode, so we get a string directly
                return json.loads(response_line)
            except json.JSONDecodeError as e:
                raise IOError(f"Failed to decode JSON response from MCP proxy: {e}. Response: {response_line}")

    def _http_request(self, payload: Dict[str, Any], timeout: int = 60) -> Dict[str, Any]:
        """Makes a JSON-RPC request to a remote MCP server via HTTP."""
        if not self.url:
            return {"error": {"message": "HTTP request attempted without a URL."}}

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        # Add custom headers from config
        if 'request_headers' in self.config:
            headers.update(self.config['request_headers'])

        try:
            response = requests.post(self.url, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            return {"error": {"code": -32000, "message": f"HTTP request timed out after {timeout} seconds."}}
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] HTTP request to {self.url} failed: {e}")
            return {"error": {"message": str(e)}}

    def list_tools(self, timeout: int = 15) -> List[Dict[str, Any]]:
        """Retrieves the list of tools from the MCP server."""
        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/list",
            "params": {}
        }
        
        print(f"[INFO] Listing tools for '{self.server_name}'...")
        # Allow a longer timeout for the initial tool listing to give the user time to authenticate.
        response_data = self._make_request(payload, timeout=120)

        if not response_data or 'error' in response_data:
            error = response_data.get('error', {})
            error_msg = error.get('message', 'Unknown error')

            if "timed out" in error_msg:
                print(f"[INFO] Listing tools from '{self.server_name}' timed out. This is likely waiting for you to authenticate.")
                print(f"[INFO] Please complete the login flow in your browser, then try your request again.")
            else:
                print(f"[ERROR] MCP error from '{self.server_name}' while listing tools: {error_msg}")
            return []

        if response_data.get('id') != request_id:
            print(f"[ERROR] MCP response ID mismatch for '{self.server_name}'.")
            return []

        self.tools = response_data.get('result', {}).get('tools', [])
        print(f"[INFO] Successfully retrieved {len(self.tools)} tool(s) from '{self.server_name}'.")
        return self.tools

    def execute_tool(self, tool_name: str, parameters: Dict[str, Any], use_streaming: bool = False) -> Any:
        """Executes a tool on the server, with optional streaming."""
        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": parameters,
                "stream": use_streaming
            }
        }

        print(f"[INFO] Executing tool '{tool_name}' on '{self.server_name}' (Streaming: {use_streaming})")
        
        if use_streaming:
            return self._make_streaming_request(payload)
        else:
            response_data = self._make_request(payload)
            if not response_data or 'error' in response_data:
                error_details = response_data.get('error', {})
                return {"error": f"MCP tool execution error: {error_details.get('message', 'Unknown error')}"}
            
            result = response_data.get('result', {})
            if result.get('isError'):
                return {"error": f"Tool '{tool_name}' on server '{self.server_name}' reported an execution error."}
            
            content_parts = [item.get('text', '') for item in result.get('content', []) if item.get('type') == 'text']
            return "\n".join(content_parts) if content_parts else result

    def _make_streaming_request(self, payload: Dict[str, Any]) -> Any:
        """Routes the streaming request to the appropriate handler."""
        if self.command:
            return self._stdio_streaming_request(payload)
        else:
            return self._http_streaming_request(payload)

    def _stdio_streaming_request(self, payload: Dict[str, Any]) -> Any:
        """Handles a streaming request over stdio, processing JSON-RPC notifications."""
        if not self.process or not self.process.stdin or not self.process.stdout:
            return {"error": {"message": "Subprocess not running for stdio streaming."}}

        full_response_content = []
        with self._lock:
            try:
                request_str = json.dumps(payload)
                self.process.stdin.write(request_str + '\n')
                self.process.stdin.flush()

                print(f"--- Streaming output for tool call {payload['id']} ---")
                while True:
                    response_str = self.process.stdout.readline()
                    if not response_str:
                        print(f"\n[WARNING] Stdio stream ended unexpectedly.")
                        break
                    
                    try:
                        event = json.loads(response_str)
                        if 'error' in event and event.get('id') == payload['id']:
                            print(f"\n[ERROR] Received error during stream: {event['error']}")
                            return event

                        if event.get('method') == 'tool.stream.partial':
                            params = event.get('params', {})
                            content = params.get('content', [])
                            text_parts = [part.get('text', '') for part in content if part.get('type') == 'text']
                            if text_parts:
                                print(''.join(text_parts), end='', flush=True)
                                full_response_content.extend(text_parts)
                        
                        elif event.get('method') == 'tool.stream.final':
                            params = event.get('params', {})
                            content = params.get('content', [])
                            final_text_parts = [part.get('text', '') for part in content if part.get('type') == 'text']
                            if final_text_parts:
                                full_response_content = final_text_parts
                            break

                    except json.JSONDecodeError:
                        print(f"\n[WARNING] Could not decode JSON from stdio stream: {response_str.strip()}")
                print(f"\n--- End of streaming output ---")

            except IOError as e:
                print(f"\n[ERROR] Stdio streaming request failed: {e}")
                return {"error": f"Stdio streaming request failed: {e}"}

        return "\n".join(full_response_content)

    def _http_streaming_request(self, payload: Dict[str, Any]) -> Any:
        """Makes a streaming HTTP request and processes Server-Sent Events (SSE)."""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream'
        }
        full_response_content = []
        try:
            with requests.post(self.url, json=payload, headers=headers, stream=True, timeout=300) as response:
                response.raise_for_status()
                print(f"--- Streaming output for tool call {payload['id']} ---")
                for line in response.iter_lines(decode_unicode=True):
                    if line.startswith('data:'):
                        try:
                            data_str = line[len('data:'):].strip()
                            if data_str == '[DONE]':
                                break
                            event_data = json.loads(data_str)
                            
                            if event_data.get('type') == 'tool.stream.partial':
                                partial_result = event_data.get('result', {})
                                content_parts = [item.get('text', '') for item in partial_result.get('content', []) if item.get('type') == 'text']
                                print(''.join(content_parts), end='', flush=True)
                                full_response_content.extend(content_parts)

                            elif event_data.get('type') == 'tool.stream.final':
                                final_result = event_data.get('result', {})
                                if final_result:
                                    full_response_content = [item.get('text', '') for item in final_result.get('content', []) if item.get('type') == 'text']
                                break
                        
                        except json.JSONDecodeError:
                            print(f"\n[WARNING] Could not decode JSON from HTTP stream: {line}")
                print(f"\n--- End of streaming output ---")

        except requests.exceptions.RequestException as e:
            print(f"\n[ERROR] HTTP streaming request failed: {e}")
            return {"error": f"HTTP streaming request failed: {e}"}

        return "\n".join(full_response_content)
