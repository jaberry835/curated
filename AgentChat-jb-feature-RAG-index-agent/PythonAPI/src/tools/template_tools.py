"""Template for new MCP tool modules.

This template provides a comprehensive example of how to create new tool modules
for the AgentChat system. Follow the patterns shown here for consistency.

USAGE:
1. Copy this file and rename it (e.g., string_tools.py)
2. Update the function name (e.g., register_string_tools)
3. Replace the example tools with your actual tools
4. Import and add to TOOL_MODULES list in mcp_server.py
5. Create function wrappers in mcp_functions.py
6. Add agent in multi_agent_system.py (if needed)
"""

def register_example_tools(mcp):
    """Register example tools with the MCP server.
    
    This function demonstrates various patterns for creating MCP tools:
    - Simple input/output tools
    - Tools with multiple parameters
    - Tools with optional parameters
    - Tools with complex return types
    - Tools with error handling
    - Tools with data validation
    """
    
    @mcp.tool()
    def simple_example(text: str) -> str:
        """Simple example tool that reverses text.
        
        Args:
            text: The text to reverse
            
        Returns:
            The reversed text
        """
        if not text:
            return ""
        return text[::-1]
    
    @mcp.tool()
    def multiple_params_example(text: str, count: int, uppercase: bool = False) -> dict:
        """Example tool with multiple parameters including optional ones.
        
        Args:
            text: The text to process
            count: Number of times to repeat the text
            uppercase: Whether to convert to uppercase (optional, default False)
            
        Returns:
            Dictionary with processing results
        """
        if count < 0:
            raise ValueError("Count must be non-negative")
        
        processed_text = text.upper() if uppercase else text
        repeated_text = (processed_text + " ") * count
        
        return {
            "original": text,
            "processed": processed_text,
            "repeated": repeated_text.strip(),
            "count": count,
            "uppercase_applied": uppercase,
            "final_length": len(repeated_text.strip())
        }
    
    @mcp.tool()
    def list_processing_example(items: list[str], operation: str = "count") -> dict:
        """Example tool that processes a list of items.
        
        Args:
            items: List of strings to process
            operation: Operation to perform ("count", "sort", "unique", "stats")
            
        Returns:
            Dictionary with processing results
        """
        if not items:
            return {"error": "Empty list provided"}
        
        if operation == "count":
            return {
                "operation": "count",
                "total_items": len(items),
                "unique_items": len(set(items))
            }
        elif operation == "sort":
            return {
                "operation": "sort",
                "original": items,
                "sorted": sorted(items),
                "reverse_sorted": sorted(items, reverse=True)
            }
        elif operation == "unique":
            unique_items = list(set(items))
            return {
                "operation": "unique",
                "original_count": len(items),
                "unique_items": unique_items,
                "unique_count": len(unique_items),
                "duplicates_removed": len(items) - len(unique_items)
            }
        elif operation == "stats":
            lengths = [len(item) for item in items]
            return {
                "operation": "stats",
                "total_items": len(items),
                "shortest_length": min(lengths),
                "longest_length": max(lengths),
                "average_length": sum(lengths) / len(lengths),
                "total_characters": sum(lengths)
            }
        else:
            return {"error": f"Unknown operation: {operation}"}
    
    @mcp.tool()
    def error_handling_example(value: str, strict: bool = True) -> dict:
        """Example tool demonstrating proper error handling.
        
        Args:
            value: A string that should be a number
            strict: Whether to raise errors or return error info
            
        Returns:
            Dictionary with result or error information
        """
        try:
            # Attempt to convert to number
            num_value = float(value)
            
            # Perform some calculation
            result = {
                "original": value,
                "numeric_value": num_value,
                "squared": num_value ** 2,
                "square_root": num_value ** 0.5 if num_value >= 0 else None,
                "is_integer": num_value.is_integer(),
                "absolute": abs(num_value),
                "success": True
            }
            
            return result
            
        except ValueError as e:
            error_info = {
                "original": value,
                "error": f"Cannot convert '{value}' to number",
                "error_type": "ValueError",
                "success": False
            }
            
            if strict:
                raise ValueError(error_info["error"]) from e
            else:
                return error_info
    
    @mcp.tool()
    def data_validation_example(email: str, age: int) -> dict:
        """Example tool with input validation.
        
        Args:
            email: Email address to validate
            age: Age in years
            
        Returns:
            Dictionary with validation results
        """
        import re
        
        # Validate email format
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        is_valid_email = re.match(email_pattern, email) is not None
        
        # Validate age
        is_valid_age = 0 <= age <= 150
        
        # Determine overall validity
        is_valid = is_valid_email and is_valid_age
        
        return {
            "email": email,
            "age": age,
            "email_valid": is_valid_email,
            "age_valid": is_valid_age,
            "overall_valid": is_valid,
            "validation_details": {
                "email_format": "Valid format" if is_valid_email else "Invalid email format",
                "age_range": "Valid range" if is_valid_age else "Age must be between 0 and 150"
            }
        }
    
    @mcp.tool()
    def complex_processing_example(data: dict, options: dict = None) -> dict:
        """Example tool for complex data processing.
        
        Args:
            data: Dictionary containing data to process
            options: Optional processing options
            
        Returns:
            Dictionary with processed results
        """
        if options is None:
            options = {}
        
        # Default options
        default_options = {
            "include_metadata": True,
            "sort_keys": False,
            "max_depth": 3,
            "filter_empty": False
        }
        
        # Merge options
        merged_options = {**default_options, **options}
        
        def process_value(value, depth=0):
            if depth > merged_options["max_depth"]:
                return "[Max depth exceeded]"
            
            if isinstance(value, dict):
                processed = {}
                for k, v in value.items():
                    if merged_options["filter_empty"] and not v:
                        continue
                    processed[k] = process_value(v, depth + 1)
                return processed
            elif isinstance(value, list):
                return [process_value(item, depth + 1) for item in value]
            elif isinstance(value, str):
                return value.strip()
            else:
                return value
        
        # Process the data
        processed_data = process_value(data)
        
        # Sort keys if requested
        if merged_options["sort_keys"] and isinstance(processed_data, dict):
            processed_data = dict(sorted(processed_data.items()))
        
        result = {
            "processed_data": processed_data,
            "processing_options": merged_options
        }
        
        # Add metadata if requested
        if merged_options["include_metadata"]:
            result["metadata"] = {
                "original_type": type(data).__name__,
                "original_size": len(str(data)),
                "processed_size": len(str(processed_data)),
                "keys_count": len(data) if isinstance(data, dict) else None,
                "processing_timestamp": "2024-01-01T00:00:00Z"  # In real implementation, use actual timestamp
            }
        
        return result
    
    # Template for async tools (if needed)
    # Note: MCP tools are typically synchronous, but this shows the pattern
    @mcp.tool()
    def async_example(delay_seconds: float = 1.0) -> dict:
        """Example of a tool that simulates async operation.
        
        Args:
            delay_seconds: Seconds to simulate processing delay
            
        Returns:
            Dictionary with timing information
        """
        import time
        
        start_time = time.time()
        
        # Simulate some processing time
        time.sleep(delay_seconds)
        
        end_time = time.time()
        actual_delay = end_time - start_time
        
        return {
            "requested_delay": delay_seconds,
            "actual_delay": actual_delay,
            "start_time": start_time,
            "end_time": end_time,
            "message": f"Processed with {actual_delay:.2f} second delay"
        }
    
    # All tools are automatically registered by the @mcp.tool() decorator
    # No additional registration code needed
