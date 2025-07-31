# Dynamic RAG Agent System

## Overview

The Dynamic RAG (Retrieval-Augmented Generation) Agent System allows you to create specialized AI agents that can search and interact with different datasets stored in Azure AI Search indexes. Each dataset can have its own customized system prompts, agent instructions, and search parameters.

## Architecture

The system consists of several key components:

1. **RAG Dataset Configuration** (`rag_datasets_config.py`) - Manages dataset configurations
2. **RAG Dataset Tools** (`rag_dataset_tools.py`) - Provides search functionality for each dataset
3. **RAG Agent Service** (`rag_agent_service.py`) - Manages dynamic agents for each dataset
4. **API Routes** (`rag_routes.py`) - REST API endpoints for managing datasets and agents
5. **Configuration File** (`rag_datasets.json`) - JSON configuration for all datasets

## Configuration

### Dataset Configuration Structure

Each dataset is configured with the following properties:

```json
{
  "name": "dataset_identifier",
  "display_name": "Human Readable Name",
  "description": "Description of what this dataset contains",
  "azure_search_index": "azure-search-index-name",
  "system_prompt": "Instructions for how the AI should behave with this dataset",
  "agent_instructions": "Detailed instructions for the agent's capabilities and response patterns",
  "max_results": 5,
  "enabled": true,
  "temperature": 0.3,
  "max_tokens": 8000
}
```

### Configuration File Location

The configuration file is located at: `src/config/rag_datasets.json`

### Default Datasets

The system comes with two example datasets:

1. **Hulk Dataset** (`hulk-idx`) - Information about the Hulk character from Marvel Comics
2. **Policy Documents** (`policy-docs-idx`) - Corporate policy documents and procedures

## Features

### Dynamic Agent Creation

- Automatically creates agents for each enabled dataset
- Each agent has its own specialized knowledge and response patterns
- Agents can be reloaded without restarting the application

### Azure AI Search Integration

- Uses Azure AI Search for document retrieval
- Supports both text search and vector search (hybrid search)
- Automatically generates embeddings for queries when Azure OpenAI is configured

### Intelligent Response Generation

- Uses Azure OpenAI to generate contextual responses based on search results
- Incorporates dataset-specific system prompts and instructions
- Configurable temperature and token limits per dataset

### Real-time Activity Tracking

- Emits Server-Sent Events (SSE) for real-time activity tracking
- Shows search progress, results found, and response generation
- Integrates with the existing multi-agent system

## Usage

### Adding a New Dataset

1. **Create the Azure AI Search Index**: Ensure your documents are indexed in Azure AI Search
2. **Add Dataset Configuration**: Either use the API or manually edit the JSON file
3. **Reload Configuration**: The system will automatically create an agent for the new dataset

#### Via API:

```bash
POST /api/rag/datasets
{
  "name": "my_dataset",
  "display_name": "My Dataset",
  "description": "Description of my dataset",
  "azure_search_index": "my-search-index",
  "system_prompt": "You are an expert on my dataset topic...",
  "agent_instructions": "Detailed instructions for the agent...",
  "max_results": 5,
  "enabled": true,
  "temperature": 0.3,
  "max_tokens": 8000
}
```

#### Via Configuration File:

Add a new entry to `src/config/rag_datasets.json`:

```json
{
  "datasets": {
    "existing_dataset": { ... },
    "my_dataset": {
      "name": "my_dataset",
      "display_name": "My Dataset",
      "description": "Description of my dataset",
      "azure_search_index": "my-search-index",
      "system_prompt": "You are an expert on my dataset topic...",
      "agent_instructions": "Detailed instructions...",
      "max_results": 5,
      "enabled": true,
      "temperature": 0.3,
      "max_tokens": 8000
    }
  }
}
```

### Using RAG Agents

#### Via MCP Tools:

```python
# Search a specific dataset
result = await mcp_client.call_tool("search_hulk_dataset", {
    "query": "What are Hulk's main powers?",
    "max_results": 5
})

# Search policy documents
result = await mcp_client.call_tool("search_policy_documents_dataset", {
    "query": "vacation policy",
    "max_results": 3
})
```

#### Via API:

```bash
# Search a dataset
POST /api/rag/datasets/hulk/search
{
  "query": "What are Hulk's main powers?",
  "max_results": 5
}

# Query an agent (includes LLM response)
POST /api/rag/agents/hulk/query
{
  "query": "Tell me about Hulk's transformation abilities"
}
```

#### Via RAG Agent Service:

```python
from src.services.rag_agent_service import rag_agent_service

# Query a specific agent
result = await rag_agent_service.query_agent(
    dataset_name="hulk",
    user_query="What are Hulk's main powers?",
    session_id="session_123",
    user_id="user_456"
)
```

## API Endpoints

### Dataset Management

- `GET /api/rag/datasets` - List all datasets
- `GET /api/rag/datasets/{name}` - Get dataset details
- `POST /api/rag/datasets` - Create new dataset
- `PUT /api/rag/datasets/{name}` - Update dataset
- `DELETE /api/rag/datasets/{name}` - Delete dataset
- `POST /api/rag/datasets/{name}/search` - Search dataset

