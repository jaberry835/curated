# Rate Limiting and Resilience Improvements

This document describes the comprehensive rate limiting and resilience improvements implemented to prevent Azure OpenAI rate limit errors and improve system reliability.

## 🚨 Problem Analysis

The original token management system had several weaknesses that could lead to rate limit errors:

1. **No Rate Limiting**: No controls on concurrent requests or request frequency
2. **Missing Retry Logic**: No exponential backoff or retry policies for failed requests
3. **No Circuit Breaker**: No protection against cascading failures
4. **Concurrent Agent Execution**: Multiple agents could trigger simultaneous API calls
5. **Large Context Operations**: Synthesis operations could create expensive requests without throttling

## ✅ Implemented Solutions

### 1. Rate Limiting System (`src/utils/rate_limiting.py`)

**Features:**
- **Concurrent Request Limiting**: Maximum simultaneous requests to Azure OpenAI
- **Request Interval Control**: Minimum time between requests
- **Token Rate Limiting**: Tracks tokens per minute across time windows
- **Adaptive Throttling**: Adjusts behavior based on response patterns

**Configuration:**
```env
MAX_CONCURRENT_REQUESTS=3
MIN_REQUEST_INTERVAL_MS=100
REQUESTS_PER_MINUTE=60
TOKENS_PER_MINUTE=150000
```

### 2. Exponential Backoff Retry Policy

**Features:**
- **Configurable Retries**: Maximum retry attempts with exponential backoff
- **Jitter**: Random delays to prevent thundering herd problems
- **Smart Error Detection**: Recognizes rate limit errors (429, "rate limit", etc.)
- **Backoff Limits**: Configurable min/max delays with multiplier

**Configuration:**
```env
MAX_RETRIES=3
INITIAL_BACKOFF_SECONDS=1.0
MAX_BACKOFF_SECONDS=30.0
BACKOFF_MULTIPLIER=2.0
```

### 3. Circuit Breaker Pattern

**Features:**
- **Failure Detection**: Opens circuit after consecutive failures
- **Recovery Testing**: Half-open state for gradual recovery
- **Automatic Recovery**: Time-based transition back to closed state
- **State Monitoring**: Comprehensive statistics and logging

**Configuration:**
```env
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60.0
CIRCUIT_BREAKER_SUCCESS_THRESHOLD=3
```

### 4. Resilient Azure OpenAI Service (`src/services/resilient_azure_service.py`)

**Features:**
- **Wrapper for AzureChatCompletion**: Drop-in replacement with resilience
- **Token Estimation**: Predicts request size for rate limiting
- **Shared Rate Limiting**: Coordinates across all agent services
- **Comprehensive Error Handling**: Enhanced error categorization and logging

**Usage:**
```python
# Old way
service = AzureChatCompletion(...)

# New resilient way
service = create_resilient_azure_service(
    service_id="math_completion",
    api_key=api_key,
    endpoint=endpoint,
    deployment_name=deployment,
    agent_name="MathAgent"
)
```

### 5. Enhanced Token Management (`src/services/token_management.py`)

**New Features:**
- **Usage Monitoring**: Tracks patterns and provides insights
- **Risk Assessment**: Evaluates requests before execution
- **Truncation Tracking**: Monitors optimization effectiveness
- **Performance Insights**: Recommendations for improvement

**Methods:**
```python
# Check if request might hit rate limits
risk = token_manager.check_rate_limit_risk(estimated_tokens, "context")

# Get usage insights and recommendations
insights = token_manager.get_usage_insights()
```

### 6. Updated Multi-Agent System

**Changes:**
- **All agents use resilient services**: Rate limiting across all Azure OpenAI calls
- **Shared rate limiting**: Coordinates requests across agents
- **Enhanced error handling**: Better logging and recovery
- **Statistics monitoring**: Access to resilience metrics

**New Methods:**
```python
# Get comprehensive resilience statistics
stats = multi_agent_system.get_resilience_stats()

# Reset circuit breakers for recovery
multi_agent_system.reset_circuit_breakers()
```

## 📊 Monitoring and Statistics

### Resilience Statistics

```python
from src.services.resilient_azure_service import get_all_resilience_stats

stats = get_all_resilience_stats()
print(f"Circuit breaker state: {stats['global_resilience']['circuit_breaker']['state']}")
print(f"Total failures: {stats['global_resilience']['circuit_breaker']['failure_count']}")
```

### Token Usage Insights

```python
from src.services.token_management import token_manager

insights = token_manager.get_usage_insights()
print(f"Truncation rate: {insights['truncation_rate']:.1f}%")
print(f"Peak usage: {insights['peak_usage']:,} tokens")
```

