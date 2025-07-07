# AgentChat - Multi-Agent System with MCP Tools

A comprehensive multi-agent chat system built with Angular frontend and Python Flask backend, featuring Model Context Protocol (MCP) tools for extensible agent capabilities.

## 🚀 Quick Start

### Prerequisites

- Node.js (v18 or higher)
- Python 3.9+
- Angular CLI (`npm install -g @angular/cli`)

### Local Development Setup

#### 1. Start the Python API Server

```bash
cd PythonAPI
python main.py
```

The API will start on `http://localhost:5007`

#### 2. Start the Angular Development Server

```bash
# From the project root directory
npx ng --proxy-config proxy.conf.json serve --open
```

The Angular app will start on `http://localhost:4200` and automatically open in your browser.

### Development URLs

- **Frontend**: http://localhost:4200
- **API**: http://localhost:5007
- **API Health Check**: http://localhost:5007/api/v1/health
- **MCP Tools**: http://localhost:5007/api/v1/tools

## 🏗️ Architecture

### Multi-Agent System

The system provides a flexible multi-agent architecture where:

- **Each agent** has its own set of specialized MCP (Model Context Protocol) tools
- **Agents can be added** dynamically without modifying core system code
- **Tools are extensible** and can be shared between agents
- **Session management** handles multi-turn conversations with context

### System Components

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Angular UI    │    │   Python API    │    │   MCP Tools     │
│                 │    │                 │    │                 │
│ • Chat Interface│◄──►│ • Agent Routes  │◄──►│ • Math Tools    │
│ • Agent Select  │    │ • MCP Server    │    │ • Utility Tools │
│ • File Upload   │    │ • SSE Streaming │    │ • Custom Tools  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                        │                        │
         │                        ▼                        │
         │              ┌─────────────────┐                │
         │              │   Data Layer    │                │
         │              │                 │                │
         └──────────────│ • Cosmos DB     │◄───────────────┘
                        │ • Blob Storage  │
                        │ • AI Search     │
                        └─────────────────┘
```

## 🔧 Adding New Agents and MCP Tools

### 📖 Complete Step-by-Step Guide

For detailed, step-by-step instructions on adding new agents and tools, see our comprehensive guide:

**[📋 Adding Agents and Tools Guide](ADDING_AGENTS_AND_TOOLS.md)**

This guide covers:
- ✅ **Adding New Tools** - Step-by-step process with examples
- ✅ **Adding New Agents** - Complete agent creation workflow  
- ✅ **Code Examples** - Real working examples you can copy
- ✅ **Best Practices** - Proven patterns for maintainable code
- ✅ **Troubleshooting** - Common issues and solutions
- ✅ **Testing** - How to verify your extensions work

### Quick Summary

The system follows this architecture:

1. **Create Tools** → Add `[category]_tools.py` in `src/tools/`
2. **Register Tools** → Update `src/mcp_server.py` 
3. **Create Wrappers** → Add function wrappers in `src/agents/mcp_functions.py`
4. **Add Agent** → Update `src/agents/multi_agent_system.py`
5. **Test** → Verify everything works together

### Example: Quick Tool Creation

```python
# src/tools/my_tools.py
def register_my_tools(mcp):
    @mcp.tool()
    def my_tool(input_text: str) -> str:
        """My custom tool that processes text."""
        return f"Processed: {input_text}"
```

**Important**: Agents are centralized in `multi_agent_system.py`, not separate files. See the [complete guide](ADDING_AGENTS_AND_TOOLS.md) for the full workflow!

### Legacy Example (For Reference Only)

The following example shows the old pattern - **use the new guide above instead**:

```python
# PythonAPI/src/tools/my_custom_tools.py
from mcp import Tool
from typing import Dict, Any, List

