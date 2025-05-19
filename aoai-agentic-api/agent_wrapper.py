# agent_wrapper.py
import asyncio
from semantic_kernel import Kernel
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.azure_chat_prompt_execution_settings import AzureChatPromptExecutionSettings
from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior

from decouple import config

api_key  = config('api_key')

class SemanticAgent:
    def __init__(self, agent_name: str, kernel: Kernel):
        self.agent_name = agent_name
        self.kernel = kernel
        self.chat_history = ChatHistory()
        self._configure_services()

    def _configure_services(self):
        # Register AI service; replace these parameters with your actual credentials.
        chat_completion = AzureChatCompletion(
            deployment_name="gpt-4o",
            api_key=api_key,
            base_url="https://jb-ai-test.openai.azure.com/",
        )
        self.kernel.add_service(chat_completion)
        # You can also add plugins specific to this agent
        # For example: self.kernel.add_plugin(LightsPlugin(), plugin_name="Lights")
    
    async def run_task(self, agent_input: str) -> str:
        # Example of building execution settings.
        execution_settings = AzureChatPromptExecutionSettings()
        execution_settings.function_choice_behavior = FunctionChoiceBehavior.Auto()
        
        # Add user input to the conversation history.
        self.chat_history.add_user_message(agent_input)
        
        # Use the AzureChatCompletion service to get a response.
        # Note: Adjust this call based on your actual Semantic Kernel API.
        chat_completion = self.kernel.get_service(AzureChatCompletion)
        result = await chat_completion.get_chat_message_content(
            chat_history=self.chat_history,
            settings=execution_settings,
            kernel=self.kernel,
        )
        # Store the response to continue the conversation
        self.chat_history.add_message(result)
        return str(result)
