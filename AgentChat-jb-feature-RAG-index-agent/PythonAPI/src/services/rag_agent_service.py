"""Dynamic RAG Agent Service for managing dataset-specific agents."""

import json
import asyncio
import logging
from typing import Dict, List, Any, Optional
from openai import AzureOpenAI

try:
    from ..config.settings import settings
    from ..config.rag_datasets_config import rag_datasets_config, RAGDatasetConfig
    from ..tools.rag_dataset_tools import rag_search_service, search_rag_dataset_impl
    from ..utils.logging import get_logger
    from ..utils.sse_emitter import sse_emitter
except ImportError:
    from src.config.settings import settings
    from src.config.rag_datasets_config import rag_datasets_config, RAGDatasetConfig  
    from src.tools.rag_dataset_tools import rag_search_service, search_rag_dataset_impl
    from src.utils.logging import get_logger
    from src.utils.sse_emitter import sse_emitter

logger = get_logger(__name__)

class RAGAgent:
    """Individual RAG agent for a specific dataset."""
    
    def __init__(self, dataset_config: RAGDatasetConfig):
        """Initialize RAG agent with dataset configuration."""
        self.dataset_config = dataset_config
        self.agent_name = f"{dataset_config.display_name} Agent"
        self.search_function = None
        self.openai_client = None
        self._setup_agent()
    
    def _setup_agent(self):
        """Setup the agent with its search function and AI client."""
        try:
            # Create search function for this dataset
            async def search_dataset(query: str, max_results: int = None, 
                                   user_id: str = None, session_id: str = None) -> str:
                if max_results is None:
                    max_results = self.dataset_config.max_results
                return await search_rag_dataset_impl(
                    self.dataset_config.name, query, max_results, user_id, session_id
                )
            
            self.search_function = search_dataset
            
            # Initialize Azure OpenAI client
            if (settings.azure.azure_openai_endpoint and 
                settings.azure.azure_openai_api_key and
                '[' not in settings.azure.azure_openai_endpoint and 
                '[' not in settings.azure.azure_openai_api_key):
                
                self.openai_client = AzureOpenAI(
                    azure_endpoint=settings.azure.azure_openai_endpoint,
                    api_key=settings.azure.azure_openai_api_key,
                    api_version="2024-02-01"
                )
            
            logger.info(f"✅ RAG Agent setup complete: {self.agent_name}")
            
        except Exception as e:
            logger.error(f"❌ Failed to setup RAG agent '{self.agent_name}': {e}")
    
    async def process_query(self, user_query: str, session_id: str = None, 
                          user_id: str = None) -> Dict[str, Any]:
        """Process a user query using this RAG agent."""
        try:
            logger.info(f"🤖 {self.agent_name}: Processing query '{user_query}'")
            
            # Emit initial activity
            if session_id:
                try:
                    sse_emitter.emit_agent_activity(
                        session_id=session_id,
                        agent_name=self.agent_name,
                        action=f"Searching {self.dataset_config.display_name}",
                        status="in-progress",
                        details=f"Searching for: {user_query}"
                    )
                except Exception as emit_error:
                    logger.warning(f"Failed to emit RAG agent activity: {str(emit_error)}")
            
            # Search the dataset
            search_results = await self.search_function(
                query=user_query,
                max_results=self.dataset_config.max_results,
                user_id=user_id,
                session_id=session_id
            )
            
            # Parse search results
            search_data = json.loads(search_results) if isinstance(search_results, str) else search_results
            
            if not search_data.get("success", False):
                error_response = {
                    "success": False,
                    "agent": self.agent_name,
                    "dataset": self.dataset_config.name,
                    "error": search_data.get("error", "Search failed"),
                    "response": f"I apologize, but I encountered an error while searching the {self.dataset_config.display_name} dataset: {search_data.get('error', 'Unknown error')}"
                }
                
                # Emit error activity
                if session_id:
                    try:
                        sse_emitter.emit_agent_activity(
                            session_id=session_id,
                            agent_name=self.agent_name,
                            action="Search failed",
                            status="error",
                            details=search_data.get("error", "Unknown error")
                        )
                    except Exception as emit_error:
                        logger.warning(f"Failed to emit RAG agent error activity: {str(emit_error)}")
                
                return error_response
            
            # Process results with LLM
            search_results_list = search_data.get("results", [])
            result_count = len(search_results_list)
            
            if result_count == 0:
                no_results_response = {
                    "success": True,
                    "agent": self.agent_name,
                    "dataset": self.dataset_config.name,
                    "search_results": [],
                    "result_count": 0,
                    "response": f"I searched the {self.dataset_config.display_name} dataset but couldn't find any relevant information for your query: '{user_query}'. Please try rephrasing your question or ask about different topics related to {self.dataset_config.description.lower()}."
                }
                
                # Emit no results activity
                if session_id:
                    try:
                        sse_emitter.emit_agent_activity(
                            session_id=session_id,
                            agent_name=self.agent_name,
                            action="Search completed",
                            status="no-results",
                            details="No relevant documents found"
                        )
                    except Exception as emit_error:
                        logger.warning(f"Failed to emit RAG agent no-results activity: {str(emit_error)}")
                
                return no_results_response
            
            # Emit search results activity
            if session_id:
                try:
                    file_names = [r.get("fileName", "unknown") for r in search_results_list[:3]]
                    file_list = ", ".join(file_names)
                    if len(search_results_list) > 3:
                        file_list += f" and {len(search_results_list) - 3} more"
                    
                    sse_emitter.emit_agent_activity(
                        session_id=session_id,
                        agent_name=self.agent_name,
                        action="Generating response",
                        status="in-progress",
                        details=f"Found {result_count} documents: {file_list}"
                    )
                except Exception as emit_error:
                    logger.warning(f"Failed to emit RAG agent results activity: {str(emit_error)}")
            
            # Create context from search results
            context_parts = []
            for i, result in enumerate(search_results_list, 1):
                title = result.get("title", "Untitled")
                content = result.get("content", "")
                file_name = result.get("fileName", "Unknown file")
                
                context_parts.append(f"Document {i} - {title} (from {file_name}):\n{content}\n")
            
            context = "\n".join(context_parts)
            
            # Create prompt for LLM
            rag_prompt = f"""{self.dataset_config.system_prompt}

CONTEXT INFORMATION:
The following documents were found relevant to the user's query:

{context}

USER QUERY: {user_query}

{self.dataset_config.agent_instructions}

Please provide a comprehensive answer based on the context information above. If the context doesn't contain enough information to fully answer the question, be honest about the limitations while providing what information is available."""
            
            # Get LLM response
            try:
                if self.openai_client and settings.azure.azure_openai_deployment:
                    # Generate response using Azure OpenAI
                    response = self.openai_client.chat.completions.create(
                        model=settings.azure.azure_openai_deployment,
                        messages=[
                            {"role": "user", "content": rag_prompt}
                        ],
                        temperature=self.dataset_config.temperature,
                        max_tokens=self.dataset_config.max_tokens
                    )
                    
                    llm_response = response.choices[0].message.content if response.choices else "I apologize, but I couldn't generate a response."
                    
                else:
                    llm_response = f"Based on my search of the {self.dataset_config.display_name} dataset, I found {result_count} relevant documents. However, I cannot provide a detailed analysis as the LLM service is not configured."
            
            except Exception as llm_error:
                logger.error(f"❌ LLM error in RAG agent '{self.agent_name}': {llm_error}")
                llm_response = f"I found {result_count} relevant documents in the {self.dataset_config.display_name} dataset, but encountered an error while generating a detailed response. Here's a summary of what I found:\n\n"
                
                for i, result in enumerate(search_results_list[:3], 1):
                    title = result.get("title", "Untitled")
                    content = result.get("content", "")[:200] + "..." if len(result.get("content", "")) > 200 else result.get("content", "")
                    llm_response += f"{i}. {title}: {content}\n\n"
            
            # Final response
            final_response = {
                "success": True,
                "agent": self.agent_name,
                "dataset": self.dataset_config.name,
                "search_results": search_results_list,
                "result_count": result_count,
                "response": llm_response
            }
            
            # Emit completion activity
            if session_id:
                try:
                    response_preview = llm_response[:100] + "..." if len(llm_response) > 100 else llm_response
                    sse_emitter.emit_agent_activity(
                        session_id=session_id,
                        agent_name=self.agent_name,
                        action="Response generated",
                        status="completed",
                        details=f"Generated response based on {result_count} documents: {response_preview}"
                    )
                except Exception as emit_error:
                    logger.warning(f"Failed to emit RAG agent completion activity: {str(emit_error)}")
            
            logger.info(f"✅ {self.agent_name}: Successfully processed query")
            return final_response
            
        except Exception as e:
            error_msg = f"Error in RAG agent '{self.agent_name}': {str(e)}"
            logger.error(f"❌ {error_msg}")
            
            error_response = {
                "success": False,
                "agent": self.agent_name,
                "dataset": self.dataset_config.name,
                "error": error_msg,
                "response": f"I apologize, but I encountered an error while processing your query: {str(e)}"
            }
            
            # Emit error activity
            if session_id:
                try:
                    sse_emitter.emit_agent_activity(
                        session_id=session_id,
                        agent_name=self.agent_name,
                        action="Processing failed",
                        status="error",
                        details=str(e)
                    )
                except Exception as emit_error:
                    logger.warning(f"Failed to emit RAG agent error activity: {str(emit_error)}")
            
            return error_response

