import json
import requests
import uuid
import webbrowser
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, List, Optional

class MCPClient:
    """
    Manages a direct connection to a remote MCP server, including OAuth 2.1 authentication.
    """
    def __init__(self, server_name: str, config: Dict[str, Any]):
        self.server_name = server_name
        self.config = config
        self.url = config.get('url')
        self.auth_config = config.get('auth')
        
        self.access_token: Optional[str] = None
        self.tools: List[Dict[str, Any]] = []
        
        if not self.url or not self.auth_config:
            raise ValueError(f"MCP configuration for '{server_name}' is missing 'url' or 'auth' details.")

    def authenticate(self) -> bool:
        """
        Ensures the client is authenticated with the MCP server using OAuth 2.1.
        If an access token is not available, it initiates the full auth flow.
        """
        if self.access_token:
            return True

        print(f"[INFO] Authenticating with MCP server: '{self.server_name}'...")
        
        auth_code = self._get_authorization_code()
        if not auth_code:
            print(f"[ERROR] Could not retrieve authorization code for '{self.server_name}'.")
            return False
            
        access_token = self._exchange_code_for_token(auth_code)
        if not access_token:
            print(f"[ERROR] Could not exchange authorization code for an access token for '{self.server_name}'.")
            return False

        self.access_token = access_token
        print(f"[INFO] Successfully authenticated with '{self.server_name}'.")
        return True

    def _get_authorization_code(self) -> Optional[str]:
        """
        Initiates the OAuth Authorization Code Grant flow.
        """
        redirect_uri = "http://localhost:8989/callback"
        state = str(uuid.uuid4())
        
        params = {
            'response_type': 'code',
            'client_id': self.auth_config.get('client_id'),
            'redirect_uri': redirect_uri,
            'state': state
        }
        scopes = self.auth_config.get('scopes', [])
        if scopes:
            params['scope'] = ' '.join(scopes)
        auth_url = f"{self.auth_config['auth_url']}?{requests.compat.urlencode(params)}"

        auth_code = None
        auth_event = threading.Event()

        class OAuthCallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                nonlocal auth_code
                query_components = parse_qs(urlparse(self.path).query)
                if 'code' in query_components:
                    auth_code = query_components["code"][0]
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(b"<h1>Authentication successful!</h1><p>You can close this window now.</p>")
                else:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"<h1>Authentication failed.</h1><p>No authorization code found in the request.</p>")
                auth_event.set()

        server = HTTPServer(('localhost', 8989), OAuthCallbackHandler)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()

        print("\n" + "="*80)
        print(f"ACTION REQUIRED: Please authorize this application for MCP server '{self.server_name}'.")
        print(f"Opening the following URL in your browser:\n{auth_url}")
        print("="*80 + "\n")
        webbrowser.open(auth_url)

        # Wait for the callback to be handled or timeout
        auth_event.wait(timeout=120)
        server.shutdown()
        server.server_close()

        return auth_code

    def _exchange_code_for_token(self, code: str) -> Optional[str]:
        """
        Exchanges an authorization code for an access token.
        """
        client_id = self.auth_config.get('client_id')
        client_secret = self.auth_config.get('client_secret')

        token_payload = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': "http://localhost:8989/callback",
        }

        auth_tuple = None
        # The presence of a client_secret indicates we should use HTTP Basic Auth.
        if client_secret:
            auth_tuple = (client_id, client_secret)
        else:
            # If no secret, include client_id in the payload, as is common.
            token_payload['client_id'] = client_id

        try:
            token_response = requests.post(self.auth_config['token_url'], data=token_payload, auth=auth_tuple)
            token_response.raise_for_status()
            token_json = token_response.json()
            self.access_token = token_json['access_token']
            print(f"[INFO] Successfully obtained access token for '{self.server_name}'.")
            return self.access_token
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Network error when exchanging code for token for '{self.server_name}': {e}")
            print(f"[DEBUG] Response content: {e.response.text if e.response else 'No response'}")
            return None

    def _make_request(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Makes an authenticated JSON-RPC request to the MCP server."""
        if not self.access_token:
            if not self.authenticate():
                return {"error": {"message": "Authentication failed."}}

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.access_token}'
        }
        
        try:
            response = requests.post(self.url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
             if e.response.status_code == 401: # Unauthorized
                print(f"[INFO] Access token for '{self.server_name}' may have expired. Re-authenticating...")
                self.access_token = None # Clear expired token
                if not self.authenticate():
                    return {"error": {"message": "Re-authentication failed."}}
                # Retry the request with the new token
                headers['Authorization'] = f'Bearer {self.access_token}'
                response = requests.post(self.url, json=payload, headers=headers, timeout=30)
                response.raise_for_status()
                return response.json()
             else:
                print(f"[ERROR] HTTP error from '{self.server_name}': {e}")
                return {"error": {"message": f"HTTP error: {e}"}}
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Network error during MCP request for '{self.server_name}': {e}")
            return {"error": {"message": f"Network error: {e}"}}
        except json.JSONDecodeError:
            print(f"[ERROR] Failed to decode JSON response from '{self.server_name}'.")
            return {"error": {"message": "Invalid JSON response."}}

    def list_tools(self) -> List[Dict[str, Any]]:
        """Retrieves the list of tools from the remote server."""
        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/list",
            "params": {}
        }
        
        print(f"[INFO] Listing tools for '{self.server_name}' from {self.url}")
        response_data = self._make_request(payload)

        if not response_data or 'error' in response_data:
            error_msg = response_data.get('error', {}).get('message', 'Unknown error')
            print(f"[ERROR] MCP error from '{self.server_name}' while listing tools: {error_msg}")
            return []

        if response_data.get('id') != request_id:
            print(f"[ERROR] MCP response ID mismatch for '{self.server_name}'.")
            return []

        self.tools = response_data.get('result', {}).get('tools', [])
        print(f"[INFO] Successfully retrieved {len(self.tools)} tool(s) from '{self.server_name}'.")
        return self.tools

    def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """Executes a tool on the remote server."""
        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": parameters
            }
        }

        print(f"[INFO] Executing remote tool '{tool_name}' on '{self.server_name}' with params: {parameters}")
        response_data = self._make_request(payload)

        if not response_data or 'error' in response_data:
            error_details = response_data.get('error', {})
            return {"error": f"MCP tool execution error: {error_details.get('message', 'Unknown error')}"}

        result = response_data.get('result', {})
        if result.get('isError'):
             return {"error": f"Tool '{tool_name}' on server '{self.server_name}' reported an execution error."}

        content_parts = [item.get('text', '') for item in result.get('content', []) if item.get('type') == 'text']
        return "\n".join(content_parts) if content_parts else result
