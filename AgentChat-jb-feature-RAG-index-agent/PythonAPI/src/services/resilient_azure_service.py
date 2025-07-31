"""
Resilient Azure OpenAI service wrapper with rate limiting and retry policies.
Prevents rate limit errors and improves agent system reliability.
"""

import logging
from typing import Optional, Dict, Any, List
import asyncio

from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents import ChatHistory, ChatMessageContent
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings

from ..utils.rate_limiting import ResilientAPIClient, RetryConfig, RateLimitConfig, CircuitBreakerConfig
from ..config.token_limits import token_config

logger = logging.getLogger(__name__)


class ResilientAzureChatCompletion(ChatCompletionClientBase):
    """
    A resilient wrapper around AzureChatCompletion that adds:
    - Rate limiting and request throttling
    - Exponential backoff retry policies
    - Circuit breaker pattern
    - Token-aware request estimation
    - Comprehensive error handling
    """
    
    def __init__(self, 
                 service_id: str,
                 api_key: str,
                 endpoint: str, 
                 deployment_name: str,
                 agent_name: str = "DefaultAgent",
                 **kwargs):
        """
        Initialize resilient Azure OpenAI completion service.
        
        Args:
            service_id: Service identifier
            api_key: Azure OpenAI API key
            endpoint: Azure OpenAI endpoint URL
            deployment_name: Deployment name
            agent_name: Name of the agent using this service (for monitoring)
            **kwargs: Additional AzureChatCompletion parameters
        """
        # Initialize the parent ChatCompletionClientBase
        super().__init__(service_id=service_id, ai_model_id=deployment_name)
        
        self._service_id = service_id
        self._agent_name = agent_name
        
        # Filter out execution settings from service initialization parameters
        azure_service_kwargs = {}
        execution_settings = {}
        
        # Separate service parameters from execution settings
        service_params = ['api_version', 'ad_token', 'default_headers', 'http_client']
        execution_params = ['max_tokens', 'temperature', 'top_p', 'frequency_penalty', 'presence_penalty']
        
        for key, value in kwargs.items():
            if key in execution_params:
                execution_settings[key] = value
            else:
                azure_service_kwargs[key] = value
        
        # Store execution settings for later use
        self._default_execution_settings = execution_settings
        
        # Create the underlying Azure chat completion service
        self._azure_service = AzureChatCompletion(
            service_id=service_id,
            api_key=api_key,
            endpoint=endpoint,
            deployment_name=deployment_name,
            **azure_service_kwargs
        )
        
        # Initialize resilient API client with configuration from token_config
        try:
            retry_config = token_config.get_retry_config()
            rate_limit_config = token_config.get_rate_limiting_config()
            circuit_breaker_config = token_config.get_circuit_breaker_config()
        except Exception as e:
            logger.warning(f"⚠️ Could not load resilience config from token_config: {e}")
            # Fallback to default configurations
            retry_config = RetryConfig()
            rate_limit_config = RateLimitConfig()
            circuit_breaker_config = CircuitBreakerConfig()
        
        self._resilient_client = ResilientAPIClient(
            retry_config=retry_config,
            rate_limit_config=rate_limit_config,
            circuit_breaker_config=circuit_breaker_config
        )
        
        logger.info(f"🛡️ Resilient Azure completion service initialized for {agent_name}")
        logger.info(f"   📊 Rate limits: {rate_limit_config.max_concurrent_requests} concurrent, "
                   f"{rate_limit_config.requests_per_minute} req/min, {rate_limit_config.tokens_per_minute} tokens/min")
        logger.info(f"   🔄 Retries: {retry_config.max_retries} max, {retry_config.initial_backoff}s initial backoff")
        logger.info(f"   ⚡ Circuit breaker: {circuit_breaker_config.failure_threshold} failure threshold")
    
    async def get_chat_message_contents(self,
                                      chat_history: ChatHistory,
                                      settings: OpenAIChatPromptExecutionSettings,
                                      **kwargs) -> List[ChatMessageContent]:
        """
        Get chat message contents with full resilience features.
        
        Args:
            chat_history: Chat conversation history
            settings: Execution settings for the completion
            **kwargs: Additional arguments
            
        Returns:
            List[ChatMessageContent]: The completion responses
        """
        # For compatibility, this just calls get_chat_message_content and returns as a list
        result = await self.get_chat_message_content(chat_history, settings, **kwargs)
        return [result] if result else []

    async def get_chat_message_content(self,
                                     chat_history: ChatHistory,
                                     settings: OpenAIChatPromptExecutionSettings,
                                     kernel=None,
                                     **kwargs) -> ChatMessageContent:
        """
        Get chat message content with full resilience features.
        
        Args:
            chat_history: Chat conversation history
            settings: Execution settings for the completion
            kernel: Semantic kernel instance (optional)
            **kwargs: Additional arguments
            
        Returns:
            ChatMessageContent: The completion response
            
        Raises:
            Exception: If all retries are exhausted or circuit breaker prevents execution
        """
        # Estimate tokens for rate limiting
        estimated_tokens = self._estimate_request_tokens(chat_history, settings)
        
        logger.debug(f"🚀 [{self._agent_name}] Making resilient chat completion request "
                    f"(estimated {estimated_tokens:,} tokens)")
        
        # Execute with full resilience
        try:
            if kernel:
                result = await self._resilient_client.execute_with_resilience(
                    self._azure_service.get_chat_message_content,
                    chat_history=chat_history,
                    settings=settings,
                    kernel=kernel,
                    estimated_tokens=estimated_tokens,
                    **kwargs
                )
            else:
                result = await self._resilient_client.execute_with_resilience(
                    self._azure_service.get_chat_message_content,
                    chat_history=chat_history,
                    settings=settings,
                    estimated_tokens=estimated_tokens,
                    **kwargs
                )
            
            logger.debug(f"✅ [{self._agent_name}] Resilient request completed successfully")
            return result
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Enhanced error categorization and logging
            if "429" in error_msg or "rate limit" in error_msg:
                logger.error(f"🚨 [{self._agent_name}] Rate limit error despite resilience measures: {str(e)}")
                logger.error(f"   💡 Suggestion: Consider reducing {self._agent_name} max_tokens or increasing request intervals")
            elif "timeout" in error_msg:
                logger.error(f"⏰ [{self._agent_name}] Timeout error: {str(e)}")
                logger.error(f"   💡 Suggestion: Consider reducing request complexity or increasing timeout settings")
            elif "quota" in error_msg or "limit" in error_msg:
                logger.error(f"📊 [{self._agent_name}] Quota/limit error: {str(e)}")
                logger.error(f"   💡 Suggestion: Check Azure OpenAI quotas and usage patterns")
            else:
                logger.error(f"❌ [{self._agent_name}] Unexpected error: {str(e)}")
            
            # Include resilience stats in error context
            stats = self._resilient_client.get_stats()
            logger.error(f"   📈 Resilience stats: Circuit={stats['circuit_breaker']['state']}, "
                        f"Failures={stats['circuit_breaker']['failure_count']}")
            
            raise
    
    def _estimate_request_tokens(self, 
                               chat_history: ChatHistory, 
                               settings: OpenAIChatPromptExecutionSettings) -> int:
        """
        Estimate tokens for a chat completion request.
        
        Args:
            chat_history: Chat conversation history
            settings: Execution settings
            
        Returns:
            int: Estimated token count
        """
        try:
            # Import token manager
            from ..services.token_management import token_manager
            
            # Convert chat history to messages for token counting
            messages = []
            for message in chat_history.messages:
                messages.append({
                    'role': str(message.role),
                    'content': str(message.content) if message.content else "",
                    'name': getattr(message, 'name', '')
                })
            
            # Count input tokens
            input_tokens = token_manager.count_messages_tokens(messages)
            
            # Add estimated output tokens from settings
            max_output_tokens = getattr(settings, 'max_tokens', 1000)
            
            # Add system prompt overhead estimation
            system_overhead = 200
            
            total_estimated = input_tokens + max_output_tokens + system_overhead
            
            logger.debug(f"📊 Token estimation: {input_tokens} input + {max_output_tokens} output + "
                        f"{system_overhead} overhead = {total_estimated} total")
            
            return total_estimated
            
        except Exception as e:
            logger.warning(f"⚠️ Token estimation failed: {e}, using fallback estimate")
            # Fallback estimation
            total_chars = sum(len(str(msg.content) or "") for msg in chat_history.messages)
            fallback_estimate = max(1000, total_chars // 3)  # ~3 chars per token
            return fallback_estimate
    
    def get_resilience_stats(self) -> Dict[str, Any]:
        """Get comprehensive resilience statistics."""
        stats = self._resilient_client.get_stats()
        stats['agent_name'] = self._agent_name
        stats['service_id'] = self._service_id
        return stats
    
    def get_service(self):
        """Get the underlying Azure service for compatibility."""
        return self._azure_service
    
    @property
    def ai_model_id(self) -> str:
        """Get the AI model ID."""
        return self._azure_service.ai_model_id if hasattr(self._azure_service, 'ai_model_id') else self.service_id
    
    @property
    def service_id(self) -> str:
        """Get the service ID."""
        return self._service_id
    
    @service_id.setter
    def service_id(self, value: str):
        """Set the service ID."""
        self._service_id = value
    
    @property
    def agent_name(self) -> str:
        """Get the agent name."""
        return self._agent_name
    
    @agent_name.setter
    def agent_name(self, value: str):
        """Set the agent name."""
        self._agent_name = value
    
    # Delegate other methods to the underlying service for compatibility
    def __getattr__(self, name):
        """Delegate unknown attributes to the underlying Azure service."""
        return getattr(self._azure_service, name)


class ResilientServiceFactory:
    """Factory for creating resilient Azure OpenAI services with shared rate limiting."""
    
    def __init__(self):
        """Initialize the factory with global rate limiting coordination."""
        self._global_resilient_client: Optional[ResilientAPIClient] = None
        self._service_instances: Dict[str, ResilientAzureChatCompletion] = {}
        
    def create_resilient_service(self,
                               service_id: str,
                               api_key: str,
                               endpoint: str,
                               deployment_name: str,
                               agent_name: str,
                               use_shared_rate_limiting: bool = True,
                               **kwargs) -> ResilientAzureChatCompletion:
        """
        Create a resilient Azure OpenAI service.
        
        Args:
            service_id: Service identifier
            api_key: Azure OpenAI API key  
            endpoint: Azure OpenAI endpoint URL
            deployment_name: Deployment name
            agent_name: Name of the agent using this service
            use_shared_rate_limiting: Whether to use shared rate limiting across all services
            **kwargs: Additional service parameters
            
        Returns:
            ResilientAzureChatCompletion: Configured resilient service
        """
        # Check if we already have this service
        if service_id in self._service_instances:
            logger.info(f"🔄 Reusing existing resilient service: {service_id}")
            return self._service_instances[service_id]
        
        # Create new resilient service
        if use_shared_rate_limiting:
            logger.info(f"🤝 Creating resilient service with shared rate limiting: {service_id}")
            # Use global shared rate limiting
            if not self._global_resilient_client:
                try:
                    retry_config = token_config.get_retry_config()
                    rate_limit_config = token_config.get_rate_limiting_config()
                    circuit_breaker_config = token_config.get_circuit_breaker_config()
                except Exception as e:
                    logger.warning(f"⚠️ Could not load global resilience config: {e}")
                    retry_config = RetryConfig()
                    rate_limit_config = RateLimitConfig()
                    circuit_breaker_config = CircuitBreakerConfig()
                
                self._global_resilient_client = ResilientAPIClient(
                    retry_config=retry_config,
                    rate_limit_config=rate_limit_config,
                    circuit_breaker_config=circuit_breaker_config
                )
            
            service = ResilientAzureChatCompletion(
                service_id=service_id,
                api_key=api_key,
                endpoint=endpoint,
                deployment_name=deployment_name,
                agent_name=agent_name,
                **kwargs
            )
            
            # Replace the service's resilient client with the shared one
            service._resilient_client = self._global_resilient_client
            
        else:
            logger.info(f"🏠 Creating resilient service with isolated rate limiting: {service_id}")
            service = ResilientAzureChatCompletion(
                service_id=service_id,
                api_key=api_key,
                endpoint=endpoint,
                deployment_name=deployment_name,
                agent_name=agent_name,
                **kwargs
            )
        
        # Cache the service
        self._service_instances[service_id] = service
        
        logger.info(f"✅ Resilient service created for {agent_name}: {service_id}")
        
        return service
    
    def get_global_stats(self) -> Dict[str, Any]:
        """Get statistics from all services."""
        stats = {
            'total_services': len(self._service_instances),
            'shared_rate_limiting': self._global_resilient_client is not None,
            'services': {}
        }
        
        if self._global_resilient_client:
            stats['global_resilience'] = self._global_resilient_client.get_stats()
        
        for service_id, service in self._service_instances.items():
            stats['services'][service_id] = service.get_resilience_stats()
        
        return stats
    
    def reset_circuit_breakers(self):
        """Reset all circuit breakers - useful for testing or recovery."""
        if self._global_resilient_client:
            self._global_resilient_client.circuit_breaker.state = "CLOSED"
            self._global_resilient_client.circuit_breaker.failure_count = 0
            logger.info("🔄 Global circuit breaker reset")
        
        for service in self._service_instances.values():
            if hasattr(service, '_resilient_client'):
                service._resilient_client.circuit_breaker.state = "CLOSED"
                service._resilient_client.circuit_breaker.failure_count = 0
        
        logger.info(f"🔄 Reset {len(self._service_instances)} service circuit breakers")


# Global factory instance
resilient_service_factory = ResilientServiceFactory()


def create_resilient_azure_service(service_id: str,
                                 api_key: str,
                                 endpoint: str,
                                 deployment_name: str,
                                 agent_name: str,
                                 **kwargs) -> ResilientAzureChatCompletion:
    """
    Convenience function to create a resilient Azure OpenAI service.
    
    Args:
        service_id: Service identifier
        api_key: Azure OpenAI API key
        endpoint: Azure OpenAI endpoint URL  
        deployment_name: Deployment name
        agent_name: Name of the agent using this service
        **kwargs: Additional service parameters
        
    Returns:
        ResilientAzureChatCompletion: Configured resilient service
    """
    return resilient_service_factory.create_resilient_service(
        service_id=service_id,
        api_key=api_key,
        endpoint=endpoint,
        deployment_name=deployment_name,
        agent_name=agent_name,
        **kwargs
    )


def get_all_resilience_stats() -> Dict[str, Any]:
    """Get comprehensive resilience statistics from all services."""
    return resilient_service_factory.get_global_stats()


def reset_all_circuit_breakers():
    """Reset all circuit breakers across all services."""
    resilient_service_factory.reset_circuit_breakers()
