"""Utility tools for the MCP server."""

def register_utility_tools(mcp):
    """Register all utility tools with the MCP server."""
    
    @mcp.tool()
    def health_check() -> dict:
        """Check the health and status of the MCP server."""
        import datetime
        return {
            "status": "healthy",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "version": "1.0.0",
            "server": "PythonAPI MCP Server"
        }

    @mcp.tool()
    def get_timestamp() -> str:
        """Get the current UTC timestamp in ISO format."""
        import datetime
        return datetime.datetime.utcnow().isoformat()

    @mcp.tool()
    def generate_hash(text: str, algorithm: str = "sha256") -> dict:
        """Generate a hash for the given text using the specified algorithm."""
        import hashlib
        
        valid_algorithms = ["md5", "sha1", "sha256", "sha512"]
        if algorithm not in valid_algorithms:
            raise ValueError(f"Invalid algorithm. Choose from: {valid_algorithms}")
        
        hash_obj = hashlib.new(algorithm)
        hash_obj.update(text.encode('utf-8'))
        hash_value = hash_obj.hexdigest()
        
        return {
            "original_text": text,
            "algorithm": algorithm,
            "hash": hash_value
        }

    @mcp.tool()
    def format_json(json_string: str, indent: int = 2) -> dict:
        """Validate and format JSON data."""
        import json
        
        try:
            # Parse JSON to validate
            parsed_data = json.loads(json_string)
            
            # Format with specified indentation
            formatted_json = json.dumps(parsed_data, indent=indent, ensure_ascii=False)
            
            return {
                "valid": True,
                "formatted_json": formatted_json,
                "size": len(formatted_json),
                "message": "JSON is valid and formatted successfully"
            }
        
        except json.JSONDecodeError as e:
            return {
                "valid": False,
                "error": str(e),
                "message": "Invalid JSON format"
            }

# Implementation functions for direct calling
def health_check_impl() -> dict:
    """Implementation function for health check."""
    import datetime
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "server": "PythonAPI MCP Server"
    }

def get_timestamp_impl() -> str:
    """Implementation function for getting timestamp."""
    import datetime
    return datetime.datetime.utcnow().isoformat()

def generate_hash_impl(text: str, algorithm: str = "sha256") -> dict:
    """Implementation function for generating hash."""
    import hashlib
    
    valid_algorithms = ["md5", "sha1", "sha256", "sha512"]
    if algorithm not in valid_algorithms:
        raise ValueError(f"Invalid algorithm. Choose from: {valid_algorithms}")
    
    hash_obj = hashlib.new(algorithm)
    hash_obj.update(text.encode('utf-8'))
    hash_value = hash_obj.hexdigest()
    
    return {
        "original_text": text,
        "algorithm": algorithm,
        "hash": hash_value
    }

def format_json_impl(json_string: str, indent: int = 2, session_id: str = None) -> dict:
    """Implementation function for formatting JSON."""
    import json
    import logging
    logger = logging.getLogger(__name__)
    
    # Import SSE emitter if available
    try:
        from utils.sse_emitter import sse_emitter
        from flask import has_app_context
        sse_available = True
    except ImportError:
        sse_available = False
        
    logger.info(f"🔧 FORMAT JSON: Formatting {len(json_string) if json_string else 0} chars of JSON")
    
    try:
        # Parse JSON to validate
        parsed_data = json.loads(json_string)
        
        # Format with specified indentation
        formatted_json = json.dumps(parsed_data, indent=indent, ensure_ascii=False)
        
        # Emit success event if SSE is available
        if sse_available and session_id and has_app_context():
            try:
                sse_emitter.emit_agent_activity(
                    session_id=session_id,
                    agent_name="Utility Agent",
                    action="JSON formatting complete",
                    status="completed",
                    details=f"Successfully formatted {len(json_string)} chars of JSON data"
                )
            except Exception as emit_error:
                logger.warning(f"Failed to emit JSON formatting activity: {str(emit_error)}")
        
        return {
            "valid": True,
            "formatted_json": formatted_json,
            "size": len(formatted_json),
            "message": "JSON is valid and formatted successfully"
        }
    
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON format: {str(e)}"
        logger.error(f"❌ JSON FORMAT ERROR: {error_msg}")
        
        # Emit error event if SSE is available
        if sse_available and session_id and has_app_context():
            try:
                sse_emitter.emit_agent_activity(
                    session_id=session_id,
                    agent_name="Utility Agent",
                    action="JSON formatting failed",
                    status="error",
                    details=error_msg
                )
            except Exception as emit_error:
                logger.warning(f"Failed to emit JSON error activity: {str(emit_error)}")
        
        return {
            "valid": False,
            "error": str(e),
            "message": "Invalid JSON format"
        }
