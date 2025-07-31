"""
Rate limiting, retry policies, and circuit breaker patterns for Azure OpenAI API calls.
Prevents rate limit errors and improves resilience.
"""

import asyncio
import time
import logging
from typing import Callable, Any, Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import wraps
import json

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry policies."""
    max_retries: int = 3
    initial_backoff: float = 1.0
    max_backoff: float = 30.0
    backoff_multiplier: float = 2.0
    retry_on_status_codes: List[int] = field(default_factory=lambda: [429, 500, 502, 503, 504])
    retry_on_exceptions: List[str] = field(default_factory=lambda: ["rate limit", "timeout", "service unavailable"])


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    max_concurrent_requests: int = 3
    min_request_interval: float = 0.1  # seconds
    requests_per_minute: int = 60
    tokens_per_minute: int = 150000
    enable_adaptive_throttling: bool = True


class CircuitBreakerState:
    """Circuit breaker states."""
    CLOSED = "CLOSED"
    OPEN = "OPEN" 
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 3  # For half-open state
    monitor_window: float = 300.0  # 5 minutes


class RateLimitTracker:
    """Tracks rate limit usage across time windows."""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.request_times: List[float] = []
        self.token_usage: List[tuple] = []  # (timestamp, tokens)
        self._lock = asyncio.Lock()
    
    async def can_make_request(self, estimated_tokens: int = 1000) -> tuple[bool, float]:
        """
        Check if a request can be made within rate limits.
        
        Returns:
            tuple[bool, float]: (can_proceed, wait_time_seconds)
        """
        async with self._lock:
            current_time = time.time()
            
            # Clean old entries
            self._cleanup_old_entries(current_time)
            
            # Check concurrent requests
            if len(self.request_times) >= self.config.max_concurrent_requests:
                oldest_request = min(self.request_times)
                wait_time = self.config.min_request_interval - (current_time - oldest_request)
                if wait_time > 0:
                    return False, wait_time
            
            # Check requests per minute
            recent_requests = [t for t in self.request_times if current_time - t < 60]
            if len(recent_requests) >= self.config.requests_per_minute:
                oldest_in_window = min(recent_requests)
                wait_time = 60 - (current_time - oldest_in_window)
                return False, wait_time
            
            # Check tokens per minute
            recent_tokens = sum(tokens for timestamp, tokens in self.token_usage 
                              if current_time - timestamp < 60)
            if recent_tokens + estimated_tokens > self.config.tokens_per_minute:
                oldest_token_time = min(timestamp for timestamp, _ in self.token_usage 
                                      if current_time - timestamp < 60)
                wait_time = 60 - (current_time - oldest_token_time)
                return False, wait_time
            
            return True, 0.0
    
    async def record_request(self, tokens_used: int = 1000):
        """Record a completed request."""
        async with self._lock:
            current_time = time.time()
            self.request_times.append(current_time)
            self.token_usage.append((current_time, tokens_used))
    
    def _cleanup_old_entries(self, current_time: float):
        """Remove entries older than tracking window."""
        # Keep only last hour of data
        cutoff = current_time - 3600
        self.request_times = [t for t in self.request_times if t > cutoff]
        self.token_usage = [(t, tokens) for t, tokens in self.token_usage if t > cutoff]


class CircuitBreaker:
    """Circuit breaker pattern implementation for resilience."""
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.last_request_time: Optional[float] = None
        self._lock = asyncio.Lock()
    
    async def can_execute(self) -> tuple[bool, str]:
        """
        Check if a request can be executed based on circuit breaker state.
        
        Returns:
            tuple[bool, str]: (can_execute, reason)
        """
        async with self._lock:
            current_time = time.time()
            
            if self.state == CircuitBreakerState.CLOSED:
                return True, "Circuit is closed"
            
            elif self.state == CircuitBreakerState.OPEN:
                if (self.last_failure_time and 
                    current_time - self.last_failure_time > self.config.recovery_timeout):
                    self.state = CircuitBreakerState.HALF_OPEN
                    self.success_count = 0
                    logger.info("🔄 Circuit breaker transitioning to HALF_OPEN")
                    return True, "Circuit transitioning to half-open"
                else:
                    remaining_time = self.config.recovery_timeout - (current_time - (self.last_failure_time or 0))
                    return False, f"Circuit is open, retry in {remaining_time:.1f}s"
            
            elif self.state == CircuitBreakerState.HALF_OPEN:
                return True, "Circuit is half-open (testing)"
            
            return False, "Unknown circuit state"
    
    async def record_success(self):
        """Record a successful request."""
        async with self._lock:
            if self.state == CircuitBreakerState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    self.state = CircuitBreakerState.CLOSED
                    self.failure_count = 0
                    logger.info("✅ Circuit breaker closed - service recovered")
            elif self.state == CircuitBreakerState.CLOSED:
                self.failure_count = max(0, self.failure_count - 1)
    
    async def record_failure(self):
        """Record a failed request."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state == CircuitBreakerState.HALF_OPEN:
                self.state = CircuitBreakerState.OPEN
                logger.warning("🔴 Circuit breaker opened from half-open due to failure")
            elif (self.state == CircuitBreakerState.CLOSED and 
                  self.failure_count >= self.config.failure_threshold):
                self.state = CircuitBreakerState.OPEN
                logger.warning(f"🔴 Circuit breaker opened due to {self.failure_count} failures")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            'state': self.state,
            'failure_count': self.failure_count,
            'success_count': self.success_count,
            'last_failure_time': self.last_failure_time,
            'recovery_timeout': self.config.recovery_timeout
        }


