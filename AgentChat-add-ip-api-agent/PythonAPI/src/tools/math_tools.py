"""Mathematical tools for the MCP server."""

def register_math_tools(mcp):
    """Register all mathematical tools with the MCP server."""
    
    @mcp.tool()
    def add(a: float, b: float) -> float:
        """Add two numbers and return the result."""
        return a + b

    @mcp.tool()
    def subtract(a: float, b: float) -> float:
        """Subtract second number from first and return the result."""
        return a - b

    @mcp.tool()
    def multiply(a: float, b: float) -> float:
        """Multiply two numbers and return the result."""
        return a * b

    @mcp.tool()
    def divide(a: float, b: float) -> float:
        """Divide first number by second and return the result."""
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b

    @mcp.tool()
    def calculate_statistics(numbers: list[float]) -> dict:
        """Calculate comprehensive statistics for a list of numbers."""
        import statistics
        
        if not numbers:
            raise ValueError("Cannot calculate statistics for empty list")
        
        try:
            # Handle mode calculation which might raise StatisticsError
            try:
                mode_value = statistics.mode(numbers)
            except statistics.StatisticsError:
                mode_value = "No unique mode"
            
            return {
                "count": len(numbers),
                "mean": statistics.mean(numbers),
                "median": statistics.median(numbers),
                "mode": mode_value,
                "std_dev": statistics.stdev(numbers) if len(numbers) > 1 else 0.0,
                "variance": statistics.variance(numbers) if len(numbers) > 1 else 0.0,
                "min_value": min(numbers),
                "max_value": max(numbers)
            }
        except Exception as e:
            raise ValueError(f"Error calculating statistics: {str(e)}")

# Implementation functions for direct calling
def add_impl(a: float, b: float) -> float:
    """Implementation function for addition."""
    return a + b

def subtract_impl(a: float, b: float) -> float:
    """Implementation function for subtraction."""
    return a - b

def multiply_impl(a: float, b: float) -> float:
    """Implementation function for multiplication."""
    return a * b

def divide_impl(a: float, b: float) -> float:
    """Implementation function for division."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b

def calculate_statistics_impl(numbers: list, session_id: str = None) -> dict:
    """Implementation function for calculating statistics."""
    import statistics
    import logging
    logger = logging.getLogger(__name__)
    
    # Import SSE emitter if available
    try:
        from utils.sse_emitter import sse_emitter
        from flask import has_app_context
        sse_available = True
    except ImportError:
        sse_available = False
    
    logger.info(f"📊 CALCULATE STATISTICS: Processing {len(numbers) if numbers else 0} numbers")
    
    # Emit event if SSE is available
    if sse_available and session_id and has_app_context():
        try:
            sse_emitter.emit_agent_activity(
                session_id=session_id,
                agent_name="Math Agent",
                action="Calculating statistics",
                status="in-progress",
                details=f"Processing {len(numbers) if numbers else 0} values"
            )
        except Exception as emit_error:
            logger.warning(f"Failed to emit math statistics activity: {str(emit_error)}")
    
    if not numbers or not isinstance(numbers, list):
        error_msg = "Please provide a non-empty list of numbers"
        logger.error(f"❌ STATISTICS ERROR: {error_msg}")
        
        # Emit error if SSE is available
        if sse_available and session_id and has_app_context():
            try:
                sse_emitter.emit_agent_activity(
                    session_id=session_id,
                    agent_name="Math Agent",
                    action="Statistics calculation failed",
                    status="error",
                    details=error_msg
                )
            except Exception as emit_error:
                logger.warning(f"Failed to emit math error: {str(emit_error)}")
                
        raise ValueError(error_msg)
    
    try:
        # Convert all items to float
        float_numbers = [float(x) for x in numbers]
        
        if len(float_numbers) == 0:
            error_msg = "No valid numbers provided"
            logger.error(f"❌ STATISTICS ERROR: {error_msg}")
            
            # Emit error if SSE is available
            if sse_available and session_id and has_app_context():
                try:
                    sse_emitter.emit_agent_activity(
                        session_id=session_id,
                        agent_name="Math Agent",
                        action="Statistics calculation failed",
                        status="error",
                        details=error_msg
                    )
                except Exception as emit_error:
                    logger.warning(f"Failed to emit math error: {str(emit_error)}")
                    
            raise ValueError(error_msg)
        
        # Calculate mode (handle case where no unique mode exists)
        try:
            mode_value = statistics.mode(float_numbers)
        except statistics.StatisticsError:
            mode_value = None  # No unique mode
        
        # Calculate all statistics
        result = {
            "count": len(float_numbers),
            "mean": statistics.mean(float_numbers),
            "median": statistics.median(float_numbers),
            "mode": mode_value,
            "std_dev": statistics.stdev(float_numbers) if len(float_numbers) > 1 else 0.0,
            "variance": statistics.variance(float_numbers) if len(float_numbers) > 1 else 0.0,
            "min_value": min(float_numbers),
            "max_value": max(float_numbers)
        }
        
        logger.info(f"✅ STATISTICS SUCCESS: Calculated stats for {len(float_numbers)} numbers")
        
        # Emit completion event 
        if sse_available and session_id and has_app_context():
            try:
                details = f"Mean: {result['mean']:.2f}, Median: {result['median']:.2f}, Min: {result['min_value']:.2f}, Max: {result['max_value']:.2f}"
                
                sse_emitter.emit_agent_activity(
                    session_id=session_id,
                    agent_name="Math Agent",
                    action="Statistics calculation complete",
                    status="completed",
                    details=details
                )
            except Exception as emit_error:
                logger.warning(f"Failed to emit math completion: {str(emit_error)}")
                
        return result
    except Exception as e:
        error_msg = f"Error calculating statistics: {str(e)}"
        logger.error(f"❌ STATISTICS ERROR: {error_msg}")
        
        # Emit error if SSE is available
        if sse_available and session_id and has_app_context():
            try:
                sse_emitter.emit_agent_activity(
                    session_id=session_id,
                    agent_name="Math Agent",
                    action="Statistics calculation failed",
                    status="error",
                    details=error_msg
                )
            except Exception as emit_error:
                logger.warning(f"Failed to emit math error: {str(emit_error)}")
                
        raise ValueError(error_msg)