### Agent Management

- `GET /api/rag/agents` - List all agents
- `POST /api/rag/agents/{name}/query` - Query specific agent

### System Management

- `POST /api/rag/reload` - Reload all configurations and agents

## Azure AI Search Index Requirements

For optimal performance, your Azure AI Search indexes should include these fields:

### Required Fields:
- `id` (string) - Unique document identifier
- `content` (string) - Main document content (searchable)
- `title` (string) - Document title
- `fileName` (string) - Original file name
- `filePath` (string) - File path or location

### Optional Fields:
- `contentVector` (vector) - Document embeddings for vector search
- `uploadedAt` (datetime) - Upload timestamp
- `metadata` (object) - Additional metadata

### Example Index Schema:

```json
{
  "fields": [
    {"name": "id", "type": "Edm.String", "key": true, "searchable": false},
    {"name": "content", "type": "Edm.String", "searchable": true, "retrievable": true},
    {"name": "title", "type": "Edm.String", "searchable": true, "retrievable": true},
    {"name": "fileName", "type": "Edm.String", "retrievable": true},
    {"name": "filePath", "type": "Edm.String", "retrievable": true},
    {"name": "contentVector", "type": "Collection(Edm.Single)", "dimensions": 1536, "vectorSearchProfile": "default"},
    {"name": "uploadedAt", "type": "Edm.DateTimeOffset", "retrievable": true},
    {"name": "metadata", "type": "Edm.ComplexType", "retrievable": true}
  ]
}
```

## Environment Variables

Ensure these Azure configuration variables are set:

```bash
# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://your-search-service.search.windows.net
AZURE_SEARCH_KEY=your-search-admin-key

# Azure OpenAI (for embeddings and response generation)
AZURE_OPENAI_ENDPOINT=https://your-openai-service.openai.azure.com
AZURE_OPENAI_API_KEY=your-openai-api-key
AZURE_OPENAI_DEPLOYMENT=your-chat-deployment-name
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=your-embedding-deployment-name
```

## Advanced Configuration

### Custom System Prompts

Each dataset can have a custom system prompt that defines how the AI should behave:

```json
{
  "system_prompt": "You are a legal expert specializing in contract analysis. You have access to a comprehensive database of legal documents and precedents. Always provide accurate, well-researched answers and cite specific documents when possible."
}
```

### Agent Instructions

Detailed instructions that define the agent's capabilities and response patterns:

```json
{
  "agent_instructions": "You are the Legal Documents Agent.\n\nCAPABILITIES:\n- Search legal documents and contracts\n- Analyze legal language and clauses\n- Provide legal insights and recommendations\n\nINSTRUCTIONS:\n- Always cite specific documents\n- Explain legal concepts in plain language\n- Highlight potential risks or issues\n\nRESPONSE PATTERN:\nEnd with: 'My legal analysis is complete - CoordinatorAgent, please approve'"
}
```

### Search Parameters

Customize search behavior per dataset:

- `max_results`: Maximum number of documents to retrieve (1-20)
- `temperature`: LLM response creativity (0.0-1.0)
- `max_tokens`: Maximum response length (100-32000)

## Troubleshooting

### Common Issues

1. **Dataset not appearing**: Check that `enabled: true` in configuration
2. **Search returns no results**: Verify Azure AI Search index name and connectivity
3. **Poor response quality**: Adjust system prompts and agent instructions
4. **Slow responses**: Reduce `max_results` or `max_tokens`

### Logging

Enable detailed logging to troubleshoot issues:

```python
import logging
logging.getLogger('src.services.rag_agent_service').setLevel(logging.DEBUG)
logging.getLogger('src.tools.rag_dataset_tools').setLevel(logging.DEBUG)
```

### Reloading Configuration

If you make changes to the configuration file, reload without restarting:

```bash
POST /api/rag/reload
```

Or via code:

```python
from src.config.rag_datasets_config import rag_datasets_config
from src.services.rag_agent_service import rag_agent_service

rag_datasets_config.reload_config()
rag_agent_service.reload_agents()
```

## Integration with Multi-Agent System

The RAG agents integrate seamlessly with the existing multi-agent coordinator system:

1. **Tool Registration**: RAG tools are automatically registered with the MCP client
2. **SSE Events**: Real-time activity updates are sent to the frontend
3. **Session Management**: User and session context is maintained across requests
4. **Response Coordination**: Agents follow the coordinator approval pattern

## Best Practices

1. **Dataset Naming**: Use descriptive, lowercase names with underscores
2. **System Prompts**: Be specific about the agent's role and capabilities
3. **Agent Instructions**: Include clear capability lists and response patterns
4. **Index Design**: Ensure your Azure AI Search indexes have good content structure
5. **Testing**: Test each dataset thoroughly before enabling in production
6. **Monitoring**: Monitor search performance and response quality regularly

## Future Enhancements

Potential future improvements:

- Multi-language support
- Custom embedding models per dataset
- Advanced filtering and faceting
- Dataset versioning and rollback
- Performance analytics and optimization
- Integration with other vector databases