class ResilientAPIClient:
    """
    A resilient API client wrapper that implements:
    - Rate limiting with adaptive throttling
    - Exponential backoff retry policies  
    - Circuit breaker pattern
    - Request queuing and coordination
    """
    
    def __init__(self, 
                 retry_config: Optional[RetryConfig] = None,
                 rate_limit_config: Optional[RateLimitConfig] = None,
                 circuit_breaker_config: Optional[CircuitBreakerConfig] = None):
        
        self.retry_config = retry_config or RetryConfig()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.circuit_breaker_config = circuit_breaker_config or CircuitBreakerConfig()
        
        self.rate_tracker = RateLimitTracker(self.rate_limit_config)
        self.circuit_breaker = CircuitBreaker(self.circuit_breaker_config)
        
        # Request coordination
        self._request_semaphore = asyncio.Semaphore(rate_limit_config.max_concurrent_requests if rate_limit_config else 3)
        self._last_request_time = 0.0
        self._request_queue = asyncio.Queue()
        
        logger.info("🛡️ Resilient API client initialized with rate limiting and circuit breaker")
    
    async def execute_with_resilience(self, 
                                    api_call: Callable,
                                    *args,
                                    estimated_tokens: int = 1000,
                                    **kwargs) -> Any:
        """
        Execute an API call with full resilience features.
        
        Args:
            api_call: The async function to call
            *args: Arguments for the API call
            estimated_tokens: Estimated tokens for rate limiting
            **kwargs: Keyword arguments for the API call
            
        Returns:
            The result of the API call
            
        Raises:
            Exception: If all retries are exhausted or circuit breaker is open
        """
        # Check circuit breaker
        can_execute, reason = await self.circuit_breaker.can_execute()
        if not can_execute:
            raise Exception(f"Circuit breaker prevented execution: {reason}")
        
        # Rate limiting and request coordination
        await self._wait_for_rate_limit(estimated_tokens)
        
        # Execute with retry logic
        last_exception = None
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                async with self._request_semaphore:
                    # Ensure minimum interval between requests
                    await self._enforce_request_interval()
                    
                    # Execute the API call
                    result = await api_call(*args, **kwargs)
                    
                    # Record success
                    await self.rate_tracker.record_request(estimated_tokens)
                    await self.circuit_breaker.record_success()
                    
                    return result
                    
            except Exception as e:
                last_exception = e
                error_message = str(e).lower()
                
                # Check if this is a retryable error
                is_retryable = (
                    any(code_str in error_message for code_str in map(str, self.retry_config.retry_on_status_codes)) or
                    any(exc_str in error_message for exc_str in self.retry_config.retry_on_exceptions) or
                    "429" in error_message or
                    "rate limit" in error_message
                )
                
                if not is_retryable or attempt >= self.retry_config.max_retries:
                    await self.circuit_breaker.record_failure()
                    logger.error(f"❌ API call failed permanently: {str(e)}")
                    raise
                
                # Calculate backoff delay
                backoff_delay = min(
                    self.retry_config.initial_backoff * (self.retry_config.backoff_multiplier ** attempt),
                    self.retry_config.max_backoff
                )
                
                # Add jitter to prevent thundering herd
                jitter = backoff_delay * 0.1 * (0.5 + 0.5 * hash(str(time.time())) % 100 / 100)
                total_delay = backoff_delay + jitter
                
                logger.warning(f"⚠️ API call failed (attempt {attempt + 1}/{self.retry_config.max_retries + 1}): {str(e)}")
                logger.info(f"🔄 Retrying in {total_delay:.2f}s...")
                
                await asyncio.sleep(total_delay)
        
        # All retries exhausted
        await self.circuit_breaker.record_failure()
        raise last_exception
    
    async def _wait_for_rate_limit(self, estimated_tokens: int):
        """Wait if necessary to respect rate limits."""
        can_proceed, wait_time = await self.rate_tracker.can_make_request(estimated_tokens)
        
        if not can_proceed:
            logger.info(f"⏳ Rate limit reached, waiting {wait_time:.2f}s...")
            await asyncio.sleep(wait_time)
    
    async def _enforce_request_interval(self):
        """Ensure minimum interval between requests."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        
        if time_since_last < self.rate_limit_config.min_request_interval:
            wait_time = self.rate_limit_config.min_request_interval - time_since_last
            await asyncio.sleep(wait_time)
        
        self._last_request_time = time.time()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics about the resilient client."""
        return {
            'circuit_breaker': self.circuit_breaker.get_stats(),
            'rate_limiting': {
                'max_concurrent': self.rate_limit_config.max_concurrent_requests,
                'min_interval': self.rate_limit_config.min_request_interval,
                'requests_per_minute': self.rate_limit_config.requests_per_minute,
                'tokens_per_minute': self.rate_limit_config.tokens_per_minute
            },
            'retry_config': {
                'max_retries': self.retry_config.max_retries,
                'initial_backoff': self.retry_config.initial_backoff,
                'max_backoff': self.retry_config.max_backoff
            }
        }


