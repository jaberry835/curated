"""Server-Sent Events (SSE) emitter utility for agent activity streaming."""

import json
import uuid
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from queue import Queue, Empty
from utils.logging import get_logger

logger = get_logger(__name__)


class SSEEmitter:
    """Utility class for managing Server-Sent Events streams."""
    
    def __init__(self):
        self._sessions: Dict[str, Queue] = {}
        self._lock = threading.Lock()
        
    def add_session(self, session_id: str) -> Queue:
        """Add a new SSE session and return its queue."""
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = Queue()
                logger.info(f"📡 Added SSE session: {session_id}")
            return self._sessions[session_id]
    
    def remove_session(self, session_id: str):
        """Remove an SSE session."""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info(f"📡 Removed SSE session: {session_id}")
    
    def emit_agent_activity(
        self,
        session_id: str,
        agent_name: str,
        action: str,
        status: str,
        details: Optional[str] = None,
        duration: Optional[float] = None
    ):
        """Emit agent activity event to a specific session."""
        try:
            activity_data = {
                "id": str(uuid.uuid4()),
                "agentName": agent_name,
                "action": action,
                "status": status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": details,
                "duration": duration
            }
            
            logger.info(f"📊 Emitting agent activity to session {session_id}: {agent_name} - {action} ({status})")
            
            self._emit_to_session(session_id, 'agentActivity', activity_data)
            
        except Exception as e:
            logger.error(f"Error emitting agent activity: {str(e)}")
    
    def emit_agent_status_update(
        self,
        session_id: str,
        agent_id: str,
        agent_name: str,
        status: str,
        current_activity: Optional[str] = None
    ):
        """Emit agent status update event."""
        try:
            status_data = {
                "agentId": agent_id,
                "name": agent_name,
                "status": status,
                "currentActivity": current_activity,
                "lastActivity": datetime.now(timezone.utc).isoformat()
            }
            
            logger.info(f"📊 Emitting agent status update to session {session_id}: {agent_name} - {status}")
            
            self._emit_to_session(session_id, 'agentStatusUpdate', status_data)
            
        except Exception as e:
            logger.error(f"Error emitting agent status update: {str(e)}")
    
    def emit_error(self, session_id: str, message: str, details: Optional[str] = None):
        """Emit error event to a specific session."""
        try:
            error_data = {
                "message": message,
                "details": details,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            logger.error(f"📊 Emitting error to session {session_id}: {message}")
            
            self._emit_to_session(session_id, 'error', error_data)
            
        except Exception as e:
            logger.error(f"Error emitting error event: {str(e)}")
    
    def _emit_to_session(self, session_id: str, event_type: str, data: Dict[str, Any]):
        """Emit data to a specific session."""
        with self._lock:
            if session_id in self._sessions:
                queue = self._sessions[session_id]
                try:
                    # Create SSE formatted message
                    sse_message = {
                        'event': event_type,
                        'data': data,
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }
                    queue.put(sse_message, timeout=1)
                except Exception as e:
                    logger.error(f"Error queuing message to session {session_id}: {str(e)}")
    
    def get_session_stream(self, session_id: str):
        """Get SSE stream generator for a session."""
        queue = self.add_session(session_id)
        
        def generate():
            try:
                # Send initial connection message immediately
                initial_message = json.dumps({
                    'event': 'connected', 
                    'data': {
                        'message': 'SSE connection established',
                        'session_id': session_id,
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }
                })
                yield f"data: {initial_message}\n\n"
                
                # Main loop with shorter timeouts for Azure threading
                while True:
                    try:
                        # Shorter timeout works better with threaded workers
                        message = queue.get(timeout=15)  # 15s timeout for threaded workers
                        
                        # Format as SSE
                        sse_data = f"event: {message['event']}\n"
                        sse_data += f"data: {json.dumps(message['data'])}\n\n"
                        
                        yield sse_data
                        
                    except Empty:
                        # Send heartbeat every 15 seconds
                        heartbeat = json.dumps({
                            'event': 'heartbeat', 
                            'data': {'timestamp': datetime.now(timezone.utc).isoformat()}
                        })
                        yield f"data: {heartbeat}\n\n"
                        
            except GeneratorExit:
                logger.info(f"📡 SSE stream ended for session: {session_id}")
                self.remove_session(session_id)
            except Exception as e:
                logger.error(f"Error in SSE stream for session {session_id}: {str(e)}")
                self.remove_session(session_id)
        
        return generate()


# Global SSE emitter instance
sse_emitter = SSEEmitter()
