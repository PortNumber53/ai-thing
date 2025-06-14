# AI Agent Workflow System

This document outlines the architecture and components of the AI agent workflow system implemented in `workflow.py`.

## Overview

The workflow system is built around the `GraphAIAgent` class, which implements a stateful, graph-based processing pipeline for handling user queries. The system uses LangGraph to manage the flow of execution between different processing nodes.

## Core Components

### AgentState

A dataclass that maintains the state throughout the agent's execution:
- `query`: The user's input
- `context`: Context for the current operation
- `analysis`: Analysis of the query
- `response`: Generated response
- `next_action`: Next action to take
- `iteration`: Current iteration count
- `max_iterations`: Maximum allowed iterations

### GraphAIAgent

The main class that implements the agent's functionality.

#### Initialization
- Sets up the agent with Google's Gemini model
- Initializes two LLM instances:
  - Main LLM for general responses
  - Specialized analyzer LLM with lower temperature for focused analysis

#### Configuration
- `_get_secrets_path()`: Gets the path to the secrets file
- `_read_secrets()`: Reads API key and model from secrets.ini
- `_configure_from_secrets()`: Configures the API key and model

#### Graph Construction (`_build_graph`)

Creates a state machine with these nodes:
1. `router`: Initial query analysis and routing
2. `analyzer`: Determines if research is needed
3. `researcher`: Performs additional research if needed
4. `responder`: Generates the final response
5. `validator`: Validates if the response is satisfactory

#### Node Implementations
- `_router_node`: Analyzes and categorizes incoming queries
- `_analyzer_node`: Decides if research is needed
- `_researcher_node`: Performs additional research
- `_responder_node`: Generates responses
- `_validator_node`: Validates responses

#### Decision Functions
- `_decide_next_step`: Determines the next node based on analysis
- `_should_continue`: Decides if the workflow should continue or end

## Workflow Process

1. **Routing**: The query is analyzed and categorized
2. **Analysis**: The system determines if additional research is needed
3. **Research** (if needed): Additional information is gathered
4. **Response Generation**: A response is generated based on the analysis and research
5. **Validation**: The response is validated for quality and completeness
6. **Iteration**: The process repeats if necessary, up to `max_iterations`

## Configuration

Configuration is managed through a `secrets.ini` file in the user's config directory (`~/.config/secrets.ini`). The file should have the following format:

```ini
[google]
api_key = your_google_api_key_here
model = gemini-1.5-flash  # optional
```

## Usage

```python
from workflow import GraphAIAgent

# Initialize the agent
agent = GraphAIAgent()  # Will use API key from secrets.ini

# Process a query
result = agent.process_query("Your query here")
print(result)
```

## Error Handling

The system includes comprehensive error handling for:
- Missing or invalid API keys
- Configuration issues
- Network connectivity problems
- Invalid state transitions

## Dependencies

- Python 3.8+
- langgraph
- langchain-google-genai
- python-dotenv
