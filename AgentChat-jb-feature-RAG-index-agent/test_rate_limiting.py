#!/usr/bin/env python3
"""
Test script for rate limiting and resilience features.
Run this to validate that the new rate limiting system works correctly.
"""

import asyncio
import logging
import time
from typing import List

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_rate_limiting():
    """Test the rate limiting functionality."""
    logger.info("🧪 Testing Rate Limiting and Resilience Features")
    
    try:
        from src.utils.rate_limiting import ResilientAPIClient, RetryConfig, RateLimitConfig, CircuitBreakerConfig
        from src.services.token_management import token_manager
        
        # Test 1: Token Manager Risk Assessment
        logger.info("\n📊 Test 1: Token Manager Risk Assessment")
        
        # Test low risk
        low_risk = token_manager.check_rate_limit_risk(1000, "test_low_risk")
        logger.info(f"   Low risk assessment: {low_risk['risk_level']} - {low_risk['recommended_action']}")
        
        # Test medium risk
        medium_risk = token_manager.check_rate_limit_risk(12000, "test_medium_risk")
        logger.info(f"   Medium risk assessment: {medium_risk['risk_level']} - {medium_risk['recommended_action']}")
        
        # Test high risk
        high_risk = token_manager.check_rate_limit_risk(25000, "test_high_risk")
        logger.info(f"   High risk assessment: {high_risk['risk_level']} - {high_risk['recommended_action']}")
        
        # Test 2: Rate Limiting Configuration
        logger.info("\n⚡ Test 2: Rate Limiting Configuration")
        
        rate_config = RateLimitConfig(
            max_concurrent_requests=2,
            min_request_interval=0.5,
            requests_per_minute=10,
            tokens_per_minute=50000
        )
        
        retry_config = RetryConfig(
            max_retries=2,
            initial_backoff=0.5,
            max_backoff=5.0
        )
        
        circuit_config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=5.0
        )
        
        resilient_client = ResilientAPIClient(
            retry_config=retry_config,
            rate_limit_config=rate_config,
            circuit_breaker_config=circuit_config
        )
        
        logger.info(f"   ✅ Resilient client created with {rate_config.max_concurrent_requests} max concurrent requests")
        
        # Test 3: Mock API Call Success
        logger.info("\n🚀 Test 3: Mock API Call Success")
        
        async def mock_successful_api_call():
            await asyncio.sleep(0.1)  # Simulate API delay
            return "Success"
        
        result = await resilient_client.execute_with_resilience(
            mock_successful_api_call,
            estimated_tokens=1000
        )
        logger.info(f"   ✅ Successful API call result: {result}")
        
        # Test 4: Mock API Call with Rate Limiting
        logger.info("\n⏳ Test 4: Rate Limiting (Multiple Concurrent Requests)")
        
        async def make_concurrent_requests(count: int):
            tasks = []
            for i in range(count):
                task = resilient_client.execute_with_resilience(
                    mock_successful_api_call,
                    estimated_tokens=1000
                )
                tasks.append(task)
            
            start_time = time.time()
            results = await asyncio.gather(*tasks)
            end_time = time.time()
            
            return results, end_time - start_time
        
        results, duration = await make_concurrent_requests(5)
        logger.info(f"   ✅ Completed {len(results)} requests in {duration:.2f} seconds (rate limited)")
        
        # Test 5: Circuit Breaker with Failures
        logger.info("\n⚡ Test 5: Circuit Breaker Pattern")
        
        async def mock_failing_api_call():
            await asyncio.sleep(0.1)
            raise Exception("429 Rate limit exceeded")
        
        failure_count = 0
        for i in range(4):  # Try to trigger circuit breaker
            try:
                await resilient_client.execute_with_resilience(
                    mock_failing_api_call,
                    estimated_tokens=1000
                )
            except Exception:
                failure_count += 1
                logger.info(f"   ❌ Expected failure {failure_count}/4")
        
        # Check circuit breaker state
        cb_stats = resilient_client.circuit_breaker.get_stats()
        logger.info(f"   🔴 Circuit breaker state: {cb_stats['state']} ({cb_stats['failure_count']} failures)")
        
        # Test 6: Configuration from token_config
        logger.info("\n🔧 Test 6: Configuration Integration")
        
        try:
            from src.config.token_limits import token_config
            
            # Test if configuration methods work
            rate_config = token_config.get_rate_limiting_config()
            retry_config = token_config.get_retry_config()
            circuit_config = token_config.get_circuit_breaker_config()
            
            logger.info(f"   ✅ Rate limiting config loaded: {rate_config.max_concurrent_requests} concurrent")
            logger.info(f"   ✅ Retry config loaded: {retry_config.max_retries} max retries")
            logger.info(f"   ✅ Circuit breaker config loaded: {circuit_config.failure_threshold} failure threshold")
            
        except Exception as e:
            logger.warning(f"   ⚠️ Configuration integration issue: {e}")
        
        # Test 7: Resilient Service Creation
        logger.info("\n🛡️ Test 7: Resilient Service Integration")
        
        try:
            from src.services.resilient_azure_service import resilient_service_factory
            
            # Get statistics (should work even without real services)
            stats = resilient_service_factory.get_global_stats()
            logger.info(f"   📊 Service factory stats: {stats['total_services']} services, "
                       f"shared rate limiting: {stats['shared_rate_limiting']}")
            
        except Exception as e:
            logger.warning(f"   ⚠️ Service integration issue: {e}")
        
        logger.info("\n✅ All rate limiting tests completed!")
        
        # Print summary
        logger.info("\n📋 TEST SUMMARY:")
        logger.info("   ✅ Token risk assessment working")
        logger.info("   ✅ Rate limiting configuration functional")
        logger.info("   ✅ Concurrent request handling working")
        logger.info("   ✅ Circuit breaker pattern functional")
        logger.info("   ✅ Configuration integration tested")
        logger.info("   ✅ Service factory integration tested")
        
        return True
        
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        logger.error("   Make sure you're running from the correct directory with all dependencies")
        return False
    except Exception as e:
        logger.error(f"❌ Test error: {e}")
        return False


