"""
Rude MCP Server - A FastMCP-based server for Math and Azure Data Explorer tools
Designed to be hosted on Azure App Service over HTTP using Streamable transport
"""

import os
import logging
import sys
from typing import Dict, Any, List
from datetime import datetime
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Configure logging FIRST, before any other imports or operations
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Log early to confirm logging is working
logger.info("🚀 Starting Rude MCP Server initialization...")

# Initialize Application Insights early in startup
try:
    from app_insights import initialize_application_insights, get_application_insights
    app_insights_ready = initialize_application_insights()
    if app_insights_ready:
        logger.info("📊 Application Insights initialized successfully")
    else:
        logger.info("📊 Application Insights not configured - continuing without telemetry")
except Exception as e:
    logger.warning(f"📊 Application Insights initialization failed: {e}")
    app_insights_ready = False

# Import shared context variables
from context import current_user_id, current_session_id, current_user_token

# Ensure current directory is in Python path for module imports
if os.path.dirname(__file__) not in sys.path:
    sys.path.insert(0, os.path.dirname(__file__))
if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())

# Load environment variables from .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
    logging.info("Environment variables loaded from .env file")
except ImportError:
    logging.info("python-dotenv not available, using system environment variables only")

from fastmcp import FastMCP
from starlette.middleware.cors import CORSMiddleware

# Import tool registration functions
try:
    logger.info("📦 Importing tool registration functions...")
    from tools import register_math_tools, register_adx_tools, register_fictional_api_tools, register_document_tools, register_rag_tools
    logger.info("✅ Tool imports successful")
except ImportError as e:
    logger.error(f"❌ Failed to import tools: {e}")
    logger.error(f"Current working directory: {os.getcwd()}")
    logger.error(f"Python path: {sys.path}")
    logger.error(f"Files in current directory: {os.listdir('.')}")
    if os.path.exists('tools'):
        logger.error(f"Files in tools directory: {os.listdir('tools')}")
    else:
        logger.error("Tools directory does not exist")
    raise


class ContextMiddleware(BaseHTTPMiddleware):
    """Middleware to extract and store request context from headers"""
    
    async def dispatch(self, request: Request, call_next):
        # Extract user context from headers for ALL requests (including MCP)
        user_id = request.headers.get("X-User-ID") or request.headers.get("x-user-id") or "defaMCPUser"
        session_id = request.headers.get("X-Session-ID") or request.headers.get("x-session-id")
        
        # Extract bearer token for user impersonation
        auth_header = request.headers.get("Authorization")
        user_token = None
        if auth_header and auth_header.startswith("Bearer "):
            user_token = auth_header[7:]  # Remove "Bearer " prefix
        
        # Store in context variables
        current_user_id.set(user_id)
        if session_id:
            current_session_id.set(session_id)
        if user_token:
            current_user_token.set(user_token)
        else:
            # Clear any previous token to avoid sticky token reuse
            current_user_token.set(None)
        
        # Log authentication events to Application Insights
        try:
            if app_insights_ready:
                app_insights = get_application_insights()
                auth_mode = "user_token" if user_token else "service_identity"
                app_insights.log_authentication_event(
                    auth_mode=auth_mode,
                    user_id=user_id,
                    success=True
                )
        except Exception as e:
            logger.debug(f"Failed to log authentication event: {e}")
        
        # Enhanced logging for debugging authentication issues
        if not request.url.path.startswith("/health"):
            # Log request details for non-health endpoints
            token_status = "PRESENT" if user_token else "MISSING"
            token_preview = f"{user_token[:50]}..." if user_token else "None"
            
            logger.info(f"🔍 Context middleware processing:")
            logger.info(f"   - Path: {request.url.path}")
            logger.info(f"   - Method: {request.method}")
            logger.info(f"   - User ID: {user_id}")
            logger.info(f"   - Session ID: {session_id}")
            logger.info(f"   - Authorization header: {'PRESENT' if auth_header else 'MISSING'}")
            logger.info(f"   - Bearer token: {token_status}")
            
            if user_token:
                logger.info(f"   - Token preview: {token_preview}")
                logger.info(f"   - Token length: {len(user_token)} characters")
                
                # Try to decode and log token details for debugging
                try:
                    import base64
                    import json
                    parts = user_token.split('.')
                    if len(parts) >= 2:
                        payload = parts[1]
                        payload += '=' * (4 - len(payload) % 4)
                        decoded = base64.b64decode(payload)
                        token_data = json.loads(decoded)
                        
                        logger.info(f"   - Token audience (aud): {token_data.get('aud', 'N/A')}")
                        logger.info(f"   - Token issuer (iss): {token_data.get('iss', 'N/A')}")
                        logger.info(f"   - Token subject (sub): {token_data.get('sub', 'N/A')[:20]}..." if token_data.get('sub') else "   - Token subject: N/A")
                        
                        exp = token_data.get('exp')
                        if exp:
                            from datetime import datetime
                            exp_date = datetime.fromtimestamp(exp)
                            logger.info(f"   - Token expires: {exp_date}")
                except Exception as decode_error:
                    logger.debug(f"   - Could not decode token: {decode_error}")
        
        try:
            response = await call_next(request)
            return response
        finally:
            # Ensure token context does not leak across async tasks after response
            current_user_token.set(None)

