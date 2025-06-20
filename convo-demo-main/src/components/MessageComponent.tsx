import React from 'react';
import { Message } from '../types/conversation';
import './MessageComponent.css';

interface MessageComponentProps {
  message: Message;
}

const MessageComponent: React.FC<MessageComponentProps> = ({ message }) => {
  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString([], { 
      hour: '2-digit', 
      minute: '2-digit' 
    });
  };

  const getStageColor = (stage: string) => {
    const stageColors: { [key: string]: string } = {
      'initiation': '#007bff',
      'specification': '#28a745',
      'payment': '#ffc107',
      'finalization': '#17a2b8',
      'offer_extra': '#6f42c1'
    };
    return stageColors[stage] || '#6c757d';
  };

  return (
    <div className={`message ${message.role.toLowerCase()}`}>
      <div className="message-header">
        <div className="message-info">
          <span className="handle">{message.handle}</span>
          <span className="role">{message.role}</span>
          <span className="timestamp">{formatTimestamp(message.timestamp)}</span>
        </div>
        <div className="message-meta">
          <span 
            className="stage-badge"
            style={{ backgroundColor: getStageColor(message.negotiation_stage) }}
          >
            {message.negotiation_stage}
          </span>
          {message.coded_language && (
            <span className="coded-indicator" title="Uses coded language">
              🔒
            </span>
          )}
          {message.security_flags.encrypted && (
            <span className="encrypted-indicator" title="Encrypted communication">
              🛡️
            </span>
          )}
        </div>
      </div>
      
      <div className="message-content">
        <p>{message.message}</p>
      </div>
      
      {message.payment_details && (
        <div className="payment-details">
          <h4>Payment Information:</h4>
          {message.payment_details.escrow_id && (
            <p><strong>Escrow ID:</strong> {message.payment_details.escrow_id}</p>
          )}
          {message.payment_details.crypto_wallet && (
            <p><strong>Wallet:</strong> {message.payment_details.crypto_wallet}</p>
          )}
          {message.payment_details.transaction_id && (
            <p><strong>Transaction ID:</strong> {message.payment_details.transaction_id}</p>
          )}
          {message.payment_details.amount && (
            <p><strong>Amount:</strong> {message.payment_details.amount}</p>
          )}
          {message.payment_details.transaction_status && (
            <p><strong>Status:</strong> {message.payment_details.transaction_status}</p>
          )}
        </div>
      )}
    </div>
  );
};

export default MessageComponent;
