"""Azure Cosmos DB service for chat sessions and messages."""

from typing import List, Dict, Any, Optional, Tuple

try:
    from ..utils.logging import get_logger
except ImportError:
    from utils.logging import get_logger

from .cosmos_client import cosmos_client
from .session_service import session_service
from .message_service import message_service

logger = get_logger(__name__)


class CosmosDBService:
    """Main service for managing chat sessions and messages in Azure Cosmos DB.
    
    This service acts as a facade that delegates to specialized services:
    - SessionService: Handles session operations
    - MessageService: Handles message operations
    - CosmosDBClient: Handles connection and configuration
    """
    
    def __init__(self):
        self.client = cosmos_client
        self.sessions = session_service
        self.messages = message_service
    
    def is_available(self) -> bool:
        """Check if Cosmos DB is available."""
        return self.client.is_available()
    
    def get_config(self) -> dict:
        """Get current Cosmos DB configuration."""
        return self.client.get_config()
    
    def reconnect(self):
        """Reconnect to Cosmos DB (useful for error recovery)."""
        self.client.reconnect()
    
    # Session management methods (delegate to session_service)
    
    async def create_session(self, user_id: str, title: str) -> Dict[str, Any]:
        """Create a new chat session."""
        return await self.sessions.create_session(user_id, title)
    
    async def get_user_sessions(self, user_id: str, page_size: int = 20, continuation_token: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Optional[str], bool]:
        """Get sessions for a user with pagination."""
        return await self.sessions.get_user_sessions(user_id, page_size, continuation_token)
    
    async def get_session(self, session_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific session."""
        return await self.sessions.get_session(session_id, user_id)
    
    async def update_session(self, session_id: str, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update a session."""
        return await self.sessions.update_session(session_id, user_id, updates)
    
    async def delete_session(self, session_id: str, user_id: str):
        """Delete a session and all its messages."""
        # Delete messages first
        await self.messages.delete_session_messages(session_id, user_id)
        # Then delete the session
        await self.sessions.delete_session(session_id, user_id)
    
    async def archive_session(self, session_id: str, user_id: str) -> Dict[str, Any]:
        """Archive a session instead of deleting it."""
        return await self.sessions.archive_session(session_id, user_id)
    
    async def add_document_to_session(self, session_id: str, user_id: str, document_info: Dict[str, Any]) -> Dict[str, Any]:
        """Add a document to a session's documents list."""
        return await self.sessions.add_document_to_session(session_id, user_id, document_info)
    
    async def remove_document_from_session(self, session_id: str, user_id: str, document_id: str) -> Dict[str, Any]:
        """Remove a document from a session's documents list."""
        return await self.sessions.remove_document_from_session(session_id, user_id, document_id)
    
    # Message management methods (delegate to message_service)
    
    async def save_message(self, session_id: str, user_id: str, message_id: str, role: str, content: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """Save a message to a session."""
        return await self.messages.save_message(session_id, user_id, message_id, role, content, metadata)
    
    async def get_session_messages(self, session_id: str, user_id: str, page_size: int = 20, continuation_token: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Optional[str], bool]:
        """Get messages for a session with pagination."""
        return await self.messages.get_session_messages(session_id, user_id, page_size, continuation_token)
    
    async def get_message(self, message_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific message."""
        return await self.messages.get_message(message_id, user_id)
    
    async def update_message(self, message_id: str, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update a message."""
        return await self.messages.update_message(message_id, user_id, updates)
    
    async def delete_session_messages(self, session_id: str, user_id: str):
        """Delete all messages for a session."""
        return await self.messages.delete_session_messages(session_id, user_id)
    
    async def search_messages(self, user_id: str, search_term: str, page_size: int = 20, continuation_token: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Optional[str], bool]:
        """Search messages by content."""
        return await self.messages.search_messages(user_id, search_term, page_size, continuation_token)


# Global instance
cosmos_service = CosmosDBService()