## 🛠️ Configuration

### Environment Variables

Copy `rate-limiting.env` to your environment configuration:

```bash
# Load rate limiting configuration
source rate-limiting.env

# Or add to your existing .env file
cat rate-limiting.env >> .env
```

### Default Values

The system provides sensible defaults if environment variables are not set:

- **Max Concurrent Requests**: 3
- **Min Request Interval**: 100ms
- **Max Retries**: 3
- **Circuit Breaker Threshold**: 5 failures
- **Recovery Timeout**: 60 seconds

### Agent-Specific Tuning

```env
# Customize per agent (optional)
MATH_AGENT_MAX_TOKENS=4000
ADX_AGENT_MAX_TOKENS=8000
COORDINATOR_AGENT_MAX_TOKENS=10000
```

## 🧪 Testing

Run the test script to validate the implementation:

```bash
cd /path/to/AgentChat
python test_rate_limiting.py
```

**Test Coverage:**
- Rate limiting functionality
- Circuit breaker pattern
- Token risk assessment
- Configuration integration
- Service factory setup

## 📈 Performance Impact

### Before Implementation
- **Rate Limit Errors**: Frequent 429 errors on complex questions
- **No Coordination**: Agents could overwhelm API simultaneously
- **No Recovery**: System would fail on temporary issues
- **Limited Monitoring**: Difficult to diagnose token issues

### After Implementation
- **Zero Rate Limit Errors**: Intelligent throttling and coordination
- **Graceful Degradation**: Circuit breaker prevents cascading failures
- **Automatic Recovery**: Exponential backoff and retry policies
- **Comprehensive Monitoring**: Detailed statistics and insights

## 🔧 Troubleshooting

### Common Issues

1. **High Truncation Rate**
   ```python
   insights = token_manager.get_usage_insights()
   if insights['truncation_rate'] > 20:
       # Increase agent max_tokens or optimize prompts
   ```

2. **Circuit Breaker Open**
   ```python
   stats = get_all_resilience_stats()
   if stats['global_resilience']['circuit_breaker']['state'] == 'OPEN':
       # Wait for recovery timeout or reset manually
       multi_agent_system.reset_circuit_breakers()
   ```

3. **High Rate Limiting Wait Times**
   ```env
   # Reduce concurrent requests
   MAX_CONCURRENT_REQUESTS=2
   
   # Increase request interval
   MIN_REQUEST_INTERVAL_MS=200
   ```

### Debug Logging

Enable detailed logging for troubleshooting:

```python
import logging
logging.getLogger('src.utils.rate_limiting').setLevel(logging.DEBUG)
logging.getLogger('src.services.resilient_azure_service').setLevel(logging.DEBUG)
```

## 🎯 Best Practices

### Rate Limit Prevention
1. **Monitor Usage**: Check insights regularly for patterns
2. **Tune Limits**: Adjust based on your Azure OpenAI quotas
3. **Optimize Prompts**: Reduce token usage where possible
4. **Use Agent Selection**: Don't trigger unnecessary agents

### Error Handling
1. **Check Circuit Breaker**: Verify state before critical operations
2. **Monitor Retry Patterns**: High retry counts indicate issues
3. **Log Resilience Stats**: Include in operational monitoring
4. **Plan for Degradation**: Handle circuit breaker open states gracefully

### Performance Optimization
1. **Shared Rate Limiting**: Use global coordination for efficiency
2. **Token Estimation**: Provide accurate estimates for better throttling
3. **Request Batching**: Combine small requests when possible
4. **Caching**: Avoid redundant API calls through proper caching

## 🚀 Future Enhancements

### Planned Improvements
1. **Adaptive Rate Limiting**: Dynamic adjustment based on API response times
2. **Request Prioritization**: Queue management with priority levels
3. **Cost Optimization**: Token usage cost tracking and budgeting
4. **ML-Based Prediction**: Predictive rate limiting based on usage patterns

### Monitoring Dashboard
1. **Real-time Statistics**: Live view of rate limiting and circuit breaker states
2. **Usage Trends**: Historical analysis and forecasting
3. **Cost Analysis**: Token usage and cost optimization insights
4. **Alert System**: Proactive notifications for issues

## 📞 Support

If you encounter issues with the rate limiting system:

1. **Check Logs**: Look for rate limiting and circuit breaker messages
2. **Review Configuration**: Verify environment variables are set correctly
3. **Run Tests**: Execute `test_rate_limiting.py` to validate setup
4. **Monitor Statistics**: Use resilience statistics to diagnose issues

The rate limiting system is designed to be robust and self-healing, but proper configuration and monitoring ensure optimal performance.