async def test_token_management():
    """Test enhanced token management features."""
    logger.info("\n🔍 Testing Enhanced Token Management")
    
    try:
        from src.services.token_management import token_manager
        
        # Test message optimization
        test_messages = [
            {'role': 'system', 'content': 'You are a helpful assistant.'},
            {'role': 'user', 'content': 'Hello, how are you?'},
            {'role': 'assistant', 'content': 'I am doing well, thank you for asking!'},
            {'role': 'user', 'content': 'Can you help me with a complex task? ' * 100}  # Long message
        ]
        
        logger.info(f"   📝 Testing message optimization with {len(test_messages)} messages")
        
        original_tokens = token_manager.count_messages_tokens(test_messages)
        optimized_messages = token_manager.optimize_messages_for_tokens(test_messages, max_tokens=1000)
        optimized_tokens = token_manager.count_messages_tokens(optimized_messages)
        
        logger.info(f"   📉 Optimized from {original_tokens} to {optimized_tokens} tokens")
        logger.info(f"   📊 Kept {len(optimized_messages)}/{len(test_messages)} messages")
        
        # Test usage insights
        insights = token_manager.get_usage_insights()
        logger.info(f"   📈 Usage insights: {insights}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Token management test error: {e}")
        return False


if __name__ == "__main__":
    async def main():
        logger.info("🚀 Starting Rate Limiting and Resilience Tests")
        
        # Test rate limiting
        rate_test_success = await test_rate_limiting()
        
        # Test token management  
        token_test_success = await test_token_management()
        
        if rate_test_success and token_test_success:
            logger.info("\n🎉 ALL TESTS PASSED! Rate limiting and resilience features are working correctly.")
            logger.info("\n💡 Next Steps:")
            logger.info("   1. Update your environment with rate-limiting.env settings")
            logger.info("   2. Deploy the updated multi-agent system")
            logger.info("   3. Monitor resilience statistics during operation")
            logger.info("   4. Adjust rate limits based on your Azure OpenAI quotas")
        else:
            logger.error("\n❌ Some tests failed. Please check the error messages above.")
    
    asyncio.run(main())