# Initialize FastMCP server
logger.info("🔧 Initializing FastMCP server...")
mcp = FastMCP("Rude MCP Server")

# Register all tools
logger.info("📋 Registering tools...")
register_math_tools(mcp)
logger.info("✅ Math tools registered")
register_adx_tools(mcp)
logger.info("✅ ADX tools registered")
register_fictional_api_tools(mcp)
logger.info("✅ Fictional API tools registered")
register_document_tools(mcp)
logger.info("✅ Document tools registered")
register_rag_tools(mcp)
logger.info("✅ RAG tools registered")
logger.info("🎉 All tools registered successfully")


# ============================================================================
# HEALTH CHECK AND STATUS TOOLS
# ============================================================================

def get_health_status() -> Dict[str, Any]:
    """Internal health check function (not an MCP tool)"""
    try:
        # Check if Kusto is configured
        kusto_status = "not_configured"
        kusto_cluster = os.getenv("KUSTO_CLUSTER_URL")
        if kusto_cluster:
            try:
                # Import here to avoid circular dependency
                from tools.adx_tools import get_kusto_manager
                manager = get_kusto_manager()
                kusto_status = "configured"
            except Exception:
                kusto_status = "error"
        
        # Check if Fictional API is configured
        fictional_api_status = "configured" if os.getenv("FICTIONAL_COMPANIES_API_URL") else "default_localhost"
        
        # Check if Azure Search is configured for document tools
        document_service_status = "configured" if (os.getenv("AZURE_SEARCH_ENDPOINT") and os.getenv("AZURE_SEARCH_KEY")) else "not_configured"
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "server_name": "Rude MCP Server",
            "version": "1.0.0",
            "features": {
                "math_tools": True,
                "azure_data_explorer": kusto_status,
                "fictional_api": fictional_api_status,
                "document_service": document_service_status,
                "rag_tools": True
            },
            "environment": {
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "azure_environment": bool(os.getenv("AZURE_CLIENT_ID")),
                "fictional_api_url": os.getenv("FICTIONAL_COMPANIES_API_URL", "http://localhost:8000"),
                "azure_search_endpoint": os.getenv("AZURE_SEARCH_ENDPOINT", "not_configured")
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }

@mcp.tool
def health_check() -> Dict[str, Any]:
    """Health check endpoint for Azure App Service (MCP tool version)"""
    return get_health_status()


# ============================================================================
# SERVER STARTUP AND CONFIGURATION
# ============================================================================

# CORS configuration functions
def get_cors_origins() -> List[str]:
    """Get CORS origins from environment variable"""
    cors_origins = os.getenv("CORS_ORIGINS", "*")
    if cors_origins == "*":
        return ["*"]
    return [origin.strip() for origin in cors_origins.split(",")]

