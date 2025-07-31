"""Token management service to prevent exceeding GPT-4o's 128K token limit with enhanced monitoring."""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import re
import time

try:
    from ..utils.logging import get_logger
except ImportError:
    from src.utils.logging import get_logger

logger = get_logger(__name__)


class TokenUsageMonitor:
    """Monitors token usage patterns and provides insights for optimization."""
    
    def __init__(self):
        self.usage_history: List[Dict[str, Any]] = []
        self.peak_usage = 0
        self.total_requests = 0
        self.truncation_events = 0
        
    def record_usage(self, 
                    context: str, 
                    tokens_used: int, 
                    max_tokens: int,
                    was_truncated: bool = False):
        """Record a token usage event for monitoring."""
        usage_record = {
            'timestamp': time.time(),
            'context': context,
            'tokens_used': tokens_used,
            'max_tokens': max_tokens,
            'usage_percentage': (tokens_used / max_tokens) * 100 if max_tokens > 0 else 0,
            'was_truncated': was_truncated
        }
        
        self.usage_history.append(usage_record)
        self.peak_usage = max(self.peak_usage, tokens_used)
        self.total_requests += 1
        
        if was_truncated:
            self.truncation_events += 1
        
        # Keep only recent history (last 1000 records)
        if len(self.usage_history) > 1000:
            self.usage_history = self.usage_history[-1000:]
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get comprehensive usage statistics."""
        if not self.usage_history:
            return {'no_data': True}
        
        recent_usage = [r['tokens_used'] for r in self.usage_history[-100:]]
        recent_percentages = [r['usage_percentage'] for r in self.usage_history[-100:]]
        
        return {
            'total_requests': self.total_requests,
            'peak_usage': self.peak_usage,
            'truncation_events': self.truncation_events,
            'truncation_rate': (self.truncation_events / self.total_requests) * 100,
            'recent_average_tokens': sum(recent_usage) / len(recent_usage) if recent_usage else 0,
            'recent_average_percentage': sum(recent_percentages) / len(recent_percentages) if recent_percentages else 0,
            'high_usage_requests': len([r for r in self.usage_history[-100:] if r['usage_percentage'] > 80]),
            'critical_usage_requests': len([r for r in self.usage_history[-100:] if r['usage_percentage'] > 95])
        }


class TokenManager:
    """Manages token counting and optimization for GPT-4o (128K token limit)."""
    
    # GPT-4o token limits (conservative estimates)
    MAX_TOKENS = 128000
    SAFE_LIMIT = 120000  # Leave buffer for response
    CONTEXT_RESERVE = 8000  # Reserve for system prompts, tools, etc.
    AVAILABLE_FOR_HISTORY = SAFE_LIMIT - CONTEXT_RESERVE  # ~112K for conversation history
    
    def __init__(self):
        """Initialize token manager with pure Python token estimation and monitoring."""
        logger.info("Using pure Python token estimation (production-safe)")
        self.usage_monitor = TokenUsageMonitor()
        self._warning_logged = False  # Prevent spam logging
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in a text string using character-based estimation.
        
        This uses a more accurate estimation than simple character division:
        - Average English: ~4 characters per token
        - Code/JSON: ~3.5 characters per token  
        - Numbers/symbols: ~2.5 characters per token
        
        Args:
            text: Text to count tokens for
            
        Returns:
            int: Number of tokens (estimated)
        """
        if not text:
            return 0
        
        # More sophisticated estimation based on content type
        text_length = len(text)
        
        # Count different character types for better estimation
        alpha_chars = sum(1 for c in text if c.isalpha())
        digit_chars = sum(1 for c in text if c.isdigit())
        space_chars = sum(1 for c in text if c.isspace())
        symbol_chars = text_length - alpha_chars - digit_chars - space_chars
        
        # Different ratios for different content types
        estimated_tokens = (
            alpha_chars / 4.0 +       # Regular text: ~4 chars per token
            digit_chars / 2.5 +       # Numbers: ~2.5 chars per token
            space_chars / 1.0 +       # Spaces usually create token boundaries
            symbol_chars / 3.0        # Symbols/punctuation: ~3 chars per token
        )
        
        # Add overhead for special tokens, formatting, etc.
        estimated_tokens *= 1.1
        
        return max(1, int(estimated_tokens))
    
    def count_message_tokens(self, message: Dict[str, Any]) -> int:
        """Count tokens in a chat message.
        
        Args:
            message: Chat message with role, content, etc.
            
        Returns:
            int: Number of tokens including formatting overhead
        """
        tokens = 0
        
        # Count role
        if 'role' in message:
            tokens += self.count_tokens(message['role'])
        
        # Count content
        if 'content' in message:
            content = str(message['content'])
            tokens += self.count_tokens(content)
        
        # Count name if present
        if 'name' in message:
            tokens += self.count_tokens(message['name'])
        
        # Add formatting overhead (role, name, content markers)
        tokens += 10
        
        return tokens
    
    def count_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Count total tokens in a list of messages.
        
        Args:
            messages: List of chat messages
            
        Returns:
            int: Total token count
        """
        total = 0
        for message in messages:
            total += self.count_message_tokens(message)
        
        # Add conversation formatting overhead
        total += len(messages) * 3
        
        return total
    
    def optimize_messages_for_tokens(self, messages: List[Dict[str, Any]], 
                                   max_tokens: Optional[int] = None) -> List[Dict[str, Any]]:
        """Optimize message list to fit within token limits.
        
        Args:
            messages: List of chat messages
            max_tokens: Maximum tokens allowed (defaults to AVAILABLE_FOR_HISTORY)
            
        Returns:
            List[Dict[str, Any]]: Optimized message list
        """
        if max_tokens is None:
            max_tokens = self.AVAILABLE_FOR_HISTORY
        
        current_tokens = self.count_messages_tokens(messages)
        
        # Record usage for monitoring
        self.usage_monitor.record_usage(
            context="message_optimization",
            tokens_used=current_tokens,
            max_tokens=max_tokens or self.AVAILABLE_FOR_HISTORY,
            was_truncated=False
        )
        
        if current_tokens <= max_tokens:
            logger.debug(f"✅ Messages fit within limit: {current_tokens}/{max_tokens} tokens")
            return messages
        
        logger.info(f"⚠️ Messages exceed limit: {current_tokens}/{max_tokens} tokens - optimizing...")
        
        # Strategy 1: Remove oldest messages while preserving recent context
        optimized = self._truncate_oldest_messages(messages, max_tokens)
        
        # Strategy 2: Summarize long messages if still too long
        if self.count_messages_tokens(optimized) > max_tokens:
            optimized = self._summarize_long_messages(optimized, max_tokens)
        
        # Strategy 3: Final truncation if still too long
        if self.count_messages_tokens(optimized) > max_tokens:
            optimized = self._final_truncation(optimized, max_tokens)
        
        final_tokens = self.count_messages_tokens(optimized)
        logger.info(f"📉 Optimized from {current_tokens} to {final_tokens} tokens")
        
        # Record the truncation event
        self.usage_monitor.record_usage(
            context="message_optimization_result",
            tokens_used=final_tokens,
            max_tokens=max_tokens,
            was_truncated=True
        )
        
        return optimized
    
    def _truncate_oldest_messages(self, messages: List[Dict[str, Any]], 
                                max_tokens: int) -> List[Dict[str, Any]]:
        """Remove oldest messages while preserving system and recent messages."""
        if not messages:
            return messages
        
        # Always preserve system messages and the last few messages
        system_messages = [msg for msg in messages if msg.get('role') == 'system']
        recent_messages = messages[-5:]  # Keep last 5 messages
        
        # Calculate tokens for preserved messages
        preserved_tokens = (self.count_messages_tokens(system_messages) + 
                          self.count_messages_tokens(recent_messages))
        
        if preserved_tokens >= max_tokens:
            # If even preserved messages are too long, just keep system + last 2
            return system_messages + messages[-2:]
        
        # Add messages from newest to oldest until we hit the limit
        available_tokens = max_tokens - preserved_tokens
        result = system_messages[:]
        
        # Add messages from the middle, working backwards
        middle_messages = messages[len(system_messages):-5]
        for msg in reversed(middle_messages):
            msg_tokens = self.count_message_tokens(msg)
            if msg_tokens <= available_tokens:
                result.append(msg)
                available_tokens -= msg_tokens
            else:
                break
        
        # Sort middle messages back to chronological order
        middle_part = sorted([msg for msg in result if msg not in system_messages], 
                           key=lambda x: messages.index(x))
        
        # Add recent messages
        result = system_messages + middle_part + recent_messages
        
        return result
    
    def _summarize_long_messages(self, messages: List[Dict[str, Any]], 
                               max_tokens: int) -> List[Dict[str, Any]]:
        """Summarize individual messages that are too long."""
        result = []
        
        for message in messages:
            msg_tokens = self.count_message_tokens(message)
            
            # If message is longer than 2000 tokens, summarize it
            if msg_tokens > 2000:
                content = str(message.get('content', ''))
                summarized_content = self._summarize_content(content, max_length=1000)
                
                summarized_message = message.copy()
                summarized_message['content'] = f"[Summarized] {summarized_content}"
                result.append(summarized_message)
            else:
                result.append(message)
        
        return result
    
    def _summarize_content(self, content: str, max_length: int = 1000) -> str:
        """Summarize long content to fit within token limits."""
        if len(content) <= max_length:
            return content
        
        # Extract key information patterns
        sentences = re.split(r'[.!?]+', content)
        
        # Keep first and last sentences, plus any sentences with keywords
        keywords = ['result', 'error', 'success', 'found', 'data', 'analysis', 'summary']
        important_sentences = []
        
        # Always include first sentence
        if sentences:
            important_sentences.append(sentences[0])
        
        # Include sentences with keywords
        for sentence in sentences[1:-1]:
            if any(keyword in sentence.lower() for keyword in keywords):
                important_sentences.append(sentence.strip())
        
        # Always include last sentence
        if len(sentences) > 1:
            important_sentences.append(sentences[-1])
        
        summarized = '. '.join(important_sentences).strip()
        
        # If still too long, truncate
        if len(summarized) > max_length:
            summarized = summarized[:max_length-3] + "..."
        
        return summarized
    
    def _final_truncation(self, messages: List[Dict[str, Any]], 
                        max_tokens: int) -> List[Dict[str, Any]]:
        """Final aggressive truncation if other methods failed."""
        if not messages:
            return messages
        
        # Keep system messages and last user/assistant pair
        system_messages = [msg for msg in messages if msg.get('role') == 'system']
        last_messages = messages[-2:] if len(messages) >= 2 else messages[-1:]
        
        result = system_messages + last_messages
        
        # If still too long, truncate content of non-system messages
        current_tokens = self.count_messages_tokens(result)
        if current_tokens > max_tokens:
            for i, msg in enumerate(result):
                if msg.get('role') != 'system':
                    content = str(msg.get('content', ''))
                    if len(content) > 500:
                        result[i] = msg.copy()
                        result[i]['content'] = content[:500] + "...[truncated]"
        
        return result
    
    def optimize_rag_context(self, rag_results: List[Dict[str, Any]], 
                           max_tokens: int = 4000) -> str:
        """Optimize RAG context to fit within token limits.
        
        Args:
            rag_results: List of RAG search results
            max_tokens: Maximum tokens for RAG context
            
        Returns:
            str: Optimized RAG context
        """
        if not rag_results:
            return ""
        
        # Sort by relevance score if available
        sorted_results = sorted(rag_results, 
                              key=lambda x: x.get('score', 0), 
                              reverse=True)
        
        context_parts = []
        used_tokens = 0
        
        for result in sorted_results:
            document_id = result.get('documentId', 'Unknown')
            content = result.get('content', '')
            score = result.get('score', 0)
            
            # Create context entry
            entry = f"Document: {document_id} (Score: {score:.3f})\nContent: {content}\n"
            entry_tokens = self.count_tokens(entry)
            
            if used_tokens + entry_tokens <= max_tokens:
                context_parts.append(entry)
                used_tokens += entry_tokens
            else:
                # Try to fit a truncated version
                remaining_tokens = max_tokens - used_tokens - 50  # Buffer
                if remaining_tokens > 100:
                    max_content_chars = remaining_tokens * 3  # Rough estimate
                    truncated_content = content[:max_content_chars] + "...[truncated]"
                    truncated_entry = f"Document: {document_id} (Score: {score:.3f})\nContent: {truncated_content}\n"
                    context_parts.append(truncated_entry)
                break
        
        context = "\n".join(context_parts)
        actual_tokens = self.count_tokens(context)
        
        logger.info(f"📄 RAG context optimized: {actual_tokens}/{max_tokens} tokens from {len(rag_results)} results")
        
        return context
    
    def get_token_stats(self, messages: List[Dict[str, Any]], 
                       rag_context: str = "", 
                       system_prompt: str = "") -> Dict[str, int]:
        """Get detailed token usage statistics.
        
        Args:
            messages: Chat messages
            rag_context: RAG context content
            system_prompt: System prompt content
            
        Returns:
            Dict with token usage breakdown
        """
        stats = {
            'messages_tokens': self.count_messages_tokens(messages),
            'rag_tokens': self.count_tokens(rag_context),
            'system_tokens': self.count_tokens(system_prompt),
            'total_tokens': 0,
            'available_tokens': 0,
            'usage_percentage': 0
        }
        
        stats['total_tokens'] = (stats['messages_tokens'] + 
                               stats['rag_tokens'] + 
                               stats['system_tokens'])
        
        stats['available_tokens'] = self.SAFE_LIMIT - stats['total_tokens']
        stats['usage_percentage'] = int((stats['total_tokens'] / self.SAFE_LIMIT) * 100)
        
        return stats
    
    def check_rate_limit_risk(self, estimated_tokens: int, context: str = "api_call") -> Dict[str, Any]:
        """
        Check if a request might hit rate limits and provide recommendations.
        
        Args:
            estimated_tokens: Estimated tokens for the upcoming request
            context: Description of the operation
            
        Returns:
            Dict with risk assessment and recommendations
        """
        risk_assessment = {
            'risk_level': 'low',
            'recommended_action': 'proceed',
            'estimated_tokens': estimated_tokens,
            'warnings': [],
            'suggestions': []
        }
        
        # Check against token thresholds
        if estimated_tokens > 20000:
            risk_assessment['risk_level'] = 'high'
            risk_assessment['warnings'].append(f"Very large request ({estimated_tokens:,} tokens)")
            risk_assessment['suggestions'].append("Consider breaking into smaller requests")
        elif estimated_tokens > 10000:
            risk_assessment['risk_level'] = 'medium'
            risk_assessment['warnings'].append(f"Large request ({estimated_tokens:,} tokens)")
            risk_assessment['suggestions'].append("Monitor for rate limiting")
        
        # Check usage patterns
        usage_stats = self.usage_monitor.get_usage_stats()
        if not usage_stats.get('no_data'):
            if usage_stats.get('truncation_rate', 0) > 20:
                risk_assessment['warnings'].append(f"High truncation rate: {usage_stats['truncation_rate']:.1f}%")
                risk_assessment['suggestions'].append("Review token optimization strategies")
            
            if usage_stats.get('recent_average_percentage', 0) > 80:
                risk_assessment['risk_level'] = 'high'
                risk_assessment['warnings'].append("Recent high token usage pattern detected")
                risk_assessment['suggestions'].append("Consider implementing more aggressive truncation")
        
        # Provide recommendations based on risk level
        if risk_assessment['risk_level'] == 'high':
            risk_assessment['recommended_action'] = 'optimize_first'
            risk_assessment['suggestions'].append("Apply token optimization before proceeding")
        elif risk_assessment['risk_level'] == 'medium':
            risk_assessment['recommended_action'] = 'proceed_with_monitoring'
            risk_assessment['suggestions'].append("Monitor response for rate limiting")
        
        # Log warning for high-risk requests
        if risk_assessment['risk_level'] in ['high', 'medium'] and not self._warning_logged:
            logger.warning(f"⚠️ Token risk assessment for {context}: {risk_assessment['risk_level']} risk")
            for warning in risk_assessment['warnings']:
                logger.warning(f"   🚨 {warning}")
            for suggestion in risk_assessment['suggestions']:
                logger.info(f"   💡 {suggestion}")
            
            # Rate limit warning logs
            self._warning_logged = True
            # Reset warning flag after some time to allow periodic warnings
            import threading
            threading.Timer(300.0, lambda: setattr(self, '_warning_logged', False)).start()
        
        return risk_assessment
    
    def get_usage_insights(self) -> Dict[str, Any]:
        """Get comprehensive insights about token usage patterns."""
        insights = self.usage_monitor.get_usage_stats()
        
        if insights.get('no_data'):
            return insights
        
        # Add recommendations
        insights['recommendations'] = []
        
        if insights.get('truncation_rate', 0) > 10:
            insights['recommendations'].append("Consider increasing agent max_tokens or implementing more efficient prompts")
        
        if insights.get('recent_average_percentage', 0) > 70:
            insights['recommendations'].append("High average token usage - consider optimizing conversation management")
        
        if insights.get('critical_usage_requests', 0) > 5:
            insights['recommendations'].append("Frequent critical usage detected - implement proactive truncation")
        
        return insights


# Global token manager instance
token_manager = TokenManager()
