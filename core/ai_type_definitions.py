from typing import Dict, Any, List, TypedDict, Callable
from dataclasses import dataclass

# Type definitions for function calling
class FunctionCall(TypedDict):
    name: str
    args: Dict[str, Any]

# Tool definition type
class Tool(TypedDict):
    function_declarations: List[Dict[str, Any]]

# Part type for chat messages
class Part(TypedDict, total=False):
    text: str
    function_response: Dict[str, Any]  # For function responses
    function_call: Dict[str, Any]  # For function calls from the model


# AITool definition
@dataclass
class AITool:
    """A structured representation of a tool for the AI to use."""
    name: str
    description: str
    func: Callable[..., Any]
    parameters: Dict[str, Any]
