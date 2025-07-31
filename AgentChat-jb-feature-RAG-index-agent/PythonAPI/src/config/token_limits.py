"""
Token limit configuration for multi-agent system.
Centralized configuration for all agent token limits and LLM settings.
"""

import os
from typing import Dict, Any

def get_env_int(key: str, default: int) -> int:
    """Get environment variable as integer with fallback."""
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default

def get_env_float(key: str, default: float) -> float:
    """Get environment variable as float with fallback."""
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default

def get_env_bool(key: str, default: bool) -> bool:
    """Get environment variable as boolean with fallback."""
    value = os.getenv(key, str(default)).lower()
    return value in ('true', '1', 'yes', 'on')

class TokenLimitsConfig:
    """Configuration class for agent token limits and LLM settings."""
    
    # 🔒 AGENT-SPECIFIC TOKEN LIMITS
    # These limits control how much each agent can generate in a single response
    AGENT_MAX_TOKENS = {
        'MathAgent': get_env_int('MATH_AGENT_MAX_TOKENS', 4000),
        'UtilityAgent': get_env_int('UTILITY_AGENT_MAX_TOKENS', 2000),
        'ADXAgent': get_env_int('ADX_AGENT_MAX_TOKENS', 8000),
        'DocumentAgent': get_env_int('DOCUMENT_AGENT_MAX_TOKENS', 6000),
        'FictionalCompaniesAgent': get_env_int('FICTIONAL_COMPANIES_AGENT_MAX_TOKENS', 5000),
        'CoordinatorAgent': get_env_int('COORDINATOR_AGENT_MAX_TOKENS', 10000),
    }
    
    # 🌡️ AGENT-SPECIFIC TEMPERATURE SETTINGS
    # Lower = more focused/deterministic, Higher = more creative
    AGENT_TEMPERATURES = {
        'MathAgent': get_env_float('MATH_AGENT_TEMPERATURE', 0.1),
        'UtilityAgent': get_env_float('UTILITY_AGENT_TEMPERATURE', 0.0),
        'ADXAgent': get_env_float('ADX_AGENT_TEMPERATURE', 0.1),
        'DocumentAgent': get_env_float('DOCUMENT_AGENT_TEMPERATURE', 0.2),
        'FictionalCompaniesAgent': get_env_float('FICTIONAL_COMPANIES_AGENT_TEMPERATURE', 0.1),
        'CoordinatorAgent': get_env_float('COORDINATOR_AGENT_TEMPERATURE', 0.3),
    }
    
    # 🚦 GLOBAL TOKEN MANAGEMENT
    GLOBAL_LIMITS = {
        'MAX_CONTEXT_TOKENS': get_env_int('MAX_CONTEXT_TOKENS', 120000),
        'SAFE_RESPONSE_BUFFER': get_env_int('SAFE_RESPONSE_BUFFER', 8000),
        'SYNTHESIS_MAX_TOKENS': get_env_int('SYNTHESIS_MAX_TOKENS', 12000),
        'EMERGENCY_TRUNCATION_LIMIT': get_env_int('EMERGENCY_TRUNCATION_LIMIT', 50000),
    }
    
    # 🛡️ OVERFLOW PROTECTION SETTINGS
    PROTECTION_SETTINGS = {
        'ENABLE_AUTOMATIC_TRUNCATION': get_env_bool('ENABLE_AUTOMATIC_TRUNCATION', True),
        'TRUNCATION_STRATEGY': os.getenv('TRUNCATION_STRATEGY', 'preserve_recent'),
        'EMERGENCY_FALLBACK': get_env_bool('EMERGENCY_FALLBACK', True),
        'WARNING_THRESHOLD': get_env_float('WARNING_THRESHOLD', 0.85),
        'CRITICAL_THRESHOLD': get_env_float('CRITICAL_THRESHOLD', 0.95),
    }
    
    # 📊 MONITORING AND ALERTING
    MONITORING = {
        'LOG_TOKEN_USAGE': get_env_bool('LOG_TOKEN_USAGE', True),
        'ALERT_ON_HIGH_USAGE': get_env_bool('ALERT_ON_HIGH_USAGE', True),
        'TRACK_AGENT_EFFICIENCY': get_env_bool('TRACK_AGENT_EFFICIENCY', True),
        'ENABLE_USAGE_ANALYTICS': get_env_bool('ENABLE_USAGE_ANALYTICS', True),
    }
    
    # 🚦 RATE LIMITING CONFIGURATION
    RATE_LIMITING = {
        'MAX_CONCURRENT_REQUESTS': get_env_int('MAX_CONCURRENT_REQUESTS', 3),
        'MIN_REQUEST_INTERVAL_MS': get_env_int('MIN_REQUEST_INTERVAL_MS', 100),
        'REQUESTS_PER_MINUTE': get_env_int('REQUESTS_PER_MINUTE', 60),
        'TOKENS_PER_MINUTE': get_env_int('TOKENS_PER_MINUTE', 150000),
        'ENABLE_ADAPTIVE_THROTTLING': get_env_bool('ENABLE_ADAPTIVE_THROTTLING', True),
        'ENABLE_CIRCUIT_BREAKER': get_env_bool('ENABLE_CIRCUIT_BREAKER', True),
    }
    
    # 🔄 RETRY CONFIGURATION  
    RETRY_CONFIG = {
        'MAX_RETRIES': get_env_int('MAX_RETRIES', 3),
        'INITIAL_BACKOFF_SECONDS': get_env_float('INITIAL_BACKOFF_SECONDS', 1.0),
        'MAX_BACKOFF_SECONDS': get_env_float('MAX_BACKOFF_SECONDS', 30.0),
        'BACKOFF_MULTIPLIER': get_env_float('BACKOFF_MULTIPLIER', 2.0),
        'ENABLE_JITTER': get_env_bool('ENABLE_JITTER', True),
    }
    
    # ⚡ CIRCUIT BREAKER CONFIGURATION
    CIRCUIT_BREAKER = {
        'FAILURE_THRESHOLD': get_env_int('CIRCUIT_BREAKER_FAILURE_THRESHOLD', 5),
        'RECOVERY_TIMEOUT_SECONDS': get_env_float('CIRCUIT_BREAKER_RECOVERY_TIMEOUT', 60.0),
        'SUCCESS_THRESHOLD': get_env_int('CIRCUIT_BREAKER_SUCCESS_THRESHOLD', 3),
        'MONITOR_WINDOW_SECONDS': get_env_float('CIRCUIT_BREAKER_MONITOR_WINDOW', 300.0),
    }
    
    @classmethod
    def get_agent_config(cls, agent_name: str) -> Dict[str, Any]:
        """Get AzureChatCompletion service configuration for a specific agent.
        
        Args:
            agent_name: Name of the agent (e.g., 'MathAgent')
            
        Returns:
            Dict containing valid AzureChatCompletion constructor parameters
        """
        # Return minimal valid AzureChatCompletion constructor parameters
        # Most settings will be handled through execution settings in individual calls
        return {}
    
    @classmethod
    def get_agent_execution_settings(cls, agent_name: str) -> Dict[str, Any]:
        """Get execution settings for chat completion calls.
        
        Args:
            agent_name: Name of the agent (e.g., 'MathAgent')
            
        Returns:
            Dict containing execution settings for chat completion calls
        """
        return {
            'max_tokens': cls.AGENT_MAX_TOKENS.get(agent_name, 4000),
            'temperature': cls.AGENT_TEMPERATURES.get(agent_name, 0.2),
            'top_p': get_env_float('TOP_P', 0.95),
            'frequency_penalty': get_env_float('FREQUENCY_PENALTY', 0.0),
            'presence_penalty': get_env_float('PRESENCE_PENALTY', 0.0),
        }
    
    @classmethod
    def get_synthesis_config(cls) -> Dict[str, Any]:
        """Get execution settings for synthesis operations.
        
        Returns:
            Dict with synthesis-specific execution settings
        """
        return {
            'max_tokens': cls.GLOBAL_LIMITS['SYNTHESIS_MAX_TOKENS'],
            'temperature': 0.4,  # Slightly more creative for synthesis
            'top_p': get_env_float('TOP_P', 0.95),
            'frequency_penalty': get_env_float('SYNTHESIS_FREQUENCY_PENALTY', 0.1),
            'presence_penalty': get_env_float('SYNTHESIS_PRESENCE_PENALTY', 0.1),
        }
    
    @classmethod
    def should_truncate(cls, current_tokens: int) -> bool:
        """Check if content should be truncated based on current usage.
        
        Args:
            current_tokens: Current token count
            
        Returns:
            bool: True if truncation is recommended
        """
        threshold = cls.GLOBAL_LIMITS['MAX_CONTEXT_TOKENS'] * cls.PROTECTION_SETTINGS['WARNING_THRESHOLD']
        return current_tokens > threshold
    
    @classmethod
    def is_critical_usage(cls, current_tokens: int) -> bool:
        """Check if token usage is at critical levels.
        
        Args:
            current_tokens: Current token count
            
        Returns:
            bool: True if usage is critical
        """
        threshold = cls.GLOBAL_LIMITS['MAX_CONTEXT_TOKENS'] * cls.PROTECTION_SETTINGS['CRITICAL_THRESHOLD']
        return current_tokens > threshold
    
    @classmethod
    def get_available_tokens(cls, current_tokens: int) -> int:
        """Calculate available tokens for new content.
        
        Args:
            current_tokens: Current token usage
            
        Returns:
            int: Available tokens remaining
        """
        max_available = cls.GLOBAL_LIMITS['MAX_CONTEXT_TOKENS'] - cls.GLOBAL_LIMITS['SAFE_RESPONSE_BUFFER']
        return max(0, max_available - current_tokens)
    
    @classmethod
    def get_rate_limiting_config(cls) -> Dict[str, Any]:
        """Get rate limiting configuration for the resilient API client.
        
        Returns:
            Dict containing rate limiting settings
        """
        from ..utils.rate_limiting import RateLimitConfig
        
        return RateLimitConfig(
            max_concurrent_requests=cls.RATE_LIMITING['MAX_CONCURRENT_REQUESTS'],
            min_request_interval=cls.RATE_LIMITING['MIN_REQUEST_INTERVAL_MS'] / 1000.0,
            requests_per_minute=cls.RATE_LIMITING['REQUESTS_PER_MINUTE'],
            tokens_per_minute=cls.RATE_LIMITING['TOKENS_PER_MINUTE'],
            enable_adaptive_throttling=cls.RATE_LIMITING['ENABLE_ADAPTIVE_THROTTLING']
        )
    
    @classmethod
    def get_retry_config(cls) -> Dict[str, Any]:
        """Get retry configuration for the resilient API client.
        
        Returns:
            Dict containing retry settings
        """
        from ..utils.rate_limiting import RetryConfig
        
        return RetryConfig(
            max_retries=cls.RETRY_CONFIG['MAX_RETRIES'],
            initial_backoff=cls.RETRY_CONFIG['INITIAL_BACKOFF_SECONDS'],
            max_backoff=cls.RETRY_CONFIG['MAX_BACKOFF_SECONDS'],
            backoff_multiplier=cls.RETRY_CONFIG['BACKOFF_MULTIPLIER']
        )
    
    @classmethod
    def get_circuit_breaker_config(cls) -> Dict[str, Any]:
        """Get circuit breaker configuration for the resilient API client.
        
        Returns:
            Dict containing circuit breaker settings
        """
        from ..utils.rate_limiting import CircuitBreakerConfig
        
        return CircuitBreakerConfig(
            failure_threshold=cls.CIRCUIT_BREAKER['FAILURE_THRESHOLD'],
            recovery_timeout=cls.CIRCUIT_BREAKER['RECOVERY_TIMEOUT_SECONDS'],
            success_threshold=cls.CIRCUIT_BREAKER['SUCCESS_THRESHOLD'],
            monitor_window=cls.CIRCUIT_BREAKER['MONITOR_WINDOW_SECONDS']
        )
    
    @classmethod
    def log_token_stats(cls, context: str, current_tokens: int, max_tokens: int = None) -> None:
        """Log token usage statistics if monitoring is enabled.
        
        Args:
            context: Description of what is being measured
            current_tokens: Current token count
            max_tokens: Maximum tokens for this context (optional)
        """
        if not cls.MONITORING['LOG_TOKEN_USAGE']:
            return
        
        if max_tokens:
            percentage = (current_tokens / max_tokens) * 100
            print(f"🔍 TOKEN STATS [{context}]: {current_tokens:,}/{max_tokens:,} tokens ({percentage:.1f}%)")
        else:
            print(f"🔍 TOKEN STATS [{context}]: {current_tokens:,} tokens")
        
        if cls.MONITORING['ALERT_ON_HIGH_USAGE']:
            if cls.is_critical_usage(current_tokens):
                print(f"🚨 CRITICAL TOKEN USAGE WARNING: {context}")
            elif cls.should_truncate(current_tokens):
                print(f"⚠️ HIGH TOKEN USAGE WARNING: {context}")

# Global configuration instance
token_config = TokenLimitsConfig()
