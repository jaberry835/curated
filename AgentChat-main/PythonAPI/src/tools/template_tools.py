"""Template for new MCP tool modules."""

def register_example_tools(mcp):
    """Register example tools with the MCP server.
    
    To create new tools:
    1. Copy this file and rename it (e.g., string_tools.py)
    2. Update the function name (e.g., register_string_tools)
    3. Replace the example tools with your actual tools
    4. Import and add to TOOL_MODULES list in mcp_server.py
    """
    
    @mcp.tool()
    def example_tool(input_text: str) -> str:
        """Example tool that reverses text."""
        return input_text[::-1]
    
    @mcp.tool()
    def another_example(number: int) -> dict:
        """Another example tool."""
        return {
            "input": number,
            "doubled": number * 2,
            "squared": number ** 2
        }
    
    # Add more tools here...
    # Each tool needs the @mcp.tool() decorator
    # Make sure to include good docstrings for descriptions
