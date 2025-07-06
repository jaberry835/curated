"""Semantic Kernel wrapper functions for MCP tools."""

from typing import Annotated
from semantic_kernel.functions import kernel_function
from src.agents.mcp_client import MCPClient


class MCPFunctionWrapper:
    """Wrapper to convert MCP tools to Semantic Kernel functions."""
    
    def __init__(self, mcp_client: MCPClient):
        self.mcp_client = mcp_client
    
    def create_math_functions(self):
        """Create Semantic Kernel functions for math tools."""
        
        @kernel_function(name="add", description="Add two numbers")
        async def add(
            a: Annotated[float, "First number"],
            b: Annotated[float, "Second number"]
        ) -> Annotated[str, "The sum of the two numbers"]:
            return await self.mcp_client.call_tool("add", {"a": a, "b": b})
        
        @kernel_function(name="subtract", description="Subtract two numbers")
        async def subtract(
            a: Annotated[float, "First number"],
            b: Annotated[float, "Second number"]
        ) -> Annotated[str, "The difference of the two numbers"]:
            return await self.mcp_client.call_tool("subtract", {"a": a, "b": b})
        
        @kernel_function(name="multiply", description="Multiply two numbers")
        async def multiply(
            a: Annotated[float, "First number"],
            b: Annotated[float, "Second number"]
        ) -> Annotated[str, "The product of the two numbers"]:
            return await self.mcp_client.call_tool("multiply", {"a": a, "b": b})
        
        @kernel_function(name="divide", description="Divide two numbers")
        async def divide(
            a: Annotated[float, "First number (dividend)"],
            b: Annotated[float, "Second number (divisor)"]
        ) -> Annotated[str, "The quotient of the two numbers"]:
            return await self.mcp_client.call_tool("divide", {"a": a, "b": b})
        
        @kernel_function(name="calculate_statistics", description="Calculate statistics for a list of numbers")
        async def calculate_statistics(
            numbers: Annotated[str, "Comma-separated list of numbers"]
        ) -> Annotated[str, "Statistical analysis of the numbers"]:
            # Convert comma-separated string to list of floats
            try:
                number_list = [float(x.strip()) for x in numbers.split(",")]
                return await self.mcp_client.call_tool("calculate_statistics", {"numbers": number_list})
            except ValueError:
                return "Error: Please provide numbers separated by commas"
        
        return [add, subtract, multiply, divide, calculate_statistics]
    
    def create_utility_functions(self):
        """Create Semantic Kernel functions for utility tools."""
        
        @kernel_function(name="health_check", description="Check the health status of the MCP server")
        async def health_check() -> Annotated[str, "Health status information"]:
            return await self.mcp_client.call_tool("health_check", {})
        
        @kernel_function(name="get_timestamp", description="Get current UTC timestamp")
        async def get_timestamp() -> Annotated[str, "Current timestamp in ISO format"]:
            return await self.mcp_client.call_tool("get_timestamp", {})
        
        @kernel_function(name="generate_hash", description="Generate hash for text")
        async def generate_hash(
            text: Annotated[str, "Text to hash"],
            algorithm: Annotated[str, "Hash algorithm (md5, sha1, sha256, sha512)"] = "sha256"
        ) -> Annotated[str, "Hash information"]:
            return await self.mcp_client.call_tool("generate_hash", {"text": text, "algorithm": algorithm})
        
        @kernel_function(name="format_json", description="Validate and format JSON data")
        async def format_json(
            json_string: Annotated[str, "JSON string to format"],
            indent: Annotated[int, "Indentation level"] = 2
        ) -> Annotated[str, "Formatted JSON result"]:
            return await self.mcp_client.call_tool("format_json", {"json_string": json_string, "indent": indent})
        
        return [health_check, get_timestamp, generate_hash, format_json]
    
    def create_adx_functions(self):
        """Create Semantic Kernel functions for Azure Data Explorer tools."""
        
        @kernel_function(name="adx_list_databases", description="List all databases in the Azure Data Explorer cluster")
        async def adx_list_databases() -> Annotated[str, "List of databases in JSON format"]:
            return await self.mcp_client.call_tool("adx_list_databases", {})
        
        @kernel_function(name="adx_list_tables", description="List all tables in a specific database")
        async def adx_list_tables(
            database: Annotated[str, "Name of the database to list tables from"]
        ) -> Annotated[str, "List of tables in JSON format"]:
            return await self.mcp_client.call_tool("adx_list_tables", {"database": database})
        
        @kernel_function(name="adx_describe_table", description="Get schema information for a specific table")
        async def adx_describe_table(
            database: Annotated[str, "Name of the database"],
            table: Annotated[str, "Name of the table to describe"]
        ) -> Annotated[str, "Table schema information in JSON format"]:
            return await self.mcp_client.call_tool("adx_describe_table", {"database": database, "table": table})
        
        @kernel_function(name="adx_execute_query", description="Execute a KQL query against Azure Data Explorer")
        async def adx_execute_query(
            database: Annotated[str, "Name of the database to query"],
            query: Annotated[str, "KQL query to execute"],
            limit: Annotated[int, "Maximum number of rows to return (default: 100)"] = 100
        ) -> Annotated[str, "Query results in JSON format"]:
            return await self.mcp_client.call_tool("adx_execute_query", {"database": database, "query": query, "limit": limit})
        
        @kernel_function(name="adx_get_cluster_info", description="Get information about the ADX cluster")
        async def adx_get_cluster_info() -> Annotated[str, "Cluster information in JSON format"]:
            return await self.mcp_client.call_tool("adx_get_cluster_info", {})
        
        return [adx_list_databases, adx_list_tables, adx_describe_table, adx_execute_query, adx_get_cluster_info]
    
    def create_document_functions(self):
        """Create Semantic Kernel functions for document management tools."""
        
        @kernel_function(name="list_documents", description="List documents in Azure Blob Storage or filter by prefix")
        async def list_documents(
            limit: Annotated[int, "Maximum number of documents to return"] = 50,
            prefix: Annotated[str, "Optional prefix to filter documents by filename"] = None
        ) -> Annotated[str, "List of documents in JSON format"]:
            params = {"limit": limit}
            if prefix:
                params["prefix"] = prefix
            return await self.mcp_client.call_tool("list_documents", params)
        
        @kernel_function(name="get_document", description="Get document metadata from Azure Blob Storage")
        async def get_document(
            document_id: Annotated[str, "The ID (blob name) of the document"]
        ) -> Annotated[str, "Document metadata in JSON format"]:
            return await self.mcp_client.call_tool("get_document", {"document_id": document_id})
        
        @kernel_function(name="delete_document", description="Delete a document from Azure Blob Storage")
        async def delete_document(
            document_id: Annotated[str, "The ID (blob name) of the document to delete"]
        ) -> Annotated[str, "Deletion result in JSON format"]:
            return await self.mcp_client.call_tool("delete_document", {"document_id": document_id})
        
        @kernel_function(name="search_documents", description="Search documents using Azure AI Search by content or filename. Returns document IDs needed for retrieval.")
        async def search_documents(
            query: Annotated[str, "Search query string - can be text content to find or a filename to search for"],
            limit: Annotated[int, "Maximum number of results to return"] = 10
        ) -> Annotated[str, "Search results with document IDs needed for subsequent get_document_content_summary calls. Extract documentId from the results array."]:
            # For the agent, we don't need to provide user_id and session_id, as these will be handled server-side
            return await self.mcp_client.call_tool("search_documents", {"query": query, "limit": limit})
        
        @kernel_function(name="get_document_content_summary", description="Get a summary of document content using the document ID (required) from search_documents results")
        async def get_document_content_summary(
            document_id: Annotated[str, "The ID of the document (must be obtained from the documentId field in search_documents results)"],
            max_length: Annotated[int, "Maximum length of content summary"] = 500
        ) -> Annotated[str, "Document content summary in JSON format with the actual content of the document"]:
            return await self.mcp_client.call_tool("get_document_content_summary", {"document_id": document_id, "max_length": max_length})
        
        return [list_documents, get_document, delete_document, search_documents, get_document_content_summary]
