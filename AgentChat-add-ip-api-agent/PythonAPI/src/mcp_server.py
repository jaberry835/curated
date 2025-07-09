"""Modular MCP server with organized tools."""

from fastmcp import FastMCP
#from mcp.server.fastmcp import FastMCP

# Import tool modules
from src.tools.utility_tools import register_utility_tools
from src.tools.math_tools import register_math_tools
from src.tools.adx_tools import register_adx_tools
from src.tools.document_tools import register_document_tools

# Create MCP server
mcp = FastMCP("PythonAPI_MCP_Server")

# Register all tool modules
# To add new tools: 1) Create a new file in tools/, 2) Add import above, 3) Add to this list
TOOL_MODULES = [
    register_utility_tools,
    register_math_tools,
    register_adx_tools,
    register_document_tools,
    # Add more tool registrations here as you create new tool files
]

# Register all tools
for register_func in TOOL_MODULES:
    register_func(mcp)


# Resources
@mcp.resource("server://status")
def get_server_status() -> str:
    """Get current server status and information."""
    import json
    status_info = {
        "server_name": "PythonAPI_MCP_Server",
        "status": "running",
        "tools_available": [
            "health_check", "get_timestamp", "generate_hash",
            "add", "subtract", "multiply", "divide", 
            "calculate_statistics", "format_json",
            "upload_document", "list_documents", "get_document",
            "download_document", "delete_document", "search_documents",
            "get_document_content_summary"
        ],
        "categories": {
            "utility": ["health_check", "get_timestamp", "generate_hash", "format_json"],
            "math": ["add", "subtract", "multiply", "divide", "calculate_statistics"],
            "document": ["upload_document", "list_documents", "get_document", "download_document", "delete_document", "search_documents", "get_document_content_summary"]
        }
    }
    return json.dumps(status_info, indent=2)


@mcp.resource("tools://list")
def get_tools_list() -> str:
    """Get list of all available tools."""
    import json
    tools_list = [
        {"name": "health_check", "description": "Check the health and status of the MCP server"},
        {"name": "get_timestamp", "description": "Get the current UTC timestamp"},
        {"name": "generate_hash", "description": "Generate a hash for the given text"},
        {"name": "add", "description": "Add two numbers"},
        {"name": "subtract", "description": "Subtract two numbers"},
        {"name": "multiply", "description": "Multiply two numbers"},
        {"name": "divide", "description": "Divide two numbers"},
        {"name": "calculate_statistics", "description": "Calculate comprehensive statistics for a list of numbers"},
        {"name": "format_json", "description": "Validate and format JSON data"},
        {"name": "upload_document", "description": "Upload a document to Azure Blob Storage"},
        {"name": "list_documents", "description": "List documents in Azure Blob Storage"},
        {"name": "get_document", "description": "Get document metadata from Azure Blob Storage"},
        {"name": "download_document", "description": "Download a document from Azure Blob Storage"},
        {"name": "delete_document", "description": "Delete a document from Azure Blob Storage"},
        {"name": "search_documents", "description": "Search documents using Azure AI Search"},
        {"name": "get_document_content_summary", "description": "Get a summary of document content"}
    ]
    return json.dumps(tools_list, indent=2)


# Prompts
@mcp.prompt()
def tool_usage_guide(tool_name: str = "") -> str:
    """Generate a usage guide for a specific tool or all tools."""
    tools_info = {
        "health_check": "Check the health and status of the MCP server",
        "get_timestamp": "Get the current UTC timestamp in ISO format",
        "generate_hash": "Generate a hash for text using md5, sha1, sha256, or sha512",
        "add": "Add two numbers",
        "subtract": "Subtract two numbers", 
        "multiply": "Multiply two numbers",
        "divide": "Divide two numbers (throws error on division by zero)",
        "calculate_statistics": "Calculate mean, median, mode, std_dev, variance, min, max for a list of numbers",
        "format_json": "Validate and format JSON data with specified indentation",
        "upload_document": "Upload a document to Azure Blob Storage and prepare for indexing",
        "list_documents": "List documents stored in Azure Blob Storage with optional filtering",
        "get_document": "Get metadata for a specific document from Azure Blob Storage",
        "download_document": "Download a document from Azure Blob Storage (returns base64 encoded content)",
        "delete_document": "Delete a document from Azure Blob Storage and remove from search index",
        "search_documents": "Search documents using Azure AI Search with natural language queries",
        "get_document_content_summary": "Get a text summary of document content for AI processing"
    }
    
    if tool_name and tool_name in tools_info:
        return f"""
# Tool Usage Guide: {tool_name}

**Description:** {tools_info[tool_name]}

## Usage
This tool can be called through the MCP protocol.
Call with appropriate parameters based on the tool's function.
"""
    else:
        # Return guide for all tools
        guide = "# Available MCP Tools\n\n"
        
        guide += "## Utility Tools\n"
        utility_tools = ["health_check", "get_timestamp", "generate_hash", "format_json"]
        for tool in utility_tools:
            if tool in tools_info:
                guide += f"- **{tool}**: {tools_info[tool]}\n"
        
        guide += "\n## Math Tools\n"
        math_tools = ["add", "subtract", "multiply", "divide", "calculate_statistics"]
        for tool in math_tools:
            if tool in tools_info:
                guide += f"- **{tool}**: {tools_info[tool]}\n"
        
        guide += "\n## Document Tools\n"
        document_tools = ["upload_document", "list_documents", "get_document", "download_document", "delete_document", "search_documents", "get_document_content_summary"]
        for tool in document_tools:
            if tool in tools_info:
                guide += f"- **{tool}**: {tools_info[tool]}\n"
        
        return guide


if __name__ == "__main__":
    print("Starting MCP Server...")
    print("Available tools:", [
        "health_check", "get_timestamp", "generate_hash", 
        "add", "subtract", "multiply", "divide", 
        "calculate_statistics", "format_json",
        "upload_document", "list_documents", "get_document",
        "download_document", "delete_document", "search_documents",
        "get_document_content_summary"
    ])
    
    # Always use SSE transport for better compatibility with HTTP clients
    print("Using SSE transport on port 3001")
    print("MCP endpoint: http://localhost:3001/sse")
    print("Test with MCP Inspector or HTTP clients")
    mcp.run(transport="sse")
