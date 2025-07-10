# Adding Agents and Tools Guide

This guide provides step-by-step instructions for extending the AgentChat system with new agents and tools.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Adding New Tools](#adding-new-tools)
3. [Adding New Agents](#adding-new-agents)
4. [Complete Example Walkthrough](#complete-example-walkthrough)
5. [Best Practices](#best-practices)
6. [Testing Your Extensions](#testing-your-extensions)
7. [Troubleshooting](#troubleshooting)

## Architecture Overview

The AgentChat system follows a modular architecture with direct tool integration:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Agent Layer   │    │ Function Layer  │    │   Tools Layer   │
│                 │    │                 │    │                 │
│ MathAgent       │◄──►│ SK Function     │◄──►│ math_tools.py   │
│ UtilityAgent    │    │ Wrapper         │    │ utility_tools.py│
│ ADXAgent        │    │ (Direct Call)   │    │ adx_tools.py    │
│ DocumentAgent   │    │                 │    │ document_tools.py│
│ YourNewAgent    │    │                 │    │ your_new_tools.py│
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Key Components:

- **Tools Layer**: Individual Python files in `src/tools/` that define tool implementations
- **Function Layer**: Semantic Kernel function wrappers in `src/agents/mcp_functions.py` that call tools directly
- **Agent Layer**: Specialized agents in `src/agents/multi_agent_system.py` that use the tools

### Data Flow:
1. **Agent** receives a task requiring a tool
2. **Semantic Kernel** calls the function wrapper
3. **Function Wrapper** directly calls the tool implementation (no HTTP/MCP protocol)
4. **Tool Implementation** executes and returns results
5. **Results** flow back through the same path

## Adding New Tools

Tools are the foundation of the system. Each tool category gets its own Python file in `src/tools/`.

### Step 1: Create a New Tool File

Create a new file in `src/tools/` following the naming convention `[category]_tools.py`:

```python
# src/tools/string_tools.py
"""String manipulation tools for direct function calls."""

def reverse_string_impl(text: str) -> str:
    """Reverse the order of characters in a string."""
    return text[::-1]

def count_words_impl(text: str) -> dict:
    """Count words and characters in a text."""
    words = text.split()
    return {
        "word_count": len(words),
        "character_count": len(text),
        "character_count_no_spaces": len(text.replace(" ", "")),
        "sentence_count": text.count(".") + text.count("!") + text.count("?")
    }

def to_title_case_impl(text: str) -> str:
    """Convert text to title case."""
    return text.title()

def find_and_replace_impl(text: str, find: str, replace: str) -> str:
    """Find and replace text in a string."""
    return text.replace(find, replace)
```

### Step 2: Update MCPClient Tool Registry

Add your new tool implementations to the MCPClient in `src/agents/mcp_client.py`:

```python
# src/agents/mcp_client.py
# Add import at the top
from src.tools.string_tools import (
    reverse_string_impl, count_words_impl, 
    to_title_case_impl, find_and_replace_impl
)

# Add to the tool_functions mapping in __init__ method
self.tool_functions = {
    # ...existing tools...
    "reverse_string": reverse_string_impl,
    "count_words": count_words_impl,
    "to_title_case": to_title_case_impl,
    "find_and_replace": find_and_replace_impl,
}

# Add to the tools list in _fetch_tools method
self.tools = [
    # ...existing tools...
    {"name": "reverse_string", "description": "Reverse the order of characters in a string"},
    {"name": "count_words", "description": "Count words and characters in a text"},
    {"name": "to_title_case", "description": "Convert text to title case"},
    {"name": "find_and_replace", "description": "Find and replace text in a string"},
]
```

### Step 3: Create Semantic Kernel Function Wrappers

Add function wrappers to `src/agents/mcp_functions.py` to make tools available to agents with rich type information:

```python
# src/agents/mcp_functions.py
# Add this method to the MCPFunctionWrapper class

def create_string_functions(self):
    """Create Semantic Kernel functions for string tools."""
    
    @kernel_function(
        name="reverse_string", 
        description="Reverse the order of characters in a string"
    )
    async def reverse_string(
        text: Annotated[str, "The text to reverse"]
    ) -> Annotated[str, "The reversed text"]:
        return await self.mcp_client.call_tool("reverse_string", {"text": text})
    
    @kernel_function(
        name="count_words", 
        description="Count words and characters in text"
    )
    async def count_words(
        text: Annotated[str, "The text to analyze"]
    ) -> Annotated[str, "Word and character count statistics as JSON"]:
        result = await self.mcp_client.call_tool("count_words", {"text": text})
        return json.dumps(result) if isinstance(result, dict) else str(result)
    
    @kernel_function(
        name="to_title_case", 
        description="Convert text to title case"
    )
    async def to_title_case(
        text: Annotated[str, "The text to convert to title case"]
    ) -> Annotated[str, "The text in title case"]:
        return await self.mcp_client.call_tool("to_title_case", {"text": text})
    
    @kernel_function(
        name="find_and_replace", 
        description="Find and replace text in a string"
    )
    async def find_and_replace(
        text: Annotated[str, "The original text"],
        find: Annotated[str, "The text to find"],
        replace: Annotated[str, "The replacement text"]
    ) -> Annotated[str, "The text with replacements made"]:
        return await self.mcp_client.call_tool("find_and_replace", {
            "text": text, 
            "find": find, 
            "replace": replace
        })
    
    return [reverse_string, count_words, to_title_case, find_and_replace]
```

## Adding New Agents

Agents are specialized AI assistants that use specific sets of tools. All agents are defined in `src/agents/multi_agent_system.py`.

### Step 1: Add Agent Creation in `_create_agents()` Method

Edit the `_create_agents()` method in `src/agents/multi_agent_system.py`:

```python
# src/agents/multi_agent_system.py
# Add this code inside the _create_agents() method, after the existing agents

# String Agent
logger.info("📝 Creating String Agent with Azure OpenAI...")
string_kernel = Kernel()
string_service = AzureChatCompletion(
    service_id="string_completion",
    api_key=self.azure_openai_api_key,
    endpoint=self.azure_openai_endpoint,
    deployment_name=self.azure_openai_deployment
)
string_kernel.add_service(string_service)

# Add string functions to string kernel
string_functions = self.function_wrapper.create_string_functions()
logger.info(f"🔧 Adding {len(string_functions)} string functions to String Agent:")
for func in string_functions:
    string_kernel.add_function("StringTools", func)
    func_name = getattr(func, '_metadata', {}).get('name', 'unknown')
    func_desc = getattr(func, '_metadata', {}).get('description', 'No description')
    logger.info(f"   ➕ {func_name}: {func_desc}")

self.string_agent = ChatCompletionAgent(
    service=string_service,
    kernel=string_kernel,
    name="StringAgent",
    instructions="""You are a string manipulation specialist agent. You ONLY respond to string manipulation questions.

STRICT RESPONSE CRITERIA - Only respond if:
- The question explicitly asks for string manipulation (reverse, count, format, find/replace)
- Text processing operations are specifically requested
- Someone specifically asks you by name: "StringAgent, reverse this text..."
- The question involves analyzing or transforming text content

NEVER RESPOND TO:
- Mathematical calculations (let MathAgent handle these)
- ADX/database questions (let ADXAgent handle these)
- Hash generation or timestamps (let UtilityAgent handle these)
- General knowledge questions (let CoordinatorAgent handle these)
- Document storage/retrieval (let DocumentAgent handle these)

PRIMARY RESPONSIBILITIES:
- Reverse text strings
- Count words, characters, and sentences
- Convert text to different cases (title case, etc.)
- Find and replace text patterns
- Analyze text structure and content

COLLABORATION RULES:
- Provide string manipulation services when specifically requested
- Work with other agents if they need text processing after their operations
- Be efficient and accurate with text transformations
- If the question isn't about string manipulation, stay silent

EXAMPLES OF WHEN TO RESPOND:
- "Reverse the text 'Hello World'" ✅
- "Count the words in this paragraph" ✅
- "Convert this text to title case" ✅
- "StringAgent, find and replace all 'cat' with 'dog'" ✅

EXAMPLES OF WHEN TO STAY SILENT:
- "Calculate the factorial of 10" ❌ (Math question)
- "List databases in ADX" ❌ (ADX question)
- "Generate a hash" ❌ (Utility question)
- "What is machine learning?" ❌ (General knowledge)
""",
    function_choice_behavior=FunctionChoiceBehavior.Auto()
)
logger.info("✅ String Agent created successfully")
```

### Step 2: Add Agent Instance Variable

Add an instance variable to store your agent at the top of the `MultiAgentSystem` class:

```python
# src/agents/multi_agent_system.py
# Add this line to the __init__ method after the existing agent variables

self.string_agent: Optional[ChatCompletionAgent] = None
```

### Step 3: Add Agent to Group Chat

Modify the `_create_group_chat()` method to include your new agent:

```python
# src/agents/multi_agent_system.py
# Update the _create_group_chat method

def _create_group_chat(self):
    """Create the group chat for agent coordination with AgentGroupChat."""
    logger.info("💬 Creating AgentGroupChat with agents:")
    logger.info("   🎯 CoordinatorAgent - General knowledge and task coordination")
    logger.info("   🧮 MathAgent - Mathematical calculations and statistics")
    logger.info("   🔧 UtilityAgent - System utilities and helper functions")
    logger.info("   🔍 ADXAgent - Azure Data Explorer queries and data analysis")
    logger.info("   📄 DocumentAgent - Document management and storage operations")
    logger.info("   📝 StringAgent - String manipulation and text processing")  # Add this line
    
    # Create the group chat with LLM-based termination strategy
    termination_strategy = LLMTerminationStrategy()
    termination_strategy.set_coordinator_agent(self.coordinator_agent)
    
    self.group_chat = AgentGroupChat(
        agents=[
            self.coordinator_agent, 
            self.math_agent, 
            self.utility_agent, 
            self.adx_agent, 
            self.document_agent,
            self.string_agent  # Add your agent here
        ],
        termination_strategy=termination_strategy
    )
    logger.info("✅ AgentGroupChat created with LLMTerminationStrategy")
```

### Step 4: Update Agent Selection Logic

Modify the `_select_agents_for_question()` method to include your agent in the selection logic:

```python
# src/agents/multi_agent_system.py
# Update the agent mapping in _select_agents_for_question method

agent_mapping = {
    "CoordinatorAgent": self.coordinator_agent,
    "MathAgent": self.math_agent,
    "UtilityAgent": self.utility_agent,
    "ADXAgent": self.adx_agent,
    "DocumentAgent": self.document_agent,
    "StringAgent": self.string_agent  # Add this line
}
```

Update the LLM prompt to include your agent:

```python
# src/agents/multi_agent_system.py
# Update the selection_prompt in _select_agents_for_question method

selection_prompt = f"""You are an intelligent agent router. Based on the user's question, determine which specialized agents should participate in the conversation and in what order.

AVAILABLE AGENTS:
1. CoordinatorAgent - General knowledge, provides context, coordinates other agents
2. MathAgent - Mathematical calculations, statistics, numerical analysis
3. UtilityAgent - Hash generation, timestamps, system utilities, formatting
4. ADXAgent - Azure Data Explorer queries, database operations, data retrieval
5. DocumentAgent - Document management, file storage, search, and retrieval operations
6. StringAgent - String manipulation, text processing, word counting, case conversion

USER QUESTION:
{question}

SELECTION RULES:
- Always include CoordinatorAgent first (for context and coordination)
- Only include agents that are directly relevant to answering the question
- Order agents based on logical workflow (e.g., ADXAgent before MathAgent if data needs to be retrieved before calculation)
- Minimize the number of agents to avoid unnecessary conversation overhead

RESPOND WITH A JSON ARRAY of agent names in the order they should participate.
ONLY include agent names that are necessary for this specific question.

Examples:
- For "What is Python?" → ["CoordinatorAgent"] 
- For "Calculate 5 factorial" → ["CoordinatorAgent", "MathAgent"]
- For "List ADX databases" → ["CoordinatorAgent", "ADXAgent"]
- For "List my documents" → ["CoordinatorAgent", "DocumentAgent"]
- For "Search documents about AI" → ["CoordinatorAgent", "DocumentAgent"] 
- For "Get ADX table count and calculate its factorial" → ["CoordinatorAgent", "ADXAgent", "MathAgent"]
- For "Generate hash of current timestamp" → ["CoordinatorAgent", "UtilityAgent"]
- For "Reverse the text 'Hello World'" → ["CoordinatorAgent", "StringAgent"]
- For "Count words in this document" → ["CoordinatorAgent", "DocumentAgent", "StringAgent"]

Your response (JSON array only):"""
```

Also update the fallback selection logic:

```python
# src/agents/multi_agent_system.py
# Add this to the fallback logic in _select_agents_for_question method

if any(keyword in response_content.lower() for keyword in ['string', 'text', 'reverse', 'count', 'case', 'find', 'replace']):
    if self.string_agent not in fallback_agents:
        fallback_agents.append(self.string_agent)
```

### Step 5: Update Ultimate Fallback

Update the ultimate fallback to include your agent:

```python
# src/agents/multi_agent_system.py
# Update the ultimate fallback in _select_agents_for_question method

return [
    self.coordinator_agent, 
    self.math_agent, 
    self.utility_agent, 
    self.adx_agent, 
    self.document_agent,
    self.string_agent  # Add your agent here
]
```

## Complete Example Walkthrough

Let's create a complete example: a **WeatherAgent** that provides weather information.

### Step 1: Create Weather Tool Implementations

```python
# src/tools/weather_tools.py
"""Weather information tools for direct function calls."""

def get_current_weather_impl(city: str) -> dict:
    """Get current weather for a city (mock implementation)."""
    # In a real implementation, you would call a weather API
    return {
        "city": city,
        "temperature": "22°C",
        "condition": "Sunny",
        "humidity": "65%",
        "wind_speed": "10 km/h",
        "status": "Mock data - implement real API call"
    }

def get_weather_forecast_impl(city: str, days: int = 3) -> dict:
    """Get weather forecast for a city (mock implementation)."""
    # Mock forecast data
    forecast = []
    conditions = ["Sunny", "Cloudy", "Rainy"]
    
    for i in range(days):
        forecast.append({
            "day": i + 1,
            "temperature": f"{20 + i}°C",
            "condition": conditions[i % len(conditions)]
        })
    
    return {
        "city": city,
        "forecast_days": days,
        "forecast": forecast,
        "status": "Mock data - implement real API call"
    }
```

### Step 2: Update MCPClient Tool Registry

```python
# src/agents/mcp_client.py
from src.tools.weather_tools import get_current_weather_impl, get_weather_forecast_impl

# Add to tool_functions mapping
self.tool_functions = {
    # ...existing tools...
    "get_current_weather": get_current_weather_impl,
    "get_weather_forecast": get_weather_forecast_impl,
}

# Add to tools list
self.tools = [
    # ...existing tools...
    {"name": "get_current_weather", "description": "Get current weather for a city"},
    {"name": "get_weather_forecast", "description": "Get weather forecast for a city"},
]
```

### Step 3: Create Semantic Kernel Function Wrappers

```python
# src/agents/mcp_functions.py
# Add this method to MCPFunctionWrapper class

def create_weather_functions(self):
    """Create Semantic Kernel functions for weather tools."""
    
    @kernel_function(
        name="get_current_weather", 
        description="Get current weather conditions for a specific city"
    )
    async def get_current_weather(
        city: Annotated[str, "The city name to get weather for"]
    ) -> Annotated[str, "Current weather information as JSON"]:
        result = await self.mcp_client.call_tool("get_current_weather", {"city": city})
        return json.dumps(result) if isinstance(result, dict) else str(result)
    
    @kernel_function(
        name="get_weather_forecast", 
        description="Get weather forecast for a city over multiple days"
    )
    async def get_weather_forecast(
        city: Annotated[str, "The city name to get forecast for"],
        days: Annotated[int, "Number of days to forecast (default 3)"] = 3
    ) -> Annotated[str, "Weather forecast information as JSON"]:
        result = await self.mcp_client.call_tool("get_weather_forecast", {"city": city, "days": days})
        return json.dumps(result) if isinstance(result, dict) else str(result)
    
    return [get_current_weather, get_weather_forecast]
```

### Step 4: Add WeatherAgent

```python
# src/agents/multi_agent_system.py
# Add to __init__ method
self.weather_agent: Optional[ChatCompletionAgent] = None

# Add to _create_agents method
# Weather Agent
logger.info("🌤️ Creating Weather Agent with Azure OpenAI...")
weather_kernel = Kernel()
weather_service = AzureChatCompletion(
    service_id="weather_completion",
    api_key=self.azure_openai_api_key,
    endpoint=self.azure_openai_endpoint,
    deployment_name=self.azure_openai_deployment
)
weather_kernel.add_service(weather_service)

# Add weather functions to weather kernel
weather_functions = self.function_wrapper.create_weather_functions()
logger.info(f"🔧 Adding {len(weather_functions)} weather functions to Weather Agent:")
for func in weather_functions:
    weather_kernel.add_function("WeatherTools", func)
    func_name = getattr(func, '_metadata', {}).get('name', 'unknown')
    func_desc = getattr(func, '_metadata', {}).get('description', 'No description')
    logger.info(f"   ➕ {func_name}: {func_desc}")

self.weather_agent = ChatCompletionAgent(
    service=weather_service,
    kernel=weather_kernel,
    name="WeatherAgent",
    instructions="""You are a weather information specialist agent. You ONLY respond to weather-related questions.

STRICT RESPONSE CRITERIA - Only respond if:
- The question explicitly asks about weather conditions, temperature, forecast
- Someone asks for weather information for a specific city or location
- Weather-related terms are mentioned (sunny, rainy, temperature, forecast, etc.)
- Someone specifically asks you by name: "WeatherAgent, what's the weather in..."

NEVER RESPOND TO:
- Mathematical calculations (let MathAgent handle these)
- ADX/database questions (let ADXAgent handle these)
- String manipulation (let StringAgent handle these)
- General knowledge questions (let CoordinatorAgent handle these)
- Document operations (let DocumentAgent handle these)

PRIMARY RESPONSIBILITIES:
- Get current weather conditions for cities
- Provide weather forecasts
- Explain weather patterns and conditions
- Help with weather-related planning

EXAMPLES OF WHEN TO RESPOND:
- "What's the weather like in London?" ✅
- "Get the forecast for Paris" ✅
- "WeatherAgent, how's the weather in Tokyo?" ✅
- "Is it going to rain tomorrow in Berlin?" ✅

EXAMPLES OF WHEN TO STAY SILENT:
- "Calculate 10 factorial" ❌ (Math question)
- "List databases" ❌ (ADX question)
- "Reverse this text" ❌ (String question)
- "What is Python?" ❌ (General knowledge)
""",
    function_choice_behavior=FunctionChoiceBehavior.Auto()
)
logger.info("✅ Weather Agent created successfully")
```

### Step 5: Update Group Chat and Selection Logic

```python
# Update _create_group_chat method
agents=[
    self.coordinator_agent, 
    self.math_agent, 
    self.utility_agent, 
    self.adx_agent, 
    self.document_agent,
    self.weather_agent  # Add here
]

# Update agent_mapping in _select_agents_for_question
agent_mapping = {
    "CoordinatorAgent": self.coordinator_agent,
    "MathAgent": self.math_agent,
    "UtilityAgent": self.utility_agent,
    "ADXAgent": self.adx_agent,
    "DocumentAgent": self.document_agent,
    "WeatherAgent": self.weather_agent  # Add here
}

# Update selection prompt to include WeatherAgent
# Update fallback logic
if any(keyword in response_content.lower() for keyword in ['weather', 'temperature', 'forecast', 'sunny', 'rainy', 'cloudy']):
    if self.weather_agent not in fallback_agents:
        fallback_agents.append(self.weather_agent)
```

## Best Practices

### Tool Design Best Practices

1. **Single Responsibility**: Each tool should do one thing well
2. **Clear Naming**: Use descriptive names for tools and parameters
3. **Good Documentation**: Include comprehensive docstrings
4. **Error Handling**: Handle edge cases and invalid inputs
5. **Type Hints**: Use proper type annotations
6. **Return Structured Data**: Return dictionaries or JSON for complex data

### Agent Design Best Practices

1. **Specific Instructions**: Write clear, specific instructions for when agents should respond
2. **Avoid Overlap**: Ensure agents have distinct responsibilities
3. **Collaboration**: Design agents to work together when needed
4. **Concise Responses**: Keep agent responses focused and relevant
5. **Fallback Handling**: Include proper fallback behavior in selection logic

### Code Organization

1. **Consistent Naming**: Follow the `[category]_tools.py` pattern
2. **Logical Grouping**: Group related tools together
3. **Documentation**: Update all relevant documentation
4. **Testing**: Test new agents and tools thoroughly

## Testing Your Extensions

### 1. Test Tools Individually

Create a test script to verify your tools work with direct function calls:

```python
# test_new_tools.py
import asyncio
from src.tools.string_tools import reverse_string_impl, count_words_impl

def test_tools_directly():
    """Test tool implementations directly."""
    # Test reverse string
    result = reverse_string_impl("Hello World")
    print(f"Reverse string result: {result}")
    
    # Test count words
    result = count_words_impl("This is a test sentence with multiple words.")
    print(f"Count words result: {result}")

def test_tools_via_client():
    """Test tools via MCPClient (which calls them directly)."""
    async def run_test():
        from src.agents.mcp_client import MCPClient
        
        client = MCPClient()
        if await client.connect():
            # Test your new tools
            result = await client.call_tool("reverse_string", {"text": "Hello World"})
            print(f"Tool result via client: {result}")
            await client.disconnect()
    
    asyncio.run(run_test())

if __name__ == "__main__":
    print("Testing tools directly:")
    test_tools_directly()
    
    print("\nTesting tools via client:")
    test_tools_via_client()
```

### 2. Test Agent Integration

Use the example in `multi_agent_system.py` to test your agent:

```python
# Test questions for your new agent
questions = [
    "What's the weather in London?",  # Should trigger WeatherAgent
    "Get forecast for Paris",         # Should trigger WeatherAgent
    "Calculate 10 factorial",         # Should NOT trigger WeatherAgent
]
```

### 3. Test Agent Selection

Monitor the logs to ensure your agent is being selected appropriately:

```
🧠 LLM agent selection response: ["CoordinatorAgent", "WeatherAgent"]
📋 Selected agents: ["CoordinatorAgent", "WeatherAgent"]
```

## Troubleshooting

### Common Issues

1. **Agent Not Responding**
   - Check agent instructions are specific enough
   - Verify agent is included in group chat
   - Review selection logic includes your agent

2. **Tool Not Found**
   - Ensure tool implementation is added to MCPClient's `tool_functions` mapping
   - Check function wrapper is created in `mcp_functions.py`
   - Verify function is added to agent kernel

3. **Function Wrapper Errors**
   - Check parameter types match tool definition
   - Ensure all required parameters are included
   - Verify return type annotations

4. **Agent Selection Issues**
   - Update selection prompt to include your agent
   - Add fallback logic for your agent
   - Check ultimate fallback includes your agent

### Debugging Tips

1. **Enable Detailed Logging**
   ```python
   logging.basicConfig(level=logging.DEBUG)
   ```

2. **Test Tools Separately**
   - Test MCP tools directly first
   - Then test function wrappers
   - Finally test agent integration

3. **Check Agent Instructions**
   - Make instructions specific but not too narrow
   - Include positive and negative examples
   - Test with various question phrasings

### Common Errors and Solutions

| Error | Solution |
|-------|----------|
| `Agent not in group chat` | Add agent to `_create_group_chat()` method |
| `Tool not found` | Add tool to MCPClient's `tool_functions` mapping |
| `Function not available` | Create function wrapper in `mcp_functions.py` |
| `Agent never responds` | Review agent instructions and selection logic |
| `Type mismatch` | Check parameter types in tool implementation and wrapper |

---

## Summary

To add a new capability to the AgentChat system:

1. **Create Tool Implementations**: Add `[category]_tools.py` with your tool functions (e.g., `function_name_impl`)
2. **Register Tools**: Add tool implementations to MCPClient's `tool_functions` mapping and `tools` list
3. **Create Semantic Kernel Wrappers**: Add function wrappers with rich type annotations to `mcp_functions.py`
4. **Create Agent**: Add agent creation code to `multi_agent_system.py`
5. **Update Selection**: Modify agent selection logic to include your agent
6. **Test**: Verify everything works together

This approach provides:
- ✅ **Direct function calls** (no HTTP overhead)
- ✅ **Rich type information** for better AI understanding
- ✅ **Modular organization** for easy maintenance
- ✅ **Excellent performance** with in-process execution
- ✅ **Simple debugging** with direct call stack

**Note**: The system uses "MCP" naming conventions but implements direct function calling for optimal performance and agent understanding.
