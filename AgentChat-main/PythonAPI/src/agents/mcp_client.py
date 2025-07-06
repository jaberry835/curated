"""MCP Client for Semantic Kernel integration - Direct function calls."""

import asyncio
import json
from typing import List, Optional, Dict, Any
import hashlib
from datetime import datetime, timezone
import statistics
from pathlib import Path
import sys

# Import our tool modules directly
try:
    from src.tools.utility_tools import health_check_impl, get_timestamp_impl, generate_hash_impl, format_json_impl
    from src.tools.math_tools import add_impl, subtract_impl, multiply_impl, divide_impl, calculate_statistics_impl
    from src.tools.adx_tools import (
        adx_list_databases_impl, adx_list_tables_impl, adx_describe_table_impl, 
        adx_execute_query_impl, adx_get_cluster_info_impl
    )
    from src.tools.document_tools import (
        list_documents_impl, get_document_metadata_impl, download_document_impl,
        search_documents_impl, get_document_content_summary_impl
    )
except ImportError as e:
    print(f"❌ Failed to import tool modules: {e}")


class MCPClient:
    """MCP Client that directly calls tool functions."""
    
    def __init__(self, server_url: str = "http://localhost:3001", user_id: str = None, session_id: str = None):
        """Initialize MCP client.
        
        Args:
            server_url: URL of the MCP server
            user_id: User ID for document access control
            session_id: Session ID for context
        """
        self.server_url = server_url
        self.tools = []
        self.connected = False
        self.user_id = user_id
        self.session_id = session_id
        
        # Tool implementations mapping
        self.tool_functions = {
            "health_check": health_check_impl,
            "get_timestamp": get_timestamp_impl,
            "generate_hash": generate_hash_impl,
            "format_json": format_json_impl,
            "add": add_impl,
            "subtract": subtract_impl,
            "multiply": multiply_impl,
            "divide": divide_impl,
            "calculate_statistics": calculate_statistics_impl,
            "adx_list_databases": adx_list_databases_impl,
            "adx_list_tables": adx_list_tables_impl,
            "adx_describe_table": adx_describe_table_impl,
            "adx_execute_query": adx_execute_query_impl,
            "adx_get_cluster_info": adx_get_cluster_info_impl,
            # Document tools
            "list_documents": list_documents_impl,
            "get_document_metadata": get_document_metadata_impl,
            "download_document": download_document_impl,
            "search_documents": search_documents_impl,
            "get_document_content_summary": get_document_content_summary_impl,
            # Additional document tools that might be implemented in the future
            "delete_document": None,
            "process_document": None
        }
        
    async def connect(self) -> bool:
        """Connect to the MCP server (or simulate connection)."""
        try:
            # Initialize tools list
            await self._fetch_tools()
            
            self.connected = True
            print(f"✅ Connected to MCP tools. Available tools: {[tool['name'] for tool in self.tools]}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to initialize MCP client: {str(e)}")
            return False
    
    async def _fetch_tools(self):
        """Fetch the list of available tools."""
        self.tools = [
            {"name": "health_check", "description": "Check the health and status of the MCP server"},
            {"name": "get_timestamp", "description": "Get the current UTC timestamp"},
            {"name": "generate_hash", "description": "Generate a hash for the given text"},
            {"name": "add", "description": "Add two numbers"},
            {"name": "subtract", "description": "Subtract two numbers"},
            {"name": "multiply", "description": "Multiply two numbers"},
            {"name": "divide", "description": "Divide two numbers"},
            {"name": "calculate_statistics", "description": "Calculate comprehensive statistics for a list of numbers"},
            {"name": "format_json", "description": "Validate and format JSON data"},
            {"name": "adx_list_databases", "description": "List all databases in the Azure Data Explorer cluster"},
            {"name": "adx_list_tables", "description": "List all tables in a specific database"},
            {"name": "adx_describe_table", "description": "Get schema information for a specific table"},
            {"name": "adx_execute_query", "description": "Execute a KQL query against Azure Data Explorer"},
            {"name": "adx_get_cluster_info", "description": "Get information about the ADX cluster"}
        ]
    
    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call an MCP tool directly."""
        import logging
        logger = logging.getLogger(__name__)
        from utils.sse_emitter import sse_emitter
        from flask import has_app_context
        
        if not self.connected:
            raise RuntimeError("Not connected to MCP server")
        
        try:
            if tool_name not in self.tool_functions:
                error_msg = f"Error: Tool '{tool_name}' not found"
                logger.error(f"🛑 MCP CLIENT ERROR: {error_msg}")
                return error_msg
            # For document tools, inject user_id and session_id if not provided
            document_tools = ["list_documents", "search_documents", "get_document_content_summary", 
                             "get_document_metadata", "download_document", "delete_document"]
            
            # ADX tools for emitting events
            adx_tools = ["adx_list_databases", "adx_list_tables", "adx_describe_table", 
                        "adx_execute_query", "adx_get_cluster_info"]
                        
            # Math tools for emitting events
            math_tools = ["add", "subtract", "multiply", "divide", "calculate_statistics"]
            
            # Utility tools for emitting events
            utility_tools = ["health_check", "get_timestamp", "generate_hash", "format_json"]
            
            # Document tools specific injection and events
            if tool_name in document_tools:
                # Only inject if not already provided in arguments
                if 'user_id' not in arguments and self.user_id:
                    arguments['user_id'] = self.user_id
                    logger.info(f"🔑 Injecting user_id: {self.user_id} for tool: {tool_name}")
                
                if 'session_id' not in arguments and self.session_id:
                    arguments['session_id'] = self.session_id
                    logger.info(f"🔑 Injecting session_id: {self.session_id} for tool: {tool_name}")
                
                # Emit SSE event for document tool usage if we have session_id
                if hasattr(self, 'session_id') and self.session_id and has_app_context():
                    try:
                        # Create a friendlier description of what's happening
                        action_desc = f"Using tool: {tool_name}"
                        details = "Working with documents"
                        
                        if tool_name == "search_documents":
                            action_desc = "Searching for documents"
                            query = arguments.get("query", "")
                            details = f"Searching for '{query}'"
                        elif tool_name == "get_document_content_summary":
                            action_desc = "Retrieving document content"
                            doc_id = arguments.get("document_id", "")
                            details = f"Getting content for document: {doc_id}"
                        
                        agent_name = "Document Agent"
                        sse_emitter.emit_agent_activity(
                            session_id=self.session_id,
                            agent_name=agent_name,
                            action=action_desc,
                            status="in-progress",
                            details=details
                        )
                    except Exception as emit_error:
                        logger.warning(f"Failed to emit document tool activity: {str(emit_error)}")
            
            # ADX tools specific events and session_id injection
            elif tool_name in adx_tools:
                # Inject session_id if not already provided in arguments
                if hasattr(self, 'session_id') and self.session_id and 'session_id' not in arguments:
                    arguments['session_id'] = self.session_id
                    logger.info(f"🔑 Injecting session_id: {self.session_id} for tool: {tool_name}")
                
                # Emit initial event
                if hasattr(self, 'session_id') and self.session_id and has_app_context():
                    try:
                        action_desc = f"Using tool: {tool_name}"
                        details = "Working with database"
                        
                        if tool_name == "adx_list_databases":
                            action_desc = "Listing databases"
                            details = "Retrieving all databases from ADX cluster"
                        elif tool_name == "adx_list_tables":
                            action_desc = "Listing tables"
                            database = arguments.get("database", "")
                            details = f"Retrieving tables from database: {database}"
                        elif tool_name == "adx_describe_table":
                            action_desc = "Describing table schema"
                            database = arguments.get("database", "")
                            table = arguments.get("table", "")
                            details = f"Getting schema for table: {table} in database: {database}"
                        elif tool_name == "adx_execute_query":
                            action_desc = "Executing database query"
                            database = arguments.get("database", "")
                            query = arguments.get("query", "")
                            query_preview = query[:50] + "..." if len(query) > 50 else query
                            details = f"Querying database: {database} with: {query_preview}"
                        
                        agent_name = "ADX Agent"
                        sse_emitter.emit_agent_activity(
                            session_id=self.session_id,
                            agent_name=agent_name,
                            action=action_desc,
                            status="in-progress",
                            details=details
                        )
                    except Exception as emit_error:
                        logger.warning(f"Failed to emit ADX tool activity: {str(emit_error)}")
                        
            # Math tools specific events and session_id injection
            elif tool_name in math_tools:
                # Inject session_id if not already provided in arguments
                if hasattr(self, 'session_id') and self.session_id and 'session_id' not in arguments:
                    arguments['session_id'] = self.session_id
                    logger.info(f"🔑 Injecting session_id: {self.session_id} for tool: {tool_name}")
                
                # Emit initial event
                if hasattr(self, 'session_id') and self.session_id and has_app_context():
                    try:
                        action_desc = "Performing calculation"
                        details = f"Using {tool_name} operation"
                        
                        if tool_name == "calculate_statistics":
                            numbers_count = len(arguments.get("numbers", []))
                            details = f"Calculating statistics for {numbers_count} numbers"
                            
                        agent_name = "Math Agent"
                        sse_emitter.emit_agent_activity(
                            session_id=self.session_id,
                            agent_name=agent_name,
                            action=action_desc,
                            status="in-progress",
                            details=details
                        )
                    except Exception as emit_error:
                        logger.warning(f"Failed to emit math tool activity: {str(emit_error)}")
                        
            # Utility tools specific events and session_id injection
            elif tool_name in utility_tools:
                # Inject session_id if not already provided in arguments
                if hasattr(self, 'session_id') and self.session_id and 'session_id' not in arguments:
                    arguments['session_id'] = self.session_id
                    logger.info(f"🔑 Injecting session_id: {self.session_id} for tool: {tool_name}")
                
                # Emit initial event
                if hasattr(self, 'session_id') and self.session_id and has_app_context():
                    try:
                        action_desc = "Using utility function"
                        details = f"Running {tool_name}"
                        
                        if tool_name == "generate_hash":
                            algorithm = arguments.get("algorithm", "sha256")
                            details = f"Generating {algorithm} hash"
                        elif tool_name == "format_json":
                            details = "Formatting and validating JSON data"
                            
                        agent_name = "Utility Agent"
                        sse_emitter.emit_agent_activity(
                            session_id=self.session_id,
                            agent_name=agent_name,
                            action=action_desc,
                            status="in-progress",
                            details=details
                        )
                    except Exception as emit_error:
                        logger.warning(f"Failed to emit utility tool activity: {str(emit_error)}")
            
            logger.info(f"🔧 MCP TOOL CALL: {tool_name} with args: {json.dumps(arguments)}")
            
            # Call the tool function directly
            func = self.tool_functions[tool_name]
            result = await func(**arguments) if asyncio.iscoroutinefunction(func) else func(**arguments)
            
            # Document tool specific logging for debugging
            if tool_name == "search_documents":
                if isinstance(result, dict):
                    count = result.get("count", 0)
                    results_array = result.get("results", [])
                    logger.info(f"🔍 MCP CLIENT: search_documents returned {count} results")
                    
                    # Emit SSE event with search results if we have session_id
                    if hasattr(self, 'session_id') and self.session_id and has_app_context():
                        try:
                            status = "completed" if count > 0 else "no-results"
                            details = f"Found {count} documents"
                            
                            # Add file names if results exist
                            if results_array and len(results_array) > 0:
                                file_names = [r.get("fileName", "unknown") for r in results_array[:3]]
                                file_list = ", ".join(file_names)
                                if len(results_array) > 3:
                                    file_list += f" and {len(results_array) - 3} more"
                                details = f"Found {count} documents: {file_list}"
                                logger.info(f"🔍 First document: {json.dumps(results_array[0], indent=2)[:200]}...")
                            else:
                                details = "No matching documents found"
                            
                            sse_emitter.emit_agent_activity(
                                session_id=self.session_id,
                                agent_name="Document Agent",
                                action="Document search results",
                                status=status,
                                details=details
                            )
                        except Exception as emit_error:
                            logger.warning(f"Failed to emit search results activity: {str(emit_error)}")
                    
                    if results_array and len(results_array) > 0:
                        logger.info(f"🔍 First document: {json.dumps(results_array[0], indent=2)[:200]}...")
            
            # Handle document content summary results
            if tool_name == "get_document_content_summary" and hasattr(self, 'session_id') and self.session_id and has_app_context():
                try:
                    doc_id = arguments.get("document_id", "unknown")
                    content_preview = str(result)
                    if len(content_preview) > 100:
                        content_preview = content_preview[:100] + "..."
                    
                    sse_emitter.emit_agent_activity(
                        session_id=self.session_id,
                        agent_name="Document Agent",
                        action="Retrieved document content",
                        status="completed",
                        details=f"Content from document {doc_id}: {content_preview}"
                    )
                except Exception as emit_error:
                    logger.warning(f"Failed to emit document content activity: {str(emit_error)}")
            
            # Handle ADX query results
            if tool_name == "adx_execute_query" and hasattr(self, 'session_id') and self.session_id and has_app_context():
                try:
                    database = arguments.get("database", "unknown")
                    result_obj = json.loads(result) if isinstance(result, str) else result
                    
                    success = result_obj.get("success", False) if isinstance(result_obj, dict) else False
                    row_count = result_obj.get("row_count", 0) if isinstance(result_obj, dict) else 0
                    
                    status = "completed" if success else "error"
                    details = f"Query returned {row_count} rows from database: {database}"
                    
                    if not success:
                        error_msg = result_obj.get("error", "Unknown error") if isinstance(result_obj, dict) else "Query failed"
                        details = f"Query error: {error_msg}"
                    
                    sse_emitter.emit_agent_activity(
                        session_id=self.session_id,
                        agent_name="ADX Agent",
                        action="Database query results",
                        status=status,
                        details=details
                    )
                except Exception as emit_error:
                    logger.warning(f"Failed to emit ADX query results activity: {str(emit_error)}")
            
            # Handle ADX table listing results
            if tool_name == "adx_list_tables" and hasattr(self, 'session_id') and self.session_id and has_app_context():
                try:
                    database = arguments.get("database", "unknown")
                    result_obj = json.loads(result) if isinstance(result, str) else result
                    
                    success = result_obj.get("success", False) if isinstance(result_obj, dict) else False
                    table_count = result_obj.get("count", 0) if isinstance(result_obj, dict) else 0
                    
                    status = "completed" if success else "error"
                    details = f"Found {table_count} tables in database: {database}"
                    
                    sse_emitter.emit_agent_activity(
                        session_id=self.session_id,
                        agent_name="ADX Agent",
                        action="Listed database tables",
                        status=status,
                        details=details
                    )
                except Exception as emit_error:
                    logger.warning(f"Failed to emit ADX table listing activity: {str(emit_error)}")
                    
            # Handle math calculation results
            if tool_name == "calculate_statistics" and hasattr(self, 'session_id') and self.session_id and has_app_context():
                try:
                    result_obj = json.loads(result) if isinstance(result, str) else result
                    status = "completed"
                    details = "Calculation completed"
                    
                    if isinstance(result_obj, dict):
                        if "mean" in result_obj and "median" in result_obj:
                            details = f"Stats calculated - Mean: {result_obj.get('mean')}, Median: {result_obj.get('median')}"
                    
                    sse_emitter.emit_agent_activity(
                        session_id=self.session_id,
                        agent_name="Math Agent",
                        action="Calculation results",
                        status=status,
                        details=details
                    )
                except Exception as emit_error:
                    logger.warning(f"Failed to emit math calculation activity: {str(emit_error)}")
            
            # Convert result to string if needed
            if isinstance(result, dict) or isinstance(result, list):
                return json.dumps(result, indent=2)
            else:
                return str(result)
                
        except Exception as e:
            error_msg = f"Error calling tool {tool_name}: {str(e)}"
            logger.error(f"🛑 MCP CLIENT ERROR: {error_msg}")
            return error_msg
    
    def get_tools_by_category(self, category: str) -> List:
        """Get tools filtered by category based on tool names."""
        if category == "math":
            math_tools = ["add", "subtract", "multiply", "divide", "calculate_statistics"]
            return [tool for tool in self.tools if tool["name"] in math_tools]
        elif category == "utility":
            utility_tools = ["health_check", "get_timestamp", "generate_hash", "format_json"]
            return [tool for tool in self.tools if tool["name"] in utility_tools]
        else:
            return self.tools
    
    async def disconnect(self):
        """Disconnect from the MCP server."""
        self.connected = False
        print("✅ MCP client disconnected")
