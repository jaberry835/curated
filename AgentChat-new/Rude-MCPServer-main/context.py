"""
Shared context variables for the MCP server
Used by both main.py and tools for request-scoped data
"""

from contextvars import ContextVar

# Context variables to store request data
current_user_id: ContextVar[str] = ContextVar('current_user_id', default='defaMCPUser')
current_session_id: ContextVar[str] = ContextVar('current_session_id', default=None)
current_user_token: ContextVar[str] = ContextVar('current_user_token', default=None)
