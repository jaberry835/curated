#!/usr/bin/env python3
"""
Startup script for Rude MCP Server on Azure App Service
This script ensures the server runs with HTTP/SSE transport using gunicorn
"""

import os
import sys
import logging
import subprocess

# Ensure current directory is in Python path for module imports
if os.path.dirname(__file__) not in sys.path:
    sys.path.insert(0, os.path.dirname(__file__))
if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())

# Configure logging for Azure App Service
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def install_dependencies():
    """Install Python dependencies if needed"""
    try:
        import fastmcp
        logger.info("FastMCP already available")
    except ImportError:
        logger.info("Installing dependencies from requirements.txt...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            logger.info("Dependencies installed successfully")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install dependencies: {e}")
            raise

if __name__ == "__main__":
    # Get port from environment (Azure App Service sets this)
    port = int(os.getenv("PORT", "8000"))
    
    logger.info("=== Rude MCP Server - Azure App Service Startup ===")
    logger.info(f"Transport: HTTP with Server-Sent Events (SSE)")
    logger.info(f"Port: {port}")
    logger.info(f"Host: 0.0.0.0")
    
    # Check Azure environment
    if os.getenv("WEBSITE_SITE_NAME"):
        logger.info(f"Running on Azure App Service: {os.getenv('WEBSITE_SITE_NAME')}")
    else:
        logger.info("Running in local/development environment")
    
    # Install dependencies first
    install_dependencies()
    
    # Debug: Log current directory and Python path
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"Script directory: {os.path.dirname(__file__)}")
    logger.info(f"Python path: {sys.path[:3]}...")  # Show first 3 entries
    
    # Check if tools directory exists
    tools_path = os.path.join(os.getcwd(), 'tools')
    logger.info(f"Tools directory exists: {os.path.exists(tools_path)}")
    if os.path.exists(tools_path):
        logger.info(f"Tools directory contents: {os.listdir(tools_path)}")
    
    # Change to the directory containing the script to ensure relative imports work
    script_dir = os.path.dirname(__file__)
    if script_dir:
        os.chdir(script_dir)
        logger.info(f"Changed working directory to: {os.getcwd()}")
    
    # Import the app after dependencies are installed
    try:
        from main import app
        logger.info("Successfully imported main app")
    except ImportError as e:
        logger.error(f"Failed to import main app: {e}")
        # List directory contents for debugging
        logger.error(f"Current directory contents: {os.listdir('.')}")
        raise
    
    # Try to use gunicorn (more standard for Azure App Service)
    try:
        import gunicorn.app.wsgiapp as wsgi
        
        logger.info("Using gunicorn server")
        
        # Configure gunicorn arguments
        sys.argv = [
            "gunicorn",
            "--bind", f"0.0.0.0:{port}",
            "--workers", "1",
            "--worker-class", "uvicorn.workers.UvicornWorker",
            "--timeout", "120",
            "--keep-alive", "5",
            "--access-logfile", "-",
            "--error-logfile", "-",
            "main:app"
        ]
        
        # Run gunicorn
        wsgi.run()
        
    except ImportError:
        # Fallback to uvicorn if gunicorn not available
        logger.info("Gunicorn not available, using uvicorn...")
        import uvicorn
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            log_level="info",
            access_log=True
        )
