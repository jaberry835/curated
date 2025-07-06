"""SSE-aware wrapper for the multi-agent system."""

import asyncio
from typing import Optional
from utils.logging import get_logger
from utils.sse_emitter import sse_emitter
from agents.multi_agent_system import MultiAgentSystem

logger = get_logger(__name__)


class SSEMultiAgentSystem:
    """Wrapper around MultiAgentSystem that emits SSE events during processing."""
    
    def __init__(self, azure_endpoint: str, azure_api_key: str, azure_deployment: str, mcp_server_url: str):
        self.agent_system = MultiAgentSystem(azure_endpoint, azure_api_key, azure_deployment, mcp_server_url)
        self._current_session_id: Optional[str] = None
        self._current_user_id: Optional[str] = None
    
    async def initialize(self) -> bool:
        """Initialize the underlying agent system."""
        try:
            return await self.agent_system.initialize()
        except Exception as e:
            logger.error(f"Error initializing SSE-aware agent system: {str(e)}")
            return False
    
    async def cleanup(self):
        """Cleanup the underlying agent system."""
        try:
            await self.agent_system.cleanup()
        except Exception as e:
            logger.error(f"Error cleaning up SSE-aware agent system: {str(e)}")
    
    def set_session_id(self, session_id: str):
        """Set the current session ID for SSE events."""
        self._current_session_id = session_id
    
    def set_user_id(self, user_id: str):
        """Set the current user ID for context."""
        self._current_user_id = user_id
    
    def _emit_activity(self, agent_name: str, action: str, status: str, details: str = None):
        """Emit SSE activity if we have a session ID."""
        if self._current_session_id:
            try:
                sse_emitter.emit_agent_activity(
                    session_id=self._current_session_id,
                    agent_name=agent_name,
                    action=action,
                    status=status,
                    details=details
                )
            except Exception as e:
                logger.error(f"Error emitting SSE activity: {str(e)}")
    
    async def process_question(self, question: str, session_id: Optional[str] = None, user_id: Optional[str] = None) -> str:
        """Process a question with SSE event emission.
        
        Args:
            question: The user's question to process
            session_id: The session ID for context and event emission
            user_id: The user ID for context and document access control
        """
        if session_id:
            self.set_session_id(session_id)
            
        if user_id:
            self.set_user_id(user_id)
        
        try:
            # Emit initial processing
            self._emit_activity(
                agent_name="Multi-Agent System",
                action="Analyzing message",
                status="in-progress",
                details=f"Processing question: {question}"
            )
            
            self._emit_activity(
                agent_name="Coordinator Agent",
                action="Starting question analysis",
                status="starting",
                details=f"Analyzing: {question}"
            )
            
            # Emit when determining agent strategy
            self._emit_activity(
                agent_name="Coordinator Agent",
                action="Determining agent strategy",
                status="in-progress",
                details="Identifying which agents to involve"
            )
            
            # Use the main system's process_question method which handles everything
            result = await self.agent_system.process_question(question, session_id, user_id)
            
            # Emit completion
            self._emit_activity(
                agent_name="Multi-Agent System",
                action="Question processing completed",
                status="completed",
                details="Final response generated successfully"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing question: {str(e)}")
            self._emit_activity(
                agent_name="System",
                action="Error processing question",
                status="error",
                details=f"Error: {str(e)}"
            )
            raise
