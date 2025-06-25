import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from brave_search_python_client import BraveSearch, WebSearchRequest
from newspaper import Article, Config
import traceback
from typing import Dict, Any, Optional
import nltk

# Define a constant for the User-Agent string
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36'

# Ensure the 'punkt' tokenizer is downloaded for newspaper
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    print("[INFO] Downloading 'punkt' tokenizer for NLTK...")
    nltk.download('punkt')

class WebSearchTool:
    """A tool for performing web searches and returning the clean text content of a page."""

    _last_call_time: float = 0
    _MONTHLY_QUOTA_LIMIT: int = 2000

    def __init__(self, brave_api_key: Optional[str] = None):
        """Initializes the WebSearchTool."""
        if not brave_api_key:
            raise ValueError("Brave API key is required for WebSearchTool")
        self.bs = BraveSearch(api_key=brave_api_key)
        self._usage_file = Path.home() / ".config" / "ai-thing" / "brave_usage.json"
        self._usage_data = self._load_usage()

    def _load_usage(self) -> Dict[str, Any]:
        """Loads usage data from the file, resetting if it's a new month."""
        current_month = datetime.now().strftime("%Y-%m")
        if not self._usage_file.exists():
            return {"month": current_month, "count": 0}

        try:
            with open(self._usage_file, 'r') as f:
                data = json.load(f)
            if data.get("month") != current_month:
                print("[INFO] New month detected. Resetting Brave API usage count.")
                return {"month": current_month, "count": 0}
            return data
        except (json.JSONDecodeError, IOError) as e:
            print(f"[WARNING] Could not read or parse usage file: {e}. Resetting count.")
            return {"month": current_month, "count": 0}

    def _save_usage(self):
        """Saves the updated usage data to the file."""
        self._usage_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._usage_file, 'w') as f:
            json.dump(self._usage_data, f, indent=4)


    def get_definition(self) -> Dict[str, Any]:
        """Returns the tool definition for the Gemini model."""
        return {
            'function_declarations': [{
                'name': 'web_search',
                'description': 'Search the web for a given query and return the clean text content of the most relevant page.',
                'parameters': {
                    'type': 'OBJECT',
                    'properties': {
                        'query': {
                            'type': 'STRING',
                            'description': 'The search query.'
                        }
                    },
                    'required': ['query']
                }
            }]
        }

    def get_summary(self) -> str:
        """Returns a brief summary of the tool's capabilities."""
        return "Performs a web search and returns the clean text content of the top result."

    def get_help(self) -> str:
        """Returns detailed help information for the tool."""
        return self.get_invocation_instructions()

    def get_invocation_instructions(self) -> str:
        """Returns the specific instructions for how the LLM should invoke this tool."""
        return """When you need to search the web, you MUST respond with a tool call in this exact format:
/tool web_search({"query": "your search query"})

Example:
User: What is the capital of France?
You: /tool web_search({"query": "capital of France"})

Important:
- The response MUST start with '/tool web_search('
- The arguments MUST be valid JSON
- The 'query' parameter is REQUIRED
- Do NOT include any other text when you want to execute a tool"""

    def execute(self, query: str) -> Dict[str, Any]:
        """
        Perform a web search and return the clean text content of the top result.

        Args:
            query: The search query.

        Returns:
            A dictionary containing the search result URL and its content, or an error.
        """
        # Check monthly quota
        if self._usage_data["count"] >= self._MONTHLY_QUOTA_LIMIT:
            error_msg = f"Brave Search API monthly quota of {self._MONTHLY_QUOTA_LIMIT} requests exceeded."
            print(f"[ERROR] {error_msg}")
            return {"error": error_msg}

        # Enforce 1 request per second rate limit
        elapsed = time.time() - self._last_call_time
        if elapsed < 1.0:
            sleep_time = 1.0 - elapsed
            print(f"[DEBUG] WebSearchTool: Rate limiting. Sleeping for {sleep_time:.2f} seconds.")
            time.sleep(sleep_time)

        print(f"[DEBUG] WebSearchTool: Executing with query: '{query}'")

        async def _search():
            print("[DEBUG] WebSearchTool: Searching with Brave...")
            response = await self.bs.web(WebSearchRequest(q=query, count=1))

            if not response or not response.web or not response.web.results:
                print("[DEBUG] WebSearchTool: No results found.")
                return {"error": "No results found for the query."}

            top_result = response.web.results[0]
            url = top_result.url
            print(f"[DEBUG] WebSearchTool: Found URL: {url}")

            # SECURITY NOTE: newspaper4k uses lxml.html.clean for parsing, which is not
            # recommended for security-critical applications. For the current use case of
            # extracting text for an LLM, the risk is low. If this content were ever
            # to be rendered in a browser, a more robust library like 'bleach' should
            # be used for HTML sanitization to prevent XSS vulnerabilities.
            config = Config()
            config.request_timeout = 10  # Set a 10-second timeout
            # Set a user-agent to mimic a browser and avoid 401 Unauthorized errors
            config.browser_user_agent = USER_AGENT

            article = Article(str(url), config=config)
            print("[DEBUG] WebSearchTool: Downloading article...")
            article.download()
            print("[DEBUG] WebSearchTool: Parsing article...")
            article.parse()
            print("[DEBUG] WebSearchTool: Article parsed successfully.")

            return {
                "url": str(url),
                "title": top_result.title,
                "content": article.text,
                "description": top_result.description
            }

        try:
            # Add a 15-second timeout to the entire search process
            result = asyncio.run(asyncio.wait_for(_search(), timeout=15.0))
            # On success, update timestamp and usage count
            self._last_call_time = time.time()
            if 'error' not in result:
                self._usage_data["count"] += 1
                self._save_usage()
            return result
        except asyncio.TimeoutError:
            print(f"[DEBUG] WebSearchTool: Search for query '{query}' timed out.")
            return {
                "query": query,
                "error": "The web search operation timed out after 15 seconds."
            }
        except Exception as e:
            print(f"[DEBUG] WebSearchTool: An error occurred: {e}")
            return {
                "query": query,
                "error": f"An unexpected error occurred: {str(e)}",
                "traceback": traceback.format_exc()
            }
