import React, { useEffect, useRef } from 'react';
import MessageComponent from './MessageComponent';
import MessageInput from './MessageInput';
import './ConversationPanel.css';
import { Message } from '../types/conversation';

interface ConversationPanelProps {
  messages: Message[];
  isBotTyping: boolean;
  onSendMessage: (messageText: string) => Promise<void>;
  started: boolean;
  draftMessage: string;              // Current draft message from Copilot selection or user input
  setDraftMessage: React.Dispatch<React.SetStateAction<string>>;
}

const ConversationPanel: React.FC<ConversationPanelProps> = ({ messages, isBotTyping, onSendMessage, started, draftMessage, setDraftMessage }) => {
  // Ref for messages container to enable auto-scrolling
  const containerRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom whenever messages change
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTo({ top: containerRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, [messages]);
  const currentStage = messages.length > 0 ? messages[messages.length - 1].negotiation_stage : '';
  return (
    <div className="conversation-panel">
      <div className="conversation-header">
        <h2>AI Negotiation Simulation</h2>
        {/* initiation controls moved to CopilotPanel */}
      </div>
      {started && currentStage && (
        <div className="stage-display">
          <span className="stage-label">Negotiation Stage:</span>
          <span className={`stage-badge ${currentStage}`}>{currentStage}</span>
        </div>
      )}

      <div className="messages-container" ref={containerRef}>
        {isBotTyping && <div className="bot-typing-indicator">SilverHawk is typing...</div>}
        {messages.map((m, i) => <MessageComponent key={i} message={m} />)}
      </div>

      <MessageInput
        onSendMessage={onSendMessage}
        disabled={!started}
        value={draftMessage}
        onChangeValue={setDraftMessage}
      />
    </div>
  );
};

export default ConversationPanel;