class RAGAgentService:
    """Service for managing dynamic RAG agents."""
    
    def __init__(self):
        """Initialize the RAG agent service."""
        self.agents: Dict[str, RAGAgent] = {}
        self._initialize_agents()
    
    def _initialize_agents(self):
        """Initialize RAG agents for all enabled datasets."""
        try:
            enabled_datasets = rag_datasets_config.get_enabled_datasets()
            
            for dataset_name, dataset_config in enabled_datasets.items():
                try:
                    agent = RAGAgent(dataset_config)
                    self.agents[dataset_name] = agent
                    logger.info(f"✅ Initialized RAG agent: {agent.agent_name}")
                except Exception as e:
                    logger.error(f"❌ Failed to initialize RAG agent for dataset '{dataset_name}': {e}")
            
            logger.info(f"🤖 RAG Agent Service initialized with {len(self.agents)} agents")
            
        except Exception as e:
            logger.error(f"Error initializing RAG agent service: {e}")
    
    def get_agent(self, dataset_name: str) -> Optional[RAGAgent]:
        """Get a specific RAG agent."""
        return self.agents.get(dataset_name)
    
    def get_all_agents(self) -> Dict[str, RAGAgent]:
        """Get all RAG agents."""
        return self.agents.copy()
    
    def get_available_datasets(self) -> List[str]:
        """Get list of available dataset names."""
        return list(self.agents.keys())
    
    def get_agent_info(self) -> List[Dict[str, Any]]:
        """Get information about all available RAG agents."""
        agent_info = []
        for dataset_name, agent in self.agents.items():
            info = {
                "dataset_name": dataset_name,
                "agent_name": agent.agent_name,
                "display_name": agent.dataset_config.display_name,
                "description": agent.dataset_config.description,
                "index": agent.dataset_config.azure_search_index,
                "enabled": agent.dataset_config.enabled,
                "max_results": agent.dataset_config.max_results
            }
            agent_info.append(info)
        return agent_info
    
    async def query_agent(self, dataset_name: str, user_query: str, 
                         session_id: str = None, user_id: str = None) -> Dict[str, Any]:
        """Query a specific RAG agent."""
        agent = self.get_agent(dataset_name)
        if not agent:
            return {
                "success": False,
                "error": f"RAG agent for dataset '{dataset_name}' not found",
                "available_datasets": list(self.agents.keys())
            }
        
        return await agent.process_query(user_query, session_id, user_id)
    
    def reload_agents(self):
        """Reload all RAG agents from configuration."""
        logger.info("🔄 Reloading RAG agents...")
        rag_datasets_config.reload_config()
        self.agents.clear()
        self._initialize_agents()

# Global service instance
rag_agent_service = RAGAgentService()
