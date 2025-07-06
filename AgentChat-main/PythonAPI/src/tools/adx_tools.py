"""Azure Data Explorer (ADX) tools for MCP server."""

import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor

try:
    from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
    from azure.kusto.data.exceptions import KustoServiceError
    from azure.identity import DefaultAzureCredential
    ADX_AVAILABLE = True
except ImportError:
    ADX_AVAILABLE = False

# MCP tool definitions
ADX_TOOLS = [
    {
        "name": "adx_list_databases",
        "description": "List all databases in the Azure Data Explorer cluster",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "adx_list_tables",
        "description": "List all tables in a specific database",
        "inputSchema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Name of the database to list tables from"
                }
            },
            "required": ["database"]
        }
    },
    {
        "name": "adx_describe_table",
        "description": "Get schema information for a specific table",
        "inputSchema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Name of the database"
                },
                "table": {
                    "type": "string",
                    "description": "Name of the table to describe"
                }
            },
            "required": ["database", "table"]
        }
    },
    {
        "name": "adx_execute_query",
        "description": "Execute a KQL query against Azure Data Explorer",
        "inputSchema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Name of the database to query"
                },
                "query": {
                    "type": "string",
                    "description": "KQL query to execute"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of rows to return (default: 100)",
                    "default": 100
                }
            },
            "required": ["database", "query"]
        }
    },
    {
        "name": "adx_get_cluster_info",
        "description": "Get information about the ADX cluster",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]

class ADXManager:
    """Manager for Azure Data Explorer operations."""
    
    def __init__(self):
        self.cluster_url = os.getenv("ADX_CLUSTER_URL")
        self.client = None
        self.credential = None
        self._executor = ThreadPoolExecutor(max_workers=2)
        
    def _get_client(self) -> Optional[KustoClient]:
        """Get or create ADX client."""
        if not ADX_AVAILABLE:
            raise Exception("Azure Data Explorer SDK not available. Install with: pip install azure-kusto-data")
        
        if not self.cluster_url:
            raise Exception("ADX_CLUSTER_URL environment variable not set")
        
        if not self.client:
            try:
                # Use DefaultAzureCredential for authentication
                self.credential = DefaultAzureCredential()
                kcsb = KustoConnectionStringBuilder.with_azure_token_credential(
                    self.cluster_url, 
                    self.credential
                )
                self.client = KustoClient(kcsb)
            except Exception as e:
                raise Exception(f"Failed to create ADX client: {str(e)}")
        
        return self.client
    
    def _execute_sync_query(self, database: str, query: str) -> Dict[str, Any]:
        """Execute a synchronous query."""
        client = self._get_client()
        try:
            response = client.execute(database, query)
            
            # Convert to JSON-serializable format
            results = []
            if response.primary_results and len(response.primary_results) > 0:
                primary_result = response.primary_results[0]
                columns = [col.column_name for col in primary_result.columns]
                
                for row in primary_result:
                    row_dict = {}
                    for i, value in enumerate(row):
                        # Handle datetime objects
                        if isinstance(value, datetime):
                            row_dict[columns[i]] = value.isoformat()
                        else:
                            row_dict[columns[i]] = value
                    results.append(row_dict)
            
            return {
                "success": True,
                "data": results,
                "row_count": len(results),
                "columns": columns if results else []
            }
            
        except KustoServiceError as e:
            return {
                "success": False,
                "error": f"Kusto service error: {str(e)}",
                "error_code": getattr(e, 'http_response_code', 'unknown')
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Query execution error: {str(e)}"
            }
    
    async def execute_query(self, database: str, query: str, limit: int = 100) -> Dict[str, Any]:
        """Execute a KQL query asynchronously."""
        # Add limit to query if not already present
        if limit and "take" not in query.lower() and "limit" not in query.lower():
            query = f"{query} | take {limit}"
        
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, 
            self._execute_sync_query, 
            database, 
            query
        )
    
    async def list_databases(self) -> Dict[str, Any]:
        """List all databases in the cluster."""
        query = ".show databases"
        return await self.execute_query("", query)
    
    async def list_tables(self, database: str) -> Dict[str, Any]:
        """List all tables in a database."""
        query = ".show tables"
        return await self.execute_query(database, query)
    
    async def describe_table(self, database: str, table: str) -> Dict[str, Any]:
        """Get schema information for a table."""
        query = f".show table {table} schema as json"
        return await self.execute_query(database, query)
    
    async def get_cluster_info(self) -> Dict[str, Any]:
        """Get cluster information."""
        if not self.cluster_url:
            return {
                "success": False,
                "error": "ADX_CLUSTER_URL not configured"
            }
        
        return {
            "success": True,
            "cluster_url": self.cluster_url,
            "status": "connected" if self.client else "not_connected",
            "authentication": "DefaultAzureCredential"
        }