class MyCustomTool(Tool):
    """Custom tool for specific functionality."""
    
    def __init__(self):
        super().__init__(
            name="my_custom_tool",
            description="Description of what this tool does",
            category="custom"
        )
    
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the custom tool logic."""
        # Your custom logic here
        return {
            "result": "success",
            "data": "processed data"
        }
```

### Step 2: Register Tools in MCP Server

Update `PythonAPI/src/mcp_server.py`:

```python
# Import your new tools
from tools.my_custom_tools import MyCustomTool

# Register in the MCP server
AVAILABLE_TOOLS = [
    # ...existing tools...
    MyCustomTool(),
]
```

### Step 3: Create Agent Configuration

Create agent configuration in `PythonAPI/src/agents/`:

```python
# PythonAPI/src/agents/my_agent.py
from .base_agent import BaseAgent
from typing import List, Dict, Any

class MyAgent(BaseAgent):
    """Custom agent with specialized tools."""
    
    def __init__(self):
        super().__init__(
            name="my_agent",
            description="Agent specialized for specific tasks",
            tools=["my_custom_tool", "health_check"]  # Tools this agent can use
        )
    
    async def process_message(self, message: str, context: Dict[str, Any]) -> str:
        """Process messages with agent-specific logic."""
        # Your agent logic here
        return f"Processed: {message}"
```

### Step 4: Register Agent

Update `PythonAPI/src/api/agent_routes.py`:

```python
from agents.my_agent import MyAgent

# Register in available agents
AVAILABLE_AGENTS = [
    # ...existing agents...
    MyAgent(),
]
```

### Step 5: Update Frontend (Optional)

If you want custom UI for your agent, update `src/app/components/agent-selector/`:

```typescript
// src/app/services/agent.service.ts
export interface Agent {
  name: string;
  description: string;
  tools: string[];
  capabilities: string[];
}

// Add your agent to the service
```

## 📁 Project Structure

```
AgentChat/
├── src/                          # Angular Frontend
│   ├── app/
│   │   ├── components/           # UI Components
│   │   │   ├── chat/            # Chat interface
│   │   │   ├── agent-selector/  # Agent selection
│   │   │   └── file-upload/     # File handling
│   │   ├── services/            # Angular services
│   │   │   ├── agent.service.ts # Agent management
│   │   │   ├── chat.service.ts  # Chat functionality
│   │   │   └── mcp.service.ts   # MCP tool integration
│   │   └── models/              # TypeScript interfaces
│   └── environments/            # Environment configs
├── PythonAPI/                   # Python Backend
│   ├── src/
│   │   ├── agents/              # Agent implementations
│   │   │   ├── base_agent.py   # Base agent class
│   │   │   └── [agent_name].py # Specific agents
│   │   ├── api/                 # Flask API routes
│   │   │   ├── agent_routes.py # Agent endpoints
│   │   │   ├── chat_routes.py  # Chat endpoints
│   │   │   └── mcp_routes.py   # MCP endpoints
│   │   ├── tools/               # MCP Tools
│   │   │   ├── math_tools.py   # Mathematical operations
│   │   │   ├── utility_tools.py# Utility functions
│   │   │   └── [custom].py     # Custom tools
│   │   ├── services/            # Business logic
│   │   ├── utils/               # Utilities
│   │   └── config/              # Configuration
│   ├── app.py                   # Main Flask app
│   └── main.py                  # Development server
├── deployment/                  # Deployment scripts
├── proxy.conf.json             # Angular proxy config
└── README.md                   # This file
```

## 🛠️ Available MCP Tools

### Math Tools
- `add` - Add two numbers
- `subtract` - Subtract two numbers
- `multiply` - Multiply two numbers
- `divide` - Divide two numbers
- `calculate_statistics` - Calculate statistics for number arrays

### Utility Tools
- `health_check` - Check system health
- `get_timestamp` - Get current UTC timestamp
- `generate_hash` - Generate hash for text
- `format_json` - Validate and format JSON

### Custom Tools
- Extend the system by adding your own tools in `PythonAPI/src/tools/`

## 📊 Logging and Monitoring

The system includes comprehensive logging:

### Local Development
- Console logging for all components
- Request/response logging
- Error tracking with stack traces

### Production (Azure)
- Azure Application Insights integration
- Structured logging with custom properties
- Performance monitoring
- Error tracking and alerting

To enable Application Insights:
```bash
# Set environment variable
export APPLICATIONINSIGHTS_CONNECTION_STRING="your_connection_string"

# Or use the configuration script
.\configure-app-insights.ps1 -ConnectionString "your_connection_string"
```

## 🧪 Testing

### Test Logging
```bash
cd PythonAPI
python test_local_logging.py
```

### Test API Endpoints
```bash
# Health check
curl http://localhost:5007/api/v1/health

# List tools
curl http://localhost:5007/api/v1/tools

# List agents
curl http://localhost:5007/api/v1/agents
```

### Test MCP Tools
```bash
# Using MCP client
cd PythonAPI
mcp dev src/mcp_server.py
```

## 🔧 Configuration

### Environment Variables

Create a `.env` file in `PythonAPI/`:

```env
# Application
FLASK_ENV=development
LOG_LEVEL=DEBUG

# Azure Application Insights (optional for local dev)
APPLICATIONINSIGHTS_CONNECTION_STRING=your_connection_string

# Azure Services (for production)
AZURE_OPENAI_ENDPOINT=your_openai_endpoint
AZURE_OPENAI_API_KEY=your_api_key
AZURE_COSMOS_DB_ENDPOINT=your_cosmos_endpoint
AZURE_STORAGE_CONNECTION_STRING=your_storage_connection
AZURE_SEARCH_ENDPOINT=your_search_endpoint
```

### Proxy Configuration

The `proxy.conf.json` file routes API calls from Angular to Flask:

```json
{
  "/api/*": {
    "target": "http://localhost:5007",
    "secure": false,
    "changeOrigin": true,
    "logLevel": "debug"
  }
}
```

## 🚀 Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed deployment instructions.

## 📚 Documentation

- **[Getting Started Guide](GETTING_STARTED.md)** - Step-by-step local development setup
- **[Adding Agents and Tools Guide](ADDING_AGENTS_AND_TOOLS.md)** - Complete extension guide
- **[Deployment Guide](DEPLOYMENT.md)** - Azure deployment instructions
- **[Application Insights Setup](PythonAPI/APPLICATION_INSIGHTS_README.md)** - Monitoring setup

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add your agent/tools following the patterns above
4. Test locally
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 🆘 Support

- Check the [DEPLOYMENT.md](DEPLOYMENT.md) for deployment issues
- Review logs in `PythonAPI/logs/` for debugging
- Use the health check endpoint to verify system status
- Check Azure Application Insights for production monitoring
