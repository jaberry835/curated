"""RAG Dataset Tools for searching specific Azure AI Search indexes."""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI

try:
    from ..config.settings import settings
    from ..config.rag_datasets_config import rag_datasets_config, RAGDatasetConfig
    from ..utils.logging import get_logger
except ImportError:
    from src.config.settings import settings  
    from src.config.rag_datasets_config import rag_datasets_config, RAGDatasetConfig
    from src.utils.logging import get_logger

logger = get_logger(__name__)

class RAGDatasetSearchService:
    """Service for searching specific RAG datasets in Azure AI Search."""
    
    def __init__(self):
        """Initialize the RAG dataset search service."""
        self.search_clients: Dict[str, SearchClient] = {}
        self.openai_client = None
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize Azure AI Search clients for each dataset."""
        try:
            # Initialize Azure OpenAI client for embeddings
            if (settings.azure.azure_openai_endpoint and 
                settings.azure.azure_openai_api_key and
                '[' not in settings.azure.azure_openai_endpoint and 
                '[' not in settings.azure.azure_openai_api_key):
                
                self.openai_client = AzureOpenAI(
                    azure_endpoint=settings.azure.azure_openai_endpoint,
                    api_key=settings.azure.azure_openai_api_key,
                    api_version="2024-02-01"
                )
                logger.info("✅ Azure OpenAI client initialized for RAG embeddings")
            
            # Initialize search clients for each enabled dataset
            if (settings.azure.azure_search_endpoint and 
                settings.azure.azure_search_key and
                '[' not in settings.azure.azure_search_endpoint and 
                '[' not in settings.azure.azure_search_key):
                
                enabled_datasets = rag_datasets_config.get_enabled_datasets()
                
                for dataset_name, dataset_config in enabled_datasets.items():
                    try:
                        search_client = SearchClient(
                            settings.azure.azure_search_endpoint,
                            dataset_config.azure_search_index,
                            AzureKeyCredential(settings.azure.azure_search_key)
                        )
                        self.search_clients[dataset_name] = search_client
                        logger.info(f"✅ Search client initialized for dataset: {dataset_name} (index: {dataset_config.azure_search_index})")
                        
                    except Exception as e:
                        logger.error(f"❌ Failed to initialize search client for dataset '{dataset_name}': {e}")
                
                logger.info(f"🔍 Initialized {len(self.search_clients)} RAG dataset search clients")
            else:
                logger.warning("Azure AI Search not configured for RAG datasets")
                
        except Exception as e:
            logger.error(f"Error initializing RAG dataset search service: {e}")
    
    async def _generate_embedding(self, text: str, embedding_model: str = None) -> Optional[List[float]]:
        """Generate embedding for text using Azure OpenAI."""
        try:
            if not self.openai_client:
                return None
            
            # Use provided model or fall back to configured default or system default
            model = embedding_model or settings.azure.azure_openai_embedding_deployment or "text-embedding-ada-002"
            
            response = self.openai_client.embeddings.create(
                input=text,
                model=model
            )
            
            embedding = response.data[0].embedding
            logger.debug(f"Generated embedding with {len(embedding)} dimensions using model: {model}")
            return embedding
            
        except Exception as e:
            logger.error(f"Error generating embedding with model {model}: {e}")
            return None
    
    async def search_dataset(self, dataset_name: str, query: str, max_results: int = 5, 
                           user_id: str = None, session_id: str = None) -> Dict[str, Any]:
        """Search a specific RAG dataset."""
        try:
            dataset_config = rag_datasets_config.get_dataset(dataset_name)
            if not dataset_config:
                return {
                    "success": False,
                    "error": f"Dataset '{dataset_name}' not found or not configured",
                    "results": [],
                    "count": 0
                }
            
            if not dataset_config.enabled:
                return {
                    "success": False,
                    "error": f"Dataset '{dataset_name}' is disabled",
                    "results": [],
                    "count": 0
                }
            
            search_client = self.search_clients.get(dataset_name)
            if not search_client:
                return {
                    "success": False,
                    "error": f"Search client not available for dataset '{dataset_name}'",
                    "results": [],
                    "count": 0
                }
            
            logger.info(f"🔍 RAG DATASET SEARCH: Searching '{query}' in dataset '{dataset_name}'")
            
            # Prepare search parameters using configurable field names
            # Build select list with only configured fields
            select_fields = [
                dataset_config.id_field, 
                dataset_config.content_field, 
                dataset_config.title_field
            ]
            
            # Add optional fields if they are configured
            if dataset_config.filename_field:
                select_fields.append(dataset_config.filename_field)
            if dataset_config.filepath_field:
                select_fields.append(dataset_config.filepath_field)
            if dataset_config.uploaded_at_field:
                select_fields.append(dataset_config.uploaded_at_field)
            if dataset_config.metadata_field:
                select_fields.append(dataset_config.metadata_field)
            
            search_kwargs = {
                "search_text": query,
                "top": max_results,
                "highlight_fields": dataset_config.content_field,  # Use configurable content field
                "select": select_fields  # Use only configured fields
            }
            
            # Generate embedding for vector search if available and enabled
            vector_query = None
            if dataset_config.enable_vector_search:
                query_embedding = await self._generate_embedding(query, dataset_config.embedding_model)
                if query_embedding:
                    # Check if embedding dimensions match expected dimensions
                    if len(query_embedding) == dataset_config.vector_dimensions:
                        vector_query = VectorizedQuery(
                            vector=query_embedding,
                            k_nearest_neighbors=max_results,
                            fields=dataset_config.vector_field  # Use configurable vector field
                        )
                        search_kwargs["vector_queries"] = [vector_query]
                        logger.info(f"🔍 Performing hybrid text + vector search in dataset '{dataset_name}' (dimensions: {len(query_embedding)})")
                    else:
                        logger.warning(f"⚠️ Vector dimension mismatch for dataset '{dataset_name}': got {len(query_embedding)}, expected {dataset_config.vector_dimensions}. Falling back to text-only search.")
                        logger.info(f"🔍 Performing text-only search in dataset '{dataset_name}' due to dimension mismatch")
                else:
                    logger.info(f"🔍 Performing text-only search in dataset '{dataset_name}' (embedding generation failed)")
            else:
                logger.info(f"🔍 Performing text-only search in dataset '{dataset_name}' (vector search disabled)")
            
            # Execute search
            search_results = search_client.search(**search_kwargs)
            
            # Process results
            results = []
            for result in search_results:
                search_score = getattr(result, '@search.score', 0)
                highlights = getattr(result, '@search.highlights', {})
                
                processed_result = {
                    "id": result.get(dataset_config.id_field, ""),
                    "title": result.get(dataset_config.title_field, ""),
                    "content": result.get(dataset_config.content_field, "")[:2000] + "..." if len(result.get(dataset_config.content_field, "")) > 2000 else result.get(dataset_config.content_field, ""),
                    "searchScore": search_score,
                    "highlights": highlights.get(dataset_config.content_field, []) if highlights else []  # Use configurable content field
                }
                
                # Add optional fields only if they are configured and available
                if dataset_config.filename_field:
                    processed_result["fileName"] = result.get(dataset_config.filename_field, "")
                if dataset_config.filepath_field:
                    processed_result["filePath"] = result.get(dataset_config.filepath_field, "")
                if dataset_config.uploaded_at_field:
                    processed_result["uploadedAt"] = result.get(dataset_config.uploaded_at_field, "")
                if dataset_config.metadata_field:
                    processed_result["metadata"] = result.get(dataset_config.metadata_field, {})
                results.append(processed_result)
            
            logger.info(f"🔍 RAG DATASET SEARCH: Found {len(results)} results in dataset '{dataset_name}'")
            
            return {
                "success": True,
                "dataset": dataset_name,
                "query": query,
                "results": results,
                "count": len(results),
                "index": dataset_config.azure_search_index
            }
            
        except Exception as e:
            error_msg = f"Error searching dataset '{dataset_name}': {str(e)}"
            logger.error(f"❌ RAG DATASET SEARCH ERROR: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "dataset": dataset_name,
                "query": query,
                "results": [],
                "count": 0
            }

# Global service instance
rag_search_service = RAGDatasetSearchService()

# Individual tool functions for each dataset
async def search_rag_dataset_impl(dataset_name: str, query: str, max_results: int = 5, 
                                user_id: str = None, session_id: str = None) -> str:
    """Generic RAG dataset search implementation."""
    try:
        result = await rag_search_service.search_dataset(
            dataset_name=dataset_name,
            query=query,
            max_results=max_results,
            user_id=user_id,
            session_id=session_id
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        error_result = {
            "success": False,
            "error": f"Error in RAG dataset search: {str(e)}",
            "dataset": dataset_name,
            "query": query,
            "results": [],
            "count": 0
        }
        return json.dumps(error_result, indent=2)

# Dynamic tool generation functions
def get_rag_dataset_tools() -> Dict[str, Any]:
    """Get all available RAG dataset tools based on configuration."""
    tools = {}
    enabled_datasets = rag_datasets_config.get_enabled_datasets()
    
    for dataset_name, dataset_config in enabled_datasets.items():
        tool_name = f"search_{dataset_name}_dataset"
        
        # Create tool function dynamically
        def create_dataset_tool(ds_name=dataset_name, ds_config=dataset_config):
            async def dataset_tool_impl(query: str, max_results: int = None, 
                                      user_id: str = None, session_id: str = None) -> str:
                if max_results is None:
                    max_results = ds_config.max_results
                return await search_rag_dataset_impl(ds_name, query, max_results, user_id, session_id)
            return dataset_tool_impl
        
        # Store the tool function
        tools[tool_name] = create_dataset_tool()
        
        logger.info(f"🔧 Created RAG tool: {tool_name} for dataset '{dataset_name}'")
    
    return tools

def get_rag_dataset_tool_descriptions() -> List[Dict[str, str]]:
    """Get tool descriptions for all RAG datasets."""
    descriptions = []
    enabled_datasets = rag_datasets_config.get_enabled_datasets()
    
    for dataset_name, dataset_config in enabled_datasets.items():
        tool_name = f"search_{dataset_name}_dataset"
        description = {
            "name": tool_name,
            "description": f"Search the {dataset_config.display_name} dataset. {dataset_config.description}",
            "dataset_name": dataset_name,
            "display_name": dataset_config.display_name,
            "index": dataset_config.azure_search_index
        }
        descriptions.append(description)
    
    return descriptions

# Specific dataset tool implementations (will be created dynamically)
async def search_hulk_dataset_impl(query: str, max_results: int = 5, 
                                 user_id: str = None, session_id: str = None) -> str:
    """Search the Hulk dataset."""
    return await search_rag_dataset_impl("hulk", query, max_results, user_id, session_id)

async def search_policy_documents_dataset_impl(query: str, max_results: int = 3, 
                                              user_id: str = None, session_id: str = None) -> str:
    """Search the Policy Documents dataset."""
    return await search_rag_dataset_impl("policy_documents", query, max_results, user_id, session_id)
