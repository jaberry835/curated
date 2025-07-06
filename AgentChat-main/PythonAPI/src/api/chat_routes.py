"""Flask API endpoints for chat sessions and messages using Cosmos DB."""

from flask import Blueprint, request, jsonify
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Dict, Any

from utils.logging import get_logger
from services.cosmos_service import cosmos_service

logger = get_logger(__name__)

# Create blueprint for chat routes
chat_bp = Blueprint('chat', __name__, url_prefix='/api/chat')


@chat_bp.route('/sessions', methods=['GET'])
def get_sessions():
    """Get user's chat sessions."""
    try:
        user_id = request.args.get('userId')
        page_size = int(request.args.get('pageSize', 20))
        continuation_token = request.args.get('continuationToken')
        
        if not user_id:
            return jsonify({"error": "userId parameter is required"}), 400
        
        # Check if Cosmos DB is available
        if not cosmos_service.is_available():
            return jsonify({"error": "Database not available"}), 500
        
        # Get sessions from Cosmos DB
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            sessions, next_token, has_more = loop.run_until_complete(
                cosmos_service.get_user_sessions(user_id, page_size, continuation_token)
            )
        finally:
            loop.close()
        
        # Convert sessions to expected format
        user_sessions = []
        for session in sessions:
            session_data = {
                "id": session["id"],
                "title": session["title"],
                "createdAt": session["createdAt"],
                "updatedAt": session.get("updatedAt", session["createdAt"]),
                "userId": session["userId"],
                "messages": []  # Messages are loaded separately
            }
            user_sessions.append(session_data)
        
        response = {
            "sessions": user_sessions,
            "hasMore": has_more,
            "continuationToken": next_token
        }
        
        logger.info(f"Retrieved {len(user_sessions)} sessions for user: {user_id}")
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error getting sessions: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@chat_bp.route('/session', methods=['POST'])
def create_session():
    """Create a new chat session."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        user_id = data.get('userId')
        title = data.get('title', f"New Chat {datetime.now().strftime('%H:%M:%S')}")
        
        if not user_id:
            return jsonify({"error": "userId is required"}), 400
        
        # Check if Cosmos DB is available
        if not cosmos_service.is_available():
            return jsonify({"error": "Database not available"}), 500
        
        # Create session using Cosmos DB
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            session = loop.run_until_complete(
                cosmos_service.create_session(user_id, title)
            )
        finally:
            loop.close()
        
        logger.info(f"Created new session: {session['id']} for user: {user_id}")
        
        return jsonify({"sessionId": session["id"]})
        
    except Exception as e:
        logger.error(f"Error creating session: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@chat_bp.route('/session/<session_id>', methods=['GET'])
def get_session(session_id: str):
    """Get session details."""
    try:
        user_id = request.args.get('userId')
        if not user_id:
            return jsonify({"error": "userId parameter is required"}), 400
        
        # Check if Cosmos DB is available
        if not cosmos_service.is_available():
            return jsonify({"error": "Database not available"}), 500
        
        # Get session from Cosmos DB
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            session = loop.run_until_complete(
                cosmos_service.get_session(session_id, user_id)
            )
        finally:
            loop.close()
        
        if not session:
            return jsonify({"error": "Session not found"}), 404
        
        return jsonify(session), 200
    
    except Exception as e:
        logger.error(f"Error getting session {session_id}: {str(e)}")
        return jsonify({
            "error": "Session error", 
            "message": str(e)
        }), 500


@chat_bp.route('/session/<session_id>', methods=['PUT'])
def update_session(session_id: str):
    """Update a chat session."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        user_id = data.get('userId')
        if not user_id:
            return jsonify({"error": "userId is required"}), 400
        
        # Check if Cosmos DB is available
        if not cosmos_service.is_available():
            return jsonify({"error": "Database not available"}), 500
        
        # Get session from Cosmos DB to verify it exists and user owns it
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            session = loop.run_until_complete(
                cosmos_service.get_session(session_id, user_id)
            )
            
            if not session:
                return jsonify({"error": "Session not found"}), 404
            
            # Prepare updates
            updates = {}
            if 'title' in data:
                updates['title'] = data['title']
            
            if updates:
                loop.run_until_complete(
                    cosmos_service.update_session(session_id, user_id, updates)
                )
                
        finally:
            loop.close()
        
        logger.info(f"Updated session: {session_id}")
        return jsonify({"success": True})
        
    except Exception as e:
        logger.error(f"Error updating session: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@chat_bp.route('/session/<session_id>', methods=['DELETE'])
def delete_session(session_id: str):
    """Delete a chat session and all its messages."""
    try:
        user_id = request.args.get('userId')
        if not user_id:
            return jsonify({"error": "userId parameter is required"}), 400
        
        # Check if Cosmos DB is available
        if not cosmos_service.is_available():
            return jsonify({"error": "Database not available"}), 500
        
        # Delete session using Cosmos DB
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(
                cosmos_service.delete_session(session_id, user_id)
            )
        finally:
            loop.close()
        
        logger.info(f"Deleted session: {session_id}")
        return jsonify({"success": True}), 200
        
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@chat_bp.route('/message', methods=['POST'])
def save_message():
    """Save a message to a session."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        session_id = data.get('sessionId')
        user_id = data.get('userId')
        message_id = data.get('id')
        role = data.get('role')
        content = data.get('content')
        timestamp = data.get('timestamp')
        
        if not all([session_id, user_id, message_id, role, content]):
            return jsonify({"error": "sessionId, userId, id, role, and content are required"}), 400
        
        # Check if Cosmos DB is available
        if not cosmos_service.is_available():
            return jsonify({"error": "Database not available"}), 500
        
        # Verify session exists and user owns it
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            session = loop.run_until_complete(
                cosmos_service.get_session(session_id, user_id)
            )
            
            if not session:
                return jsonify({"error": "Session not found"}), 404
            
            # Save message to Cosmos DB
            saved_message = loop.run_until_complete(
                cosmos_service.save_message(
                    session_id=session_id,
                    user_id=user_id,
                    message_id=message_id,
                    role=role,
                    content=content,
                    metadata={
                        "timestamp": timestamp or datetime.now(timezone.utc).isoformat()
                    }
                )
            )
            
        finally:
            loop.close()
        
        logger.info(f"Saved message to session: {session_id}")
        return jsonify({"messageId": message_id})
        
    except Exception as e:
        logger.error(f"Error saving message: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@chat_bp.route('/history', methods=['GET'])
def get_chat_history():
    """Get chat history/messages for a session."""
    try:
        session_id = request.args.get('sessionId')
        user_id = request.args.get('userId')
        page_size = int(request.args.get('pageSize', 20))
        continuation_token = request.args.get('continuationToken')
        
        if not session_id or not user_id:
            return jsonify({"error": "sessionId and userId parameters are required"}), 400
        
        # Check if Cosmos DB is available
        if not cosmos_service.is_available():
            return jsonify({"error": "Database not available"}), 500
        
        # Get messages from Cosmos DB
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            messages, next_token, has_more = loop.run_until_complete(
                cosmos_service.get_session_messages(session_id, user_id, page_size, continuation_token)
            )
        finally:
            loop.close()
        
        # Convert messages to expected format
        chat_messages = []
        for msg in messages:
            message_data = {
                "id": msg["id"],
                "role": msg["role"],
                "content": msg["content"],
                "timestamp": msg["timestamp"],
                "sessionId": msg["sessionId"]
            }
            # Add metadata if present
            if "metadata" in msg and msg["metadata"]:
                message_data.update(msg["metadata"])
            
            chat_messages.append(message_data)
        
        response = {
            "messages": chat_messages,
            "hasMore": has_more,
            "continuationToken": next_token
        }
        
        logger.info(f"Retrieved {len(chat_messages)} messages for session: {session_id}")
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error getting chat history: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@chat_bp.route('/messages/<session_id>', methods=['GET'])
def get_session_messages(session_id: str):
    """Get messages for a session with pagination."""
    try:
        user_id = request.args.get('userId')
        page_size = int(request.args.get('pageSize', 20))
        continuation_token = request.args.get('continuationToken')
        
        if not user_id:
            return jsonify({"error": "userId parameter is required"}), 400
        
        # Check if Cosmos DB is available
        if not cosmos_service.is_available():
            return jsonify({"error": "Database not available"}), 500
        
        # Get messages from Cosmos DB
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            messages, next_token, has_more = loop.run_until_complete(
                cosmos_service.get_session_messages(session_id, user_id, page_size, continuation_token)
            )
        finally:
            loop.close()
        
        # Return messages in expected format
        response = {
            "messages": messages,
            "hasMore": has_more,
            "continuationToken": next_token
        }
        
        return jsonify(response), 200
    
    except Exception as e:
        logger.error(f"Error getting messages for session {session_id}: {str(e)}")
        return jsonify({
            "error": "Messages error", 
            "message": str(e)
        }), 500


@chat_bp.route('/search', methods=['GET'])
def search_messages():
    """Search messages by content."""
    try:
        user_id = request.args.get('userId')
        search_term = request.args.get('q')
        page_size = int(request.args.get('pageSize', 20))
        continuation_token = request.args.get('continuationToken')
        
        if not user_id or not search_term:
            return jsonify({"error": "userId and q parameters are required"}), 400
        
        # Check if Cosmos DB is available
        if not cosmos_service.is_available():
            return jsonify({"error": "Database not available"}), 500
        
        # Search messages in Cosmos DB
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            messages, next_token, has_more = loop.run_until_complete(
                cosmos_service.search_messages(user_id, search_term, page_size, continuation_token)
            )
        finally:
            loop.close()
        
        response = {
            "messages": messages,
            "hasMore": has_more,
            "continuationToken": next_token,
            "searchTerm": search_term
        }
        
        logger.info(f"Found {len(messages)} messages matching '{search_term}' for user {user_id}")
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error searching messages: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