def rate_limited(estimated_tokens: int = 1000, 
                retry_config: Optional[RetryConfig] = None,
                rate_limit_config: Optional[RateLimitConfig] = None,
                circuit_breaker_config: Optional[CircuitBreakerConfig] = None):
    """
    Decorator to add rate limiting and resilience to async functions.
    
    Args:
        estimated_tokens: Estimated tokens for this operation
        retry_config: Custom retry configuration
        rate_limit_config: Custom rate limiting configuration  
        circuit_breaker_config: Custom circuit breaker configuration
    """
    
    def decorator(func: Callable):
        # Create a shared resilient client for this function
        resilient_client = ResilientAPIClient(
            retry_config=retry_config,
            rate_limit_config=rate_limit_config,
            circuit_breaker_config=circuit_breaker_config
        )
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await resilient_client.execute_with_resilience(
                func, *args, estimated_tokens=estimated_tokens, **kwargs
            )
        
        # Attach stats method to decorated function
        wrapper.get_resilience_stats = resilient_client.get_stats
        
        return wrapper
    
    return decorator


# Global instances for shared use
default_resilient_client = ResilientAPIClient()

# Convenience functions
async def resilient_api_call(api_call: Callable, *args, estimated_tokens: int = 1000, **kwargs):
    """Execute an API call with default resilience settings."""
    return await default_resilient_client.execute_with_resilience(
        api_call, *args, estimated_tokens=estimated_tokens, **kwargs
    )


def get_resilience_stats() -> Dict[str, Any]:
    """Get stats from the default resilient client."""
    return default_resilient_client.get_stats()