# Global ADX manager instance
_adx_manager = ADXManager()

# Direct implementation functions for MCP client
async def adx_list_databases_impl() -> str:
    """List all databases in the ADX cluster."""
    try:
        result = await _adx_manager.list_databases()
        if result["success"]:
            databases = [row.get("DatabaseName", "") for row in result["data"]]
            return json.dumps({
                "success": True,
                "databases": databases,
                "count": len(databases)
            }, indent=2)
        else:
            return json.dumps({
                "success": False,
                "error": result["error"]
            }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Failed to list databases: {str(e)}"
        }, indent=2)

async def adx_list_tables_impl(database: str, session_id: str = None) -> str:
    """List all tables in a database."""
    # Get a logger
    import logging
    logger = logging.getLogger(__name__)
    
    # Import SSE emitter if available
    try:
        from utils.sse_emitter import sse_emitter
        from flask import has_app_context
        sse_available = True
    except ImportError:
        sse_available = False
        
    # Log the operation for debugging
    logger.info(f"📋 ADX LIST TABLES: Database: {database}")
    
    # Emit event if SSE is available
    if sse_available and session_id and has_app_context():
        try:
            sse_emitter.emit_agent_activity(
                session_id=session_id,
                agent_name="ADX Agent",
                action="Listing database tables",
                status="in-progress",
                details=f"Getting tables in database '{database}'"
            )
        except Exception as emit_error:
            logger.warning(f"Failed to emit ADX list tables activity: {str(emit_error)}")
    
    try:
        result = await _adx_manager.list_tables(database)
        
        if result["success"]:
            tables = [row.get("TableName", "") for row in result["data"]]
            table_count = len(tables)
            logger.info(f"✅ ADX LIST TABLES SUCCESS: Found {table_count} tables in {database}")
            
            # Emit successful event if SSE is available
            if sse_available and session_id and has_app_context():
                try:
                    # Format table list for display
                    table_list = ", ".join(tables[:5])
                    if table_count > 5:
                        table_list += f" and {table_count - 5} more"
                    
                    sse_emitter.emit_agent_activity(
                        session_id=session_id,
                        agent_name="ADX Agent",
                        action="Listed database tables",
                        status="completed",
                        details=f"Found {table_count} tables in database '{database}'{': ' + table_list if table_count > 0 else ''}"
                    )
                except Exception as emit_error:
                    logger.warning(f"Failed to emit ADX list tables success: {str(emit_error)}")
            
            return json.dumps({
                "success": True,
                "database": database,
                "tables": tables,
                "count": table_count
            }, indent=2)
        else:
            error_msg = result.get("error", "Unknown error")
            logger.error(f"❌ ADX LIST TABLES ERROR: {error_msg}")
            
            # Emit error event if SSE is available
            if sse_available and session_id and has_app_context():
                try:
                    sse_emitter.emit_agent_activity(
                        session_id=session_id,
                        agent_name="ADX Agent",
                        action="List tables failed",
                        status="error",
                        details=f"Error listing tables in '{database}': {error_msg}"
                    )
                except Exception as emit_error:
                    logger.warning(f"Failed to emit ADX list tables error: {str(emit_error)}")
            
            return json.dumps({
                "success": False,
                "error": error_msg
            }, indent=2)
    except Exception as e:
        error_msg = f"Failed to list tables: {str(e)}"
        logger.error(f"❌ ADX LIST TABLES EXCEPTION: {error_msg}")
        
        # Emit exception event if SSE is available
        if sse_available and session_id and has_app_context():
            try:
                sse_emitter.emit_agent_activity(
                    session_id=session_id,
                    agent_name="ADX Agent",
                    action="List tables error",
                    status="error",
                    details=f"Exception: {error_msg}"
                )
            except Exception as emit_error:
                logger.warning(f"Failed to emit ADX list tables exception: {str(emit_error)}")
        
        return json.dumps({
            "success": False,
            "error": error_msg
        }, indent=2)

