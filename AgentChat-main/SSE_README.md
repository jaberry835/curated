# Server-Sent Events (SSE) Implementation

This project has been updated to use Server-Sent Events (SSE) instead of SocketIO for real-time agent activity streaming. This change simplifies deployment and removes the dependency on eventlet, which was causing issues with Azure App Service deployments.

## Architecture Changes

### Backend Changes
1. **Removed Dependencies**:
   - `flask-socketio==5.3.6`
   - `eventlet==0.40.1`

2. **New Components**:
   - `utils/sse_emitter.py`: SSE event emitter utility
   - `agents/sse_multi_agent_system.py`: SSE-aware multi-agent system wrapper
   - New SSE endpoint: `/sse/agent-activity/<session_id>`

3. **Updated Components**:
   - `api/app.py`: Removed SocketIO, added SSE endpoint
   - `api/agent_routes.py`: Uses SSE emitter instead of SocketIO emitter
   - `wsgi.py`: Simplified WSGI entry point without SocketIO
   - `main.py`: Standard Flask app without SocketIO

### Frontend Changes
1. **New Components**:
   - `services/agent-activity-sse.service.ts`: SSE-based agent activity service

2. **Updated Components**:
   - `services/agent-activity.service.ts`: Now uses SSE implementation
   - `components/agent-activity.component.ts`: Updated imports
   - `environments/`: Removed socketUrl configuration
   - `package.json`: Removed socket.io-client dependency

## Benefits

1. **Simplified Deployment**: No need for eventlet or special worker configurations
2. **Better Azure Compatibility**: Standard WSGI application without complex async requirements
3. **Reduced Dependencies**: Fewer packages to manage and potential conflicts
4. **Standard Web Technology**: SSE is a native web standard supported by all modern browsers
5. **Scalability**: Can use multiple Gunicorn workers without restrictions

## How It Works

### Server-Sent Events Flow
1. Frontend creates EventSource connection to `/sse/agent-activity/<session_id>`
2. Backend maintains a queue for each session
3. Agent activities are pushed to the session queue
4. SSE endpoint streams events from the queue to the connected client
5. Automatic reconnection on connection loss

### Event Types
- `agentActivity`: Real-time agent activities and progress updates
- `agentStatusUpdate`: Agent status changes
- `error`: Error messages
- `heartbeat`: Keep-alive messages (sent every 30 seconds)

## Usage

### Backend
```python
from utils.sse_emitter import sse_emitter

# Emit agent activity
sse_emitter.emit_agent_activity(
    session_id="session-123",
    agent_name="Document Agent",
    action="Processing document",
    status="in-progress",
    details="Analyzing PDF content"
)
```

### Frontend
```typescript
// The service automatically connects when joining a session
await this.agentActivityService.joinSession(sessionId);

// Subscribe to activities
this.agentActivityService.getActivities().subscribe(activities => {
  console.log('Agent activities:', activities);
});
```

## Deployment

### Local Development
```bash
# Backend
cd PythonAPI
python main.py

# Frontend
ng serve
```

### Azure App Service
The application now uses standard Flask deployment:
- Startup command: `gunicorn --bind 0.0.0.0:8000 wsgi:app`
- No need for eventlet worker class
- Can use multiple workers for better performance

## Migration Notes

- All existing functionality remains the same from a user perspective
- Agent activities still stream in real-time
- The UI remains unchanged
- Performance should be better due to simplified architecture

## Troubleshooting

### SSE Connection Issues
1. Check if the SSE endpoint is accessible: `GET /sse/agent-activity/{sessionId}`
2. Verify CORS headers are configured properly
3. Check browser network tab for SSE connection status
4. Look for EventSource errors in browser console

### Agent Activities Not Appearing
1. Verify the session ID is correctly passed to the SSE emitter
2. Check backend logs for SSE emission events
3. Ensure the agent system is using the SSE wrapper
4. Confirm the frontend is subscribed to the correct session
