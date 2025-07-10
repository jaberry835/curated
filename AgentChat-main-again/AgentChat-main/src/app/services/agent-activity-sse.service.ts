import { Injectable, signal } from '@angular/core';
import { environment } from '../../environments/environment';

export interface AgentActivity {
  id: string;
  agentId: string;
  agentName: string;
  action: string;
  status: 'starting' | 'in-progress' | 'completed' | 'error';
  timestamp: Date;
  details?: string;
  duration?: number;
}

export interface AgentStatus {
  agentId: string;
  name: string;
  status: 'idle' | 'active' | 'error';
  currentActivity?: string;
  lastActivity?: Date;
  domains: string[];
}

@Injectable({
  providedIn: 'root'
})
export class AgentActivityService {
  private _activities = signal<AgentActivity[]>([]);
  private _agentStatuses = signal<AgentStatus[]>([
    {
      agentId: 'core-agent',
      name: 'Core Agent',
      status: 'idle',
      domains: ['core', 'system', 'basic']
    },
    {
      agentId: 'adx-agent',
      name: 'ADX Agent',
      status: 'idle',
      domains: ['adx', 'data-explorer', 'kusto']
    },
    {
      agentId: 'maps-agent',
      name: 'Maps Agent',
      status: 'idle',
      domains: ['maps', 'location', 'geocoding']
    },
    {
      agentId: 'document-agent',
      name: 'Document Agent',
      status: 'idle',
      domains: ['documents', 'pdf', 'text-analysis']
    }
  ]);
  
  private eventSource?: EventSource;
  private currentSessionId?: string;

  private pollingInterval: any = null;
  private usePolling = false;
  private pollingUrl = '';

  constructor() {
    // console.log('🔄 AgentActivityService: Using SSE implementation');
  }

  // Public readonly signals for components
  readonly activities = this._activities.asReadonly();
  readonly agentStatuses = this._agentStatuses.asReadonly();