def configure_cors(app):
    """Configure CORS middleware for the FastAPI app"""
    cors_origins = get_cors_origins()
    cors_enabled = os.getenv("CORS_ENABLED", "true").lower() == "true"
    
    if cors_enabled:
        logger.info(f"CORS enabled with origins: {cors_origins}")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )
    else:
        logger.info("CORS disabled")

# Create the HTTP app from FastMCP for Azure App Service
logger.info("🌐 Creating HTTP app from FastMCP...")
app = mcp.http_app()

# Add the context middleware BEFORE other middleware
logger.info("🔧 Adding context middleware...")
app.add_middleware(ContextMiddleware)

# Configure CORS middleware
logger.info("🔧 Configuring CORS middleware...")
configure_cors(app)

# Add custom routes to the app
@app.route("/health")
async def health_endpoint(request):
    """Azure App Service health check endpoint"""
    from starlette.responses import JSONResponse
    return JSONResponse(get_health_status())

@app.route("/")
async def root(request):
    """Server information endpoint"""
    from starlette.responses import JSONResponse
    return JSONResponse({
        "name": "Rude MCP Server",
        "version": "1.0.0",
        "transport": "streamable_http",
        "description": "Modular FastMCP server with Math Tools, Azure Data Explorer, Fictional API, and Document Service integration",
        "endpoints": {
            "mcp": "/mcp/",
            "health": "/health"
        },
        "tools": {
            "math_tools": ["add", "subtract", "multiply", "divide", "power", "square_root", "calculate_statistics", "factorial"],
            "adx_tools": ["kusto_list_databases", "kusto_list_tables", "kusto_describe_table", "kusto_query", "kusto_get_cluster_info"],
            "fictional_api_tools": ["get_ip_company_info", "get_company_devices", "get_company_summary", "fictional_api_health_check"],
                "document_tools": ["list_documents", "get_document", "search_documents", "get_document_content_summary"],
                "rag_tools": ["rag_retrieve", "rag_rag_answer", "rag_health"]
        }
    })

if __name__ == "__main__":
    try:
        # Log startup information
        logger.info("Starting Rude MCP Server for Azure App Service...")
        logger.info("Transport: HTTP Streamable for MCP over HTTP")
        logger.info("Available tools: Math operations, Azure Data Explorer queries, Fictional API calls, Document management")
        logger.info("Tools are loaded from modular tools/ directory")
        
        # Log Application Insights status
        if app_insights_ready:
            logger.info("📊 Application Insights: ENABLED - Telemetry and logging active")
            app_insights = get_application_insights()
            app_insights.log_custom_event("Server_Startup", {
                "server_name": "Rude MCP Server",
                "version": os.getenv("MCP_SERVER_VERSION", "1.0.0"),
                "environment": os.getenv("ENVIRONMENT", "production"),
                "features": "math_tools,adx_tools,fictional_api_tools,document_tools"
            })
        else:
            logger.info("📊 Application Insights: DISABLED - Add APPLICATIONINSIGHTS_CONNECTION_STRING to enable")
        
        # Check for required environment variables
        kusto_cluster = os.getenv("KUSTO_CLUSTER_URL")
        if kusto_cluster:
            logger.info(f"Azure Data Explorer cluster configured: {kusto_cluster}")
        else:
            logger.warning("KUSTO_CLUSTER_URL not set - Azure Data Explorer tools will not work")
        
        # Check fictional API configuration
        fictional_api_url = os.getenv("FICTIONAL_COMPANIES_API_URL")
        if fictional_api_url:
            logger.info(f"Fictional API configured: {fictional_api_url}")
        else:
            logger.info("FICTIONAL_COMPANIES_API_URL not set - using default localhost:8000")
        
        # Check Azure Search configuration for document tools
        azure_search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
        if azure_search_endpoint:
            logger.info(f"Azure AI Search configured: {azure_search_endpoint}")
        else:
            logger.warning("AZURE_SEARCH_ENDPOINT not set - Document tools will not work")
        
        # For local development/testing, run with uvicorn
        import uvicorn
        port = int(os.getenv("PORT", "8000"))
        logger.info(f"Starting server on port {port}")
        uvicorn.run(app, host="0.0.0.0", port=port)
        
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        raise
