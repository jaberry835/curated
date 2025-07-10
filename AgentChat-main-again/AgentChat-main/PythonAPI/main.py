"""Main application entry point - Flask API + Simple MCP Server."""

import os
import sys
import threading
import subprocess
from pathlib import Path

# Add src to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from config.settings import settings
from utils.logging import setup_logging, get_logger
from api.app import create_app


def run_flask_app():
    """Run the Flask application."""
    logger = get_logger("flask_runner")
    
    try:
        app = create_app()
        logger.info(f"Starting Flask API on {settings.api.host}:{settings.api.port}")
        
        # Use standard Flask app.run
        app.run(
            host=settings.api.host,
            port=settings.api.port,
            debug=settings.api.debug
        )
    except Exception as e:
        logger.error(f"Error running Flask app: {str(e)}")
        raise


def run_mcp_server():
    """Run the simple MCP server."""
    logger = get_logger("mcp_runner")
    
    try:
        simple_server_path = Path(__file__).parent / "src" / "mcp_server.py"
        logger.info(f"Starting Simple MCP Server: {simple_server_path}")
        
        # Use the virtual environment Python if available, otherwise sys.executable
        venv_python = Path(__file__).parent / ".venv" / "Scripts" / "python.exe"
        python_executable = str(venv_python) if venv_python.exists() else sys.executable
        
        logger.info(f"Using Python executable: {python_executable}")
        
        # Run the simple MCP server as a subprocess
        subprocess.run([
            python_executable, 
            str(simple_server_path)
        ], check=True)
        
    except Exception as e:
        logger.error(f"Error running Simple MCP server: {str(e)}")
        raise


def main():
    """Main entry point - run both Flask and MCP servers."""
    
    # Set up main logger
    logger = setup_logging(
        log_level=settings.log_level,
        logger_name="main"
    )
    
    logger.info("="*60)
    logger.info("Starting Python API with Multi-Agent System")
    logger.info("="*60)
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Flask API: {settings.api.host}:{settings.api.port}")
    logger.info("MCP Tools: Direct function calls (no separate server needed)")
    logger.info("="*60)
    
    try:
        # Note: MCP server is disabled since we use direct function calls
        # The multi-agent system calls tool functions directly for better performance
        
        # Start Flask app in main thread
        logger.info("Starting Flask application...")
        run_flask_app()
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.error(f"Application error: {str(e)}")
        raise
    finally:
        logger.info("Application shutdown complete")


if __name__ == "__main__":
    main()