  async joinSession(sessionId: string) {
    // console.log('🚀 Joining session with SSE:', sessionId);
    
    // Validate sessionId
    if (!sessionId || sessionId === 'undefined' || sessionId === 'null') {
      console.error('❌ Invalid sessionId provided to joinSession:', sessionId);
      return;
    }

    // Clear activities when switching to a new session
    if (this.currentSessionId !== sessionId) {
      // console.log('🔄 Switching from session', this.currentSessionId, 'to', sessionId, '- clearing activities');
      this.clearActivities();
    }

    this.currentSessionId = sessionId;

    // Close existing EventSource if any
    if (this.eventSource) {
      // console.log('🔌 Closing existing SSE connection');
      this.eventSource.close();
    }

    try {
      // Create new EventSource connection
      const sseUrl = `${environment.api.baseUrl}/sse/agent-activity/${sessionId}`;
      // console.log('🔌 Connecting to SSE:', sseUrl);
      
      this.eventSource = new EventSource(sseUrl);
      
      this.eventSource.onopen = () => {
        // console.log('✅ SSE connection established for session:', sessionId);
      };

      this.eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data);
          // console.log('📊 Received SSE message:', data);
          
          if (data.event === 'connected') {
            // console.log('📡 SSE connection confirmed');
          } else if (data.event === 'heartbeat') {
            // console.log('💓 SSE heartbeat');
          }
        } catch (error) {
          console.error('❌ Error parsing SSE message:', error);
        }
      };

      this.eventSource.addEventListener('agentActivity', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data);
          // console.log('📊 Processing SSE agent activity:', data);
          this.handleRealtimeAgentActivity(data);
        } catch (error) {
          console.error('❌ Error processing agent activity:', error);
        }
      });

      this.eventSource.addEventListener('agentStatusUpdate', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data);
          // console.log('📊 Processing SSE agent status update:', data);
          // Handle status updates if needed
        } catch (error) {
          console.error('❌ Error processing agent status update:', error);
        }
      });

      this.eventSource.addEventListener('error', (event) => {
        console.error('❌ SSE error event received:', event);
        // Error events don't have data property
      });

      this.eventSource.onerror = (error) => {
        console.error('❌ SSE connection error:', error);
        
        // Try to reconnect after a delay
        setTimeout(() => {
          if (this.currentSessionId === sessionId) {
            // console.log('🔄 Attempting to reconnect SSE...');
            this.joinSession(sessionId);
          }
        }, 5000);
      };

      // console.log('✅ SSE connection setup completed');
      
    } catch (error) {
      console.error('❌ Error setting up SSE connection:', error);
    }
  }

  async leaveSession() {
    if (!this.currentSessionId) {
      // console.log('ℹ️ No active session to leave');
      return;
    }

    const sessionId = this.currentSessionId;
    // console.log('👋 Leaving session:', sessionId);

    if (this.eventSource) {
      // console.log('🔌 Closing SSE connection');
      this.eventSource.close();
      this.eventSource = undefined;
    }

    this.currentSessionId = undefined;
    this.clearActivities();
  }

  private handleRealtimeAgentActivity(data: any) {
    // console.log('📊 Processing real-time agent activity:', data);
    
    const activity: AgentActivity = {
      id: data.id || this.generateId(),
      agentId: data.agentName?.toLowerCase().replace(/\s+/g, '-') || 'unknown',
      agentName: data.agentName || 'Unknown Agent',
      action: data.action || 'Unknown Action',
      status: this.mapStatusFromBackend(data.status),
      timestamp: new Date(data.timestamp || Date.now()),
      details: data.result || data.details,
      duration: data.duration ? this.convertTimeSpanToMs(data.duration) : undefined
    };

    // Update the signal - add to end of array for chronological order (newest at end)
    this._activities.update(activities => {
      const newActivities = [...activities.slice(-99), activity];
      // console.log('📊 Updated activities signal - before:', activities.length, 'after:', newActivities.length);
      return newActivities;
    });
    
    this.updateAgentStatus(activity.agentId, activity.status, activity.action);
    
    // console.log('✅ Agent activity processed and added to list - current count:', this._activities().length);
  }

  private mapStatusFromBackend(status: string): AgentActivity['status'] {
    switch (status?.toLowerCase()) {
      case 'starting':
        return 'starting';
      case 'in-progress':
      case 'in_progress':
        return 'in-progress';
      case 'completed':
      case 'success':
        return 'completed';
      case 'error':
      case 'failed':
        return 'error';
      default:
        return 'in-progress';
    }
  }

  private convertTimeSpanToMs(timeSpan: any): number {
    if (typeof timeSpan === 'number') {
      return timeSpan;
    }
    
    if (typeof timeSpan === 'string') {
      // Handle TimeSpan format like "00:00:05.1234567"
      const parts = timeSpan.split(':');
      if (parts.length === 3) {
        const hours = parseInt(parts[0], 10);
        const minutes = parseInt(parts[1], 10);
        const seconds = parseFloat(parts[2]);
        return ((hours * 3600) + (minutes * 60) + seconds) * 1000;
      }
    }
    
    return 0;
  }

  // Public methods for manual activity management
  addActivity(activity: Omit<AgentActivity, 'id' | 'timestamp'>): string {
    const id = this.generateId();
    const newActivity: AgentActivity = {
      ...activity,
      id,
      timestamp: new Date()
    };
    
    this._activities.update(activities => [...activities.slice(-99), newActivity]);
    this.updateAgentStatus(newActivity.agentId, newActivity.status, newActivity.action);
    
    return id;
  }

  addActivities(activitiesList: Omit<AgentActivity, 'id' | 'timestamp'>[]): string[] {
    return activitiesList.map(activity => this.addActivity(activity));
  }

  updateActivity(id: string, updates: Partial<AgentActivity>) {
    this._activities.update(activities =>
      activities.map(activity => 
        activity.id === id ? { ...activity, ...updates } : activity
      )
    );
  }

  clearActivities() {
    // console.log('🧹 Clearing activities - before:', this._activities().length);
    this._activities.set([]);
    // console.log('🧹 Clearing activities - after:', this._activities().length);
    
    // Reset all agent statuses to idle
    this._agentStatuses.update(statuses =>
      statuses.map(status => ({
        ...status,
        status: 'idle' as const,
        currentActivity: undefined
      }))
    );
  }

  private updateAgentStatus(agentId: string, status: AgentActivity['status'], activity: string) {
    this._agentStatuses.update(statuses =>
      statuses.map(agentStatus => 
        agentStatus.agentId === agentId
          ? {
              ...agentStatus,
              status: (status === 'error' ? 'error' : (status === 'completed' ? 'idle' : 'active')) as AgentStatus['status'],
              currentActivity: status === 'completed' ? undefined : activity,
              lastActivity: new Date()
            }
          : agentStatus
      )
    );
  }

  private generateId(): string {
    return Date.now().toString(36) + Math.random().toString(36).substr(2);
  }

  // Health check methods
  ping() {
    console.log('🏓 SSE ping - connection health check');
    // For SSE, we can't really ping, but we can check if connection is open
    if (this.eventSource && this.eventSource.readyState === EventSource.OPEN) {
      console.log('✅ SSE connection is healthy');
    } else {
      console.log('❌ SSE connection is not healthy');
    }
  }

  isConnected(): boolean {
    return this.eventSource?.readyState === EventSource.OPEN;
  }

  getCurrentSessionId(): string | undefined {
    return this.currentSessionId;
  }

  // Cleanup
  disconnect() {
    if (this.eventSource) {
      console.log('🔌 Disconnecting SSE');
      this.eventSource.close();
      this.eventSource = undefined;
    }
  }
}