async def adx_describe_table_impl(database: str, table: str) -> str:
    """Get schema information for a table."""
    try:
        result = await _adx_manager.describe_table(database, table)
        if result["success"]:
            return json.dumps({
                "success": True,
                "database": database,
                "table": table,
                "schema": result["data"]
            }, indent=2)
        else:
            return json.dumps({
                "success": False,
                "error": result["error"]
            }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Failed to describe table: {str(e)}"
        }, indent=2)

async def adx_execute_query_impl(database: str, query: str, limit: int = 100, session_id: str = None) -> str:
    """Execute a KQL query."""
    # Get a logger
    import logging
    logger = logging.getLogger(__name__)
    
    # Import SSE emitter if available
    try:
        from utils.sse_emitter import sse_emitter
        from flask import has_app_context
        sse_available = True
    except ImportError:
        sse_available = False
        
    # Log the query for debugging
    logger.info(f"🔍 ADX QUERY: Database: {database}, Query: {query}")
    
    # Emit event if SSE is available
    if sse_available and session_id and has_app_context():
        try:
            sse_emitter.emit_agent_activity(
                session_id=session_id,
                agent_name="ADX Agent",
                action="Executing database query",
                status="in-progress",
                details=f"Querying database '{database}'"
            )
        except Exception as emit_error:
            logger.warning(f"Failed to emit ADX query activity: {str(emit_error)}")
    
    try:
        result = await _adx_manager.execute_query(database, query, limit)
        
        if result["success"]:
            row_count = result.get("row_count", 0)
            logger.info(f"✅ ADX QUERY SUCCESS: Retrieved {row_count} rows")
            
            # Emit successful query event if SSE is available
            if sse_available and session_id and has_app_context():
                try:
                    sse_emitter.emit_agent_activity(
                        session_id=session_id,
                        agent_name="ADX Agent",
                        action="Query executed successfully",
                        status="completed",
                        details=f"Retrieved {row_count} rows from database '{database}'"
                    )
                except Exception as emit_error:
                    logger.warning(f"Failed to emit ADX query success: {str(emit_error)}")
            
            return json.dumps({
                "success": True,
                "database": database,
                "query": query,
                "results": result["data"],
                "row_count": result["row_count"],
                "columns": result["columns"]
            }, indent=2)
        else:
            error_msg = result.get("error", "Unknown error")
            logger.error(f"❌ ADX QUERY ERROR: {error_msg}")
            
            # Emit error event if SSE is available
            if sse_available and session_id and has_app_context():
                try:
                    sse_emitter.emit_agent_activity(
                        session_id=session_id,
                        agent_name="ADX Agent",
                        action="Query execution failed",
                        status="error",
                        details=f"Error querying '{database}': {error_msg}"
                    )
                except Exception as emit_error:
                    logger.warning(f"Failed to emit ADX query error: {str(emit_error)}")
                    
            return json.dumps({
                "success": False,
                "error": error_msg,
                "query": query
            }, indent=2)
    except Exception as e:
        error_msg = f"Failed to execute query: {str(e)}"
        logger.error(f"❌ ADX QUERY EXCEPTION: {error_msg}")
        
        # Emit exception event if SSE is available
        if sse_available and session_id and has_app_context():
            try:
                sse_emitter.emit_agent_activity(
                    session_id=session_id,
                    agent_name="ADX Agent",
                    action="Query execution error",
                    status="error",
                    details=f"Exception: {error_msg}"
                )
            except Exception as emit_error:
                logger.warning(f"Failed to emit ADX query exception: {str(emit_error)}")
                
        return json.dumps({
            "success": False,
            "error": error_msg,
            "query": query
        }, indent=2)

