import React, { useState } from 'react';
import { Suggestion } from '../types/conversation';
import './SuggestionCard.css';

interface SuggestionCardProps {
  suggestion: Suggestion;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  onSelectAction?: (text: string) => void; // Callback to prefill input
  onGetDetails?: () => void; // Callback to fetch and show more details
}

const SuggestionCard: React.FC<SuggestionCardProps> = ({ suggestion, onRefresh, isRefreshing = false, onSelectAction, onGetDetails }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const getTypeIcon = (type: string) => {
    const icons: { [key: string]: string } = {
      'pattern_analysis': '🔍',
      'negotiation_tactic': '💡',
      'risk_assessment': '⚠️',
      'next_move': '🎯'
    };
    return icons[type] || '📋';
  };

  const getConfidenceLevel = (confidence: number) => {
    if (confidence >= 0.8) return 'high';
    if (confidence >= 0.6) return 'medium';
    return 'low';
  };

  return (
    <div className={`suggestion-card ${suggestion.type}`}>
      <div className="suggestion-header" onClick={() => setIsExpanded(!isExpanded)}>
        <div className="suggestion-title">
          {/* Icon with type-specific class for styling */}
          <span className={`type-icon ${suggestion.type}`}>{getTypeIcon(suggestion.type)}</span>
          <h3>{suggestion.title}</h3>
        </div>
        <div className="suggestion-controls">
          {/* Rank badge */}
          <div className="rank-badge">#{suggestion.rank}</div>
          <div className={`confidence-badge ${getConfidenceLevel(suggestion.confidence)}`}>
            {Math.round(suggestion.confidence * 100)}% confidence
          </div>
          {onRefresh && (
            <button
              className="refresh-link"
              onClick={(e) => { e.stopPropagation(); onRefresh(); }}
              disabled={isRefreshing}
              title={isRefreshing ? 'Refreshing...' : 'Refresh this suggestion'}
            >
              {isRefreshing ? '⏳' : '🔄'}
            </button>
          )}
          <button className={`expand-btn ${isExpanded ? 'expanded' : ''}`}>
            {isExpanded ? '▲' : '▼'}
          </button>
        </div>
      </div>

      {isExpanded && (
        <div className="suggestion-body">
          {/* Next logical response area */}
          <div className="next-response-area">
            <strong>Next focus:</strong> {suggestion.next_response_area}
          </div>
          <div className="suggestion-content">
            <p>{suggestion.content}</p>
          </div>

          {suggestion.action_items.length > 0 && (
            <div className="action-items">
              <h4>Recommended Actions:</h4>
              <ul>
                {suggestion.action_items.map((item, index) => (
                  <li key={index}>
                    <span className="action-bullet">→</span>
                    <span className="action-text">{item}</span>
                    {onSelectAction && (
                      <button
                        className="action-link"
                        onClick={(e) => { e.stopPropagation(); onSelectAction(item); }}
                        title="Use this action"
                      >
                        💬➔
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="suggestion-footer">
            <div className="suggestion-actions">
              <button className="action-btn primary">Apply Suggestion</button>
              <button className="action-btn secondary">Save for Later</button>
              <button
                className="action-btn tertiary"
                onClick={(e) => { e.stopPropagation(); onGetDetails && onGetDetails(); }}
              >Get More Details</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SuggestionCard;