async def adx_get_cluster_info_impl() -> str:
    """Get cluster information."""
    try:
        result = await _adx_manager.get_cluster_info()
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Failed to get cluster info: {str(e)}"
        }, indent=2)

# MCP tool handlers
async def handle_adx_list_databases(arguments: Dict[str, Any]) -> str:
    """Handle adx_list_databases tool call."""
    return await adx_list_databases_impl()

async def handle_adx_list_tables(arguments: Dict[str, Any]) -> str:
    """Handle adx_list_tables tool call."""
    database = arguments.get("database", "")
    session_id = arguments.get("session_id", None)  # Get session_id if provided
    
    if not database:
        return json.dumps({"success": False, "error": "Database name is required"})
    
    # Pass session_id if available
    return await adx_list_tables_impl(database, session_id)

async def handle_adx_describe_table(arguments: Dict[str, Any]) -> str:
    """Handle adx_describe_table tool call."""
    database = arguments.get("database", "")
    table = arguments.get("table", "")
    if not database or not table:
        return json.dumps({"success": False, "error": "Database and table names are required"})
    return await adx_describe_table_impl(database, table)

async def handle_adx_execute_query(arguments: Dict[str, Any]) -> str:
    """Handle adx_execute_query tool call."""
    database = arguments.get("database", "")
    query = arguments.get("query", "")
    limit = arguments.get("limit", 100)
    session_id = arguments.get("session_id", None)  # Get session_id if provided
    
    if not database or not query:
        return json.dumps({"success": False, "error": "Database and query are required"})
    
    return await adx_execute_query_impl(database, query, limit, session_id)

async def handle_adx_get_cluster_info(arguments: Dict[str, Any]) -> str:
    """Handle adx_get_cluster_info tool call."""
    return await adx_get_cluster_info_impl()

# Tool handlers mapping
ADX_TOOL_HANDLERS = {
    "adx_list_databases": handle_adx_list_databases,
    "adx_list_tables": handle_adx_list_tables,
    "adx_describe_table": handle_adx_describe_table,
    "adx_execute_query": handle_adx_execute_query,
    "adx_get_cluster_info": handle_adx_get_cluster_info
}

def register_adx_tools(mcp):
    """Register all ADX tools with the MCP server."""
    
    @mcp.tool()
    async def adx_list_databases() -> str:
        """List all databases in the Azure Data Explorer cluster."""
        return await handle_adx_list_databases({})
    
    @mcp.tool()
    async def adx_list_tables(database: str) -> str:
        """List all tables in a specific database."""
        return await handle_adx_list_tables({"database": database})
    
    @mcp.tool()
    async def adx_describe_table(database: str, table: str) -> str:
        """Get schema information for a specific table."""
        return await handle_adx_describe_table({"database": database, "table": table})
    
    @mcp.tool()
    async def adx_execute_query(database: str, query: str, limit: int = 100) -> str:
        """Execute a KQL query against Azure Data Explorer."""
        return await handle_adx_execute_query({"database": database, "query": query, "limit": limit})
    
    @mcp.tool()
    async def adx_get_cluster_info() -> str:
        """Get information about the ADX cluster."""
        return await handle_adx_get_cluster_info({})
