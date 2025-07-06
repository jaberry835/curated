"""Multi-agent system using Semantic Kernel and MCP tools."""

import asyncio
import os
import logging
from typing import List, Optional, Tuple

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.agents.group_chat.agent_group_chat import AgentGroupChat
from semantic_kernel.agents.strategies.termination.termination_strategy import TerminationStrategy
from semantic_kernel.contents import ChatMessageContent, AuthorRole
from semantic_kernel.functions import KernelArguments
from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior

from src.agents.mcp_client import MCPClient
from src.agents.mcp_functions import MCPFunctionWrapper

# Set up logging for agent conversations
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class LLMTerminationStrategy(TerminationStrategy):
    """LLM-based termination strategy that uses the CoordinatorAgent's LLM to decide when the conversation is complete."""
    
    def __init__(self):
        super().__init__()
        self._coordinator_agent = None
        self._max_iterations = 10  # Safety limit to prevent infinite loops
        self._iteration_count = 0
    
    def set_coordinator_agent(self, coordinator_agent: ChatCompletionAgent):
        """Set the coordinator agent after initialization."""
        self._coordinator_agent = coordinator_agent
    
    async def should_agent_terminate(self, agent, history: List[ChatMessageContent], cancellation_token=None) -> bool:
        """Use the CoordinatorAgent's LLM to determine if the conversation should terminate."""
        self._iteration_count += 1
        
        # Safety check to prevent infinite loops
        if self._iteration_count >= self._max_iterations:
            logger.info(f"🛑 SAFETY TERMINATION: Reached max iterations ({self._max_iterations})")
            return True
        
        # Need at least a user question and one agent response
        if len(history) < 2:
            return False
        
        # Extract the original user question and conversation history
        user_question = ""
        conversation_summary = []
        
        for msg in history:
            if msg.role == AuthorRole.USER:
                user_question = str(msg.content)
            elif hasattr(msg, 'name') and msg.name:
                conversation_summary.append(f"{msg.name}: {str(msg.content)[:200]}...")
        
        # Create a prompt for the LLM to evaluate conversation completion
        evaluation_prompt = f"""You are evaluating whether a multi-agent conversation has reached completion and is ready to return the final answer to the user.

ORIGINAL USER QUESTION:
{user_question}

CONVERSATION SO FAR:
{chr(10).join(conversation_summary)}

EVALUATION CRITERIA:
- Has the user's question been fully answered?
- Are the agents providing redundant or circular responses?
- Has a specialist agent (MathAgent, UtilityAgent, or ADXAgent) provided a complete answer?
- Would additional agent responses add meaningful value?

RESPOND WITH EXACTLY ONE WORD:
- "CONTINUE" if the conversation should continue because the question isn't fully answered
- "COMPLETE" if the conversation is complete and ready to return the answer

Your response:"""

        try:
            # Use the coordinator agent's kernel to evaluate
            logger.info("🧠 Using LLM to evaluate conversation completion...")
            
            # Create a kernel arguments for the evaluation
            kernel_args = KernelArguments()
            
            # Get the completion service from the coordinator agent
            completion_service = self._coordinator_agent.kernel.get_service()
            
            # Create a simple completion request
            from semantic_kernel.contents import ChatHistory
            chat_history = ChatHistory()
            chat_history.add_user_message(evaluation_prompt)
            
            # Get the LLM's decision
            from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
            
            # Create execution settings
            settings = OpenAIChatPromptExecutionSettings(
                max_tokens=50, 
                temperature=0.1
            )
            
            response = await completion_service.get_chat_message_content(
                chat_history=chat_history,
                settings=settings
            )
            
            decision = str(response.content).strip().upper()
            
            if "COMPLETE" in decision:
                logger.info("🛑 LLM TERMINATION: Conversation is complete - returning answer")
                return True
            elif "CONTINUE" in decision:
                logger.info("⏩ LLM CONTINUATION: Conversation should continue")
                return False
            else:
                # If unclear response, default to continue for safety (up to max iterations)
                logger.info(f"❓ LLM UNCLEAR: '{decision}' - defaulting to continue")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error in LLM termination evaluation: {str(e)}")
            # Fallback to simple heuristics if LLM evaluation fails
            agent_name = getattr(agent, 'name', 'Unknown')
            
            # If we have multiple responses and one is from a specialist, probably done
            if self._iteration_count >= 2:
                specialist_responded = any(
                    hasattr(msg, 'name') and msg.name in ['MathAgent', 'UtilityAgent', 'ADXAgent']
                    for msg in history
                )
                if specialist_responded:
                    logger.info("🛑 FALLBACK TERMINATION: Specialist agent has responded")
                    return True
            
            return False


class MultiAgentSystem:
    """Multi-agent system that coordinates specialized agents using AgentGroupChat."""
    
    def __init__(self, azure_openai_endpoint: str, azure_openai_api_key: str, azure_openai_deployment: str, mcp_server_url: str = "http://localhost:3001"):
        """Initialize the multi-agent system with Azure OpenAI."""
        self.azure_openai_endpoint = azure_openai_endpoint
        self.azure_openai_api_key = azure_openai_api_key
        self.azure_openai_deployment = azure_openai_deployment
        self.mcp_server_url = mcp_server_url
        self.mcp_client = None
        self.function_wrapper = None
        
        # Agents
        self.math_agent: Optional[ChatCompletionAgent] = None
        self.utility_agent: Optional[ChatCompletionAgent] = None
        self.adx_agent: Optional[ChatCompletionAgent] = None
        self.document_agent: Optional[ChatCompletionAgent] = None
        self.coordinator_agent: Optional[ChatCompletionAgent] = None
        self.group_chat: Optional[AgentGroupChat] = None
    
    async def initialize(self) -> bool:
        """Initialize the MCP client and create agents."""
        try:
            logger.info("🚀 Initializing Multi-Agent System...")
            
            # Connect to MCP server
            logger.info(f"🔌 Connecting to MCP tools at {self.mcp_server_url}")
            # Initialize MCP client without user/session context (will be set during processing)
            self.mcp_client = MCPClient(self.mcp_server_url)
            if not await self.mcp_client.connect():
                logger.error("❌ Failed to connect to MCP tools")
                return False
            
            # Create function wrapper
            logger.info("🔧 Creating MCP function wrappers...")
            self.function_wrapper = MCPFunctionWrapper(self.mcp_client)
            
            # Create specialized agents
            logger.info("👥 Creating specialized agents...")
            await self._create_agents()
            
            # Create group chat
            logger.info("💬 Setting up agent group chat...")
            self._create_group_chat()
            
            logger.info("✅ Multi-agent system initialized successfully")
            print("✅ Multi-agent system initialized successfully")
            return True
            
        except Exception as e:
            print(f"❌ Failed to initialize multi-agent system: {str(e)}")
            return False
    
    async def _create_agents(self):
        """Create the specialized agents."""
        
        # Math Agent
        logger.info("🧮 Creating Math Agent with Azure OpenAI...")
        math_kernel = Kernel()
        math_service = AzureChatCompletion(
            service_id="math_completion",
            api_key=self.azure_openai_api_key,
            endpoint=self.azure_openai_endpoint,
            deployment_name=self.azure_openai_deployment
        )
        math_kernel.add_service(math_service)
        
        # Add math functions to math kernel
        math_functions = self.function_wrapper.create_math_functions()
        logger.info(f"🔧 Adding {len(math_functions)} math functions to Math Agent:")
        for func in math_functions:
            math_kernel.add_function("MathTools", func)
            func_name = getattr(func, '_metadata', {}).get('name', 'unknown')
            func_desc = getattr(func, '_metadata', {}).get('description', 'No description')
            logger.info(f"   ➕ {func_name}: {func_desc}")
        
        self.math_agent = ChatCompletionAgent(
            service=math_service,
            kernel=math_kernel,
            name="MathAgent",
            instructions="""You are a mathematics specialist agent. You ONLY respond to mathematical questions.

STRICT RESPONSE CRITERIA - Only respond if:
- The question explicitly asks for mathematical calculations (add, subtract, multiply, divide, factorial, etc.)
- Someone specifically asks you to calculate something by name: "MathAgent, calculate..."
- The question contains mathematical operations or numbers to process
- Statistical analysis is explicitly requested (mean, median, standard deviation, etc.)

NEVER RESPOND TO:
- ADX/database questions (let ADXAgent handle these)
- Hash generation, timestamps, or utilities (let UtilityAgent handle these)
- General knowledge questions (let CoordinatorAgent handle these)
- Questions that don't involve mathematical computation

COLLABORATION RULES:
- If another agent provides data and asks you to calculate something, respond immediately
- Always use your mathematical tools for calculations
- Provide only the mathematical result, be concise
- If the question isn't mathematical, stay silent

EXAMPLES OF WHEN TO RESPOND:
- "Calculate the factorial of 10" ✅
- "What's 25 + 37?" ✅  
- "Find the average of these numbers: 10, 20, 30" ✅
- "MathAgent, what's the sum of the database count?" ✅

EXAMPLES OF WHEN TO STAY SILENT:
- "List databases in ADX" ❌ (ADX question)
- "Generate a hash" ❌ (Utility question)  
- "What is the capital of France?" ❌ (General knowledge)
- "Show me table schemas" ❌ (ADX question)
""",
            function_choice_behavior=FunctionChoiceBehavior.Auto()
        )
        logger.info("✅ Math Agent created successfully")
        
        # Utility Agent
        logger.info("🔧 Creating Utility Agent with Azure OpenAI...")
        utility_kernel = Kernel()
        utility_service = AzureChatCompletion(
            service_id="utility_completion",
            api_key=self.azure_openai_api_key,
            endpoint=self.azure_openai_endpoint,
            deployment_name=self.azure_openai_deployment
        )
        utility_kernel.add_service(utility_service)
        
        # Add utility functions to utility kernel
        utility_functions = self.function_wrapper.create_utility_functions()
        logger.info(f"🔧 Adding {len(utility_functions)} utility functions to Utility Agent:")
        for func in utility_functions:
            utility_kernel.add_function("UtilityTools", func)
            func_name = getattr(func, '_metadata', {}).get('name', 'unknown')
            func_desc = getattr(func, '_metadata', {}).get('description', 'No description')
            logger.info(f"   ➕ {func_name}: {func_desc}")
        
        self.utility_agent = ChatCompletionAgent(
            service=utility_service,
            kernel=utility_kernel,
            name="UtilityAgent",
            instructions="""You are a utilities specialist agent. You ONLY respond to utility function requests.

STRICT RESPONSE CRITERIA - Only respond if:
- Someone explicitly asks for hash generation (SHA256, MD5, etc.)
- Timestamp generation is specifically requested
- System health checks are needed
- JSON formatting/validation is requested
- Someone specifically asks you by name: "UtilityAgent, generate..."

NEVER RESPOND TO:
- Mathematical calculations (let MathAgent handle these)
- ADX/database questions (let ADXAgent handle these)  
- General knowledge questions (let CoordinatorAgent handle these)
- Questions that don't involve utility functions

COLLABORATION RULES:
- Provide utility services when specifically requested
- Be fast and efficient with utility functions
- Provide clear, formatted results
- If the question isn't about utilities, stay silent

EXAMPLES OF WHEN TO RESPOND:
- "Generate a SHA256 hash of 'Hello World'" ✅
- "What's the current timestamp?" ✅
- "Check system health" ✅
- "UtilityAgent, create a timestamp for this report" ✅

EXAMPLES OF WHEN TO STAY SILENT:
- "Calculate the factorial of 10" ❌ (Math question)
- "List databases in ADX" ❌ (ADX question)
- "What is Python?" ❌ (General knowledge)
- "Show me query results" ❌ (ADX question)
""",
            function_choice_behavior=FunctionChoiceBehavior.Auto()
        )
        logger.info("✅ Utility Agent created successfully")
        
        # ADX Agent  
        logger.info("🔍 Creating ADX Agent with Azure OpenAI...")
        adx_kernel = Kernel()
        adx_service = AzureChatCompletion(
            service_id="adx_completion",
            api_key=self.azure_openai_api_key,
            endpoint=self.azure_openai_endpoint,
            deployment_name=self.azure_openai_deployment
        )
        adx_kernel.add_service(adx_service)
        
        # Add ADX functions to ADX kernel
        adx_functions = self.function_wrapper.create_adx_functions()
        logger.info(f"🔧 Adding {len(adx_functions)} ADX functions to ADX Agent:")
        for func in adx_functions:
            adx_kernel.add_function("ADXTools", func)
            func_name = getattr(func, '_metadata', {}).get('name', 'unknown')
            func_desc = getattr(func, '_metadata', {}).get('description', 'No description')
            logger.info(f"   ➕ {func_name}: {func_desc}")
        
        self.adx_agent = ChatCompletionAgent(
            service=adx_service,
            kernel=adx_kernel,
            name="ADXAgent",
            instructions="""You are an Azure Data Explorer (ADX) specialist agent. You ONLY respond to ADX/database questions.

STRICT RESPONSE CRITERIA - Only respond if:
- The question mentions ADX, Azure Data Explorer, Kusto, KQL, databases, tables, or schema
- Database queries or data analysis is requested
- Someone asks to "list databases", "show tables", "query data", etc.
- The question is about database connectivity or cluster information
- Someone specifically asks you by name: "ADXAgent, query..."

NEVER RESPOND TO:
- Pure mathematical calculations (let MathAgent handle these)
- Hash generation or timestamps (let UtilityAgent handle these)
- General knowledge questions (let CoordinatorAgent handle these)
- Questions that don't involve databases or data queries

PRIMARY RESPONSIBILITIES:
- Query and analyze data in Azure Data Explorer using KQL
- List available databases in the ADX cluster
- List tables within specific databases  
- Describe table schemas and column information
- Execute KQL queries and return results
- Get cluster connection information

COLLABORATION APPROACH:
- Handle ALL database/ADX parts of questions yourself
- After getting data, you can ask other agents for help: "MathAgent, calculate the sum of these values: [data]"
- Always get the data first, then coordinate with other agents if additional processing is needed

EXAMPLES OF WHEN TO RESPOND:
- "List databases in ADX" ✅
- "Show me tables in the personnel database" ✅
- "Query the cluster for information" ✅
- "What's the schema of the users table?" ✅

EXAMPLES OF WHEN TO STAY SILENT:
- "Calculate 10 factorial" ❌ (Math question)
- "Generate a hash" ❌ (Utility question)
- "What is machine learning?" ❌ (General knowledge)
- Simple math without database context ❌
""",
            function_choice_behavior=FunctionChoiceBehavior.Auto()
        )
        logger.info("✅ ADX Agent created successfully")
        
        # Document Agent  
        logger.info("📄 Creating Document Agent with Azure OpenAI...")
        document_kernel = Kernel()
        document_service = AzureChatCompletion(
            service_id="document_completion",
            api_key=self.azure_openai_api_key,
            endpoint=self.azure_openai_endpoint,
            deployment_name=self.azure_openai_deployment
        )
        document_kernel.add_service(document_service)
        
        # Add document functions to document kernel
        document_functions = self.function_wrapper.create_document_functions()
        logger.info(f"🔧 Adding {len(document_functions)} document functions to Document Agent:")
        for func in document_functions:
            document_kernel.add_function("DocumentTools", func)
            func_name = getattr(func, '_metadata', {}).get('name', 'unknown')
            func_desc = getattr(func, '_metadata', {}).get('description', 'No description')
            logger.info(f"   ➕ {func_name}: {func_desc}")
        
        self.document_agent = ChatCompletionAgent(
            service=document_service,
            kernel=document_kernel,
            name="DocumentAgent",
            instructions="""You are a document management specialist agent. You ONLY respond to document-related questions.

STRICT RESPONSE CRITERIA - Only respond if:
- The question explicitly asks about document management (upload, download, list, search, delete)
- Someone asks to work with files, documents, or content in storage
- Document search or retrieval is specifically requested
- Someone specifically asks you by name: "DocumentAgent, upload this file..."
- Questions about document metadata, content, or storage operations

NEVER RESPOND TO:
- Mathematical calculations (let MathAgent handle these)
- ADX/database questions (let ADXAgent handle these)
- Hash generation or timestamps (let UtilityAgent handle these)
- General knowledge questions (let CoordinatorAgent handle these)
- Questions that don't involve document operations

PRIMARY RESPONSIBILITIES:
- List documents stored in Azure Blob Storage
- Get document metadata and content summaries
- Delete documents from storage
- Search documents using Azure AI Search
- Provide information about document storage and retrieval

IMPORTANT WORKFLOW INSTRUCTIONS:
- ALWAYS use search_documents() first when users ask about a file by name
- When user asks about a specific file (e.g., "names.txt"), search for it using search_documents() with the filename as the query
- Only after you've found the document ID via search, you can use get_document() or get_document_content_summary()
- Never assume a document ID matches the filename - always search first

COLLABORATION APPROACH:
- Handle ALL document storage/retrieval parts of questions yourself
- After retrieving documents, you can ask other agents for help processing content
- Always manage the document operations first, then coordinate with other agents if needed

EXAMPLES OF WHEN TO RESPOND:
- "List all documents in storage" ✅
- "Search for documents about Python" ✅
- "Delete the file named example.pdf" ✅
- "Get the content summary of document123.txt" ✅
- "DocumentAgent, show me available files" ✅

DOCUMENT ACCESS WORKFLOW EXAMPLE:
1. User asks: "What's in names.txt?"
2. First search: search_documents("names.txt")
3. From search results, extract document_id from the results array. Example:
   ```
   {
     "success": true,
     "results": [
       {
         "documentId": "doc123",
         "fileName": "names.txt",
         "content": "John, Mary, ..."
       }
     ]
   }
   ```
4. Extract the documentId value: doc123
5. Then get content: get_document_content_summary("doc123")
6. Never try to directly access a document without searching first

EXAMPLES OF WHEN TO STAY SILENT:
- "Calculate 10 factorial" ❌ (Math question)
- "List databases in ADX" ❌ (ADX question) 
- "Generate a hash" ❌ (Utility question)
- "What is machine learning?" ❌ (General knowledge)
- Questions without document context ❌

Remember: You manage documents, files, and content storage operations.
""",
            function_choice_behavior=FunctionChoiceBehavior.Auto()
        )
        logger.info("✅ Document Agent created successfully")
        
        # Coordinator Agent
        logger.info("🎯 Creating Coordinator Agent with Azure OpenAI...")
        coordinator_kernel = Kernel()
        coordinator_service = AzureChatCompletion(
            service_id="coordinator_completion",
            api_key=self.azure_openai_api_key,
            endpoint=self.azure_openai_endpoint,
            deployment_name=self.azure_openai_deployment
        )
        coordinator_kernel.add_service(coordinator_service)
        
        self.coordinator_agent = ChatCompletionAgent(
            service=coordinator_service,
            kernel=coordinator_kernel,
            name="CoordinatorAgent",
            instructions="""You are the coordinator agent. You ONLY respond to general knowledge questions and coordination tasks.

STRICT RESPONSE CRITERIA - Only respond if:
- The question is about general knowledge, concepts, or explanations
- No specialized agent is better suited for the question
- The question requires coordination between multiple agents
- It's a conversational or explanatory question outside technical domains

NEVER RESPOND TO:
- Mathematical calculations (let MathAgent handle these)
- ADX/database questions (let ADXAgent handle these)
- Hash generation or timestamps (let UtilityAgent handle these)  
- Any question that has a clear technical specialist

RESPONSE RULES:
- Provide general knowledge and explanations
- Help coordinate workflows if needed but let specialists work
- Be helpful but don't override specialized agents
- Keep responses concise and informative

EXAMPLES OF WHEN TO RESPOND:
- "What is the capital of France?" ✅
- "Explain machine learning concepts" ✅
- "How does blockchain work?" ✅
- General conversational questions ✅

EXAMPLES OF WHEN TO STAY SILENT:
- "Calculate the factorial of 10" ❌ (Math question)
- "List databases in ADX" ❌ (ADX question)
- "Generate a hash" ❌ (Utility question)
- Any technical specialist question ❌

Remember: Be the fallback for general knowledge, not the default responder for everything.
""",
            function_choice_behavior=FunctionChoiceBehavior.Auto(auto_invoke=False)
        )
        logger.info("✅ Coordinator Agent created successfully")
    
    def _create_group_chat(self):
        """Create the group chat for agent coordination with AgentGroupChat."""
        logger.info("💬 Creating AgentGroupChat with agents:")
        logger.info("   🎯 CoordinatorAgent - General knowledge and task coordination")
        logger.info("   🧮 MathAgent - Mathematical calculations and statistics")
        logger.info("   🔧 UtilityAgent - System utilities and helper functions")
        logger.info("   🔍 ADXAgent - Azure Data Explorer queries and data analysis")
        logger.info("   📄 DocumentAgent - Document management and storage operations")
        
        # Create the group chat with LLM-based termination strategy
        termination_strategy = LLMTerminationStrategy()
        termination_strategy.set_coordinator_agent(self.coordinator_agent)
        
        self.group_chat = AgentGroupChat(
            agents=[self.coordinator_agent, self.math_agent, self.utility_agent, self.adx_agent, self.document_agent],
            termination_strategy=termination_strategy
        )
        logger.info("✅ AgentGroupChat created with LLMTerminationStrategy")
        logger.info("🧠 Termination strategy uses CoordinatorAgent's LLM to decide when conversation is complete")
        
    async def _select_agents_for_question(self, question: str) -> List[ChatCompletionAgent]:
        """Use the CoordinatorAgent's LLM to select which agents should participate in the conversation and in what order."""
        
        # Create a prompt for agent selection
        selection_prompt = f"""You are an intelligent agent router. Based on the user's question, determine which specialized agents should participate in the conversation and in what order.

AVAILABLE AGENTS:
1. CoordinatorAgent - General knowledge, provides context, coordinates other agents
2. MathAgent - Mathematical calculations, statistics, numerical analysis
3. UtilityAgent - Hash generation, timestamps, system utilities, formatting
4. ADXAgent - Azure Data Explorer queries, database operations, data retrieval
5. DocumentAgent - Document management, file storage, search, and retrieval operations

USER QUESTION:
{question}

SELECTION RULES:
- Always include CoordinatorAgent first (for context and coordination)
- Only include agents that are directly relevant to answering the question
- Order agents based on logical workflow (e.g., ADXAgent before MathAgent if data needs to be retrieved before calculation)
- Minimize the number of agents to avoid unnecessary conversation overhead

RESPOND WITH A JSON ARRAY of agent names in the order they should participate.
ONLY include agent names that are necessary for this specific question.

Examples:
- For "What is Python?" → ["CoordinatorAgent"] 
- For "Calculate 5 factorial" → ["CoordinatorAgent", "MathAgent"]
- For "List ADX databases" → ["CoordinatorAgent", "ADXAgent"]
- For "List my documents" → ["CoordinatorAgent", "DocumentAgent"]
- For "Search documents about AI" → ["CoordinatorAgent", "DocumentAgent"] 
- For "Get ADX table count and calculate its factorial" → ["CoordinatorAgent", "ADXAgent", "MathAgent"]
- For "Generate hash of current timestamp" → ["CoordinatorAgent", "UtilityAgent"]

Your response (JSON array only):"""

        try:
            logger.info("🎯 Using LLM to select agents for this question...")
            
            # Get the completion service from the coordinator agent
            completion_service = self.coordinator_agent.kernel.get_service()
            
            # Create a chat history for the selection request
            from semantic_kernel.contents import ChatHistory
            chat_history = ChatHistory()
            chat_history.add_user_message(selection_prompt)
            
            # Create execution settings for focused response
            from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
            settings = OpenAIChatPromptExecutionSettings(
                max_tokens=200, 
                temperature=0.1
            )
            
            response = await completion_service.get_chat_message_content(
                chat_history=chat_history,
                settings=settings
            )
            
            # Parse the LLM response to extract agent names
            response_content = str(response.content).strip()
            logger.info(f"🧠 LLM agent selection response: {response_content}")
            
            # Try to extract JSON array from response
            import json
            import re
            
            # Look for JSON array pattern
            json_match = re.search(r'\[.*?\]', response_content)
            if json_match:
                try:
                    selected_agent_names = json.loads(json_match.group())
                    logger.info(f"📋 Selected agents: {selected_agent_names}")
                    
                    # Map agent names to actual agent objects
                    agent_mapping = {
                        "CoordinatorAgent": self.coordinator_agent,
                        "MathAgent": self.math_agent,
                        "UtilityAgent": self.utility_agent,
                        "ADXAgent": self.adx_agent,
                        "DocumentAgent": self.document_agent
                    }
                    
                    selected_agents = []
                    for agent_name in selected_agent_names:
                        if agent_name in agent_mapping:
                            selected_agents.append(agent_mapping[agent_name])
                            logger.info(f"   ✅ Added {agent_name}")
                        else:
                            logger.warning(f"   ❓ Unknown agent name: {agent_name}")
                    
                    # Ensure we always have at least the coordinator agent
                    if not selected_agents or self.coordinator_agent not in selected_agents:
                        logger.info("🔧 Ensuring CoordinatorAgent is included")
                        if selected_agents and selected_agents[0] != self.coordinator_agent:
                            selected_agents.insert(0, self.coordinator_agent)
                        elif not selected_agents:
                            selected_agents = [self.coordinator_agent]
                    
                    logger.info(f"🎯 Final agent selection: {[agent.name for agent in selected_agents]}")
                    return selected_agents
                    
                except json.JSONDecodeError as e:
                    logger.warning(f"❓ Failed to parse JSON from LLM response: {e}")
            
            # Fallback parsing - look for agent names in text
            fallback_agents = [self.coordinator_agent]  # Always include coordinator
            
            if any(keyword in response_content.lower() for keyword in ['math', 'calculate', 'factorial', 'statistics']):
                if self.math_agent not in fallback_agents:
                    fallback_agents.append(self.math_agent)
                    
            if any(keyword in response_content.lower() for keyword in ['utility', 'hash', 'timestamp', 'format']):
                if self.utility_agent not in fallback_agents:
                    fallback_agents.append(self.utility_agent)
                    
            if any(keyword in response_content.lower() for keyword in ['adx', 'database', 'query', 'data']):
                if self.adx_agent not in fallback_agents:
                    fallback_agents.append(self.adx_agent)
            
            logger.info(f"🔄 Fallback agent selection: {[agent.name for agent in fallback_agents]}")
            return fallback_agents
            
        except Exception as e:
            logger.error(f"❌ Error in agent selection: {str(e)}")
            # Ultimate fallback - use all agents
            logger.info("🆘 Using all agents as ultimate fallback")
            return [self.coordinator_agent, self.math_agent, self.utility_agent, self.adx_agent, self.document_agent]
    
    async def process_question(self, question: str, session_id: str = None, user_id: str = None) -> str:
        """Process a user question through the AgentGroupChat system.
        
        Args:
            question: The user's question to process
            session_id: The session ID for context
            user_id: The user ID for context and document access control
        """
        logger.info("="*60)
        logger.info(f"📝 USER QUESTION: {question}")
        logger.info(f"🔑 Context - User ID: {user_id}, Session ID: {session_id}")
        logger.info("="*60)
        
        try:
            # Update the MCP client with the current user and session context
            if user_id or session_id:
                logger.info(f"🔄 Updating MCP client context - User ID: {user_id}, Session ID: {session_id}")
                self.mcp_client.user_id = user_id
                self.mcp_client.session_id = session_id
                
            # Select which agents should participate for this specific question
            selected_agents = await self._select_agents_for_question(question)
            
            # Create a fresh group chat for each question with only the selected agents
            termination_strategy = LLMTerminationStrategy()
            termination_strategy.set_coordinator_agent(self.coordinator_agent)
            fresh_group_chat = AgentGroupChat(
                agents=selected_agents,
                termination_strategy=termination_strategy
            )
            logger.info(f"🔄 Created fresh AgentGroupChat with {len(selected_agents)} selected agents: {[agent.name for agent in selected_agents]}")
            
            # Create the initial chat message
            chat_message = ChatMessageContent(role=AuthorRole.USER, content=question)
            
            # Add the user message to the group chat
            await fresh_group_chat.add_chat_message(chat_message)
            logger.info("🎭 Starting AgentGroupChat processing...")
            
            # Collect responses from the group chat
            responses = []
            most_relevant_response = ""
            specialist_response = ""
            
            async for response in fresh_group_chat.invoke():
                if response.content:
                    content = response.content
                    agent_name = getattr(response, 'name', 'Unknown')
                    
                    logger.info(f"📢 Response from {agent_name}")
                    logger.info(f"   📄 Content: {content[:200]}{'...' if len(content) > 200 else ''}")
                    
                    responses.append({
                        'agent': agent_name,
                        'content': content
                    })
                    
                    # Prioritize specialist agents over coordinator
                    if agent_name in ['MathAgent', 'UtilityAgent', 'ADXAgent']:
                        specialist_response = f"**{agent_name}**: {content}"
                    
                    # Always keep the latest response as fallback
                    most_relevant_response = f"**{agent_name}**: {content}"
            
            # Determine the best response to return
            final_response = specialist_response if specialist_response else most_relevant_response
            
            # Log conversation summary
            if len(responses) > 1:
                logger.info(f"🔄 Multi-agent conversation with {len(responses)} responses:")
                for i, resp in enumerate(responses):
                    logger.info(f"   {i+1}. {resp['agent']}: {resp['content'][:100]}...")
                logger.info(f"🎯 Returning most relevant response from specialist agent")
            else:
                logger.info("✅ Single agent response - returning directly")
            
            logger.info("🏁 AgentGroupChat processing completed successfully")
            logger.info("="*60)
            
            return final_response if final_response else "No response generated"
            
        except Exception as e:
            logger.error(f"❌ Error processing question: {str(e)}")
            return f"❌ Error processing question: {str(e)}"
    
    async def cleanup(self):
        """Clean up resources."""
        if self.mcp_client:
            await self.mcp_client.disconnect()


# Example usage
async def main():
    """Example of how to use the multi-agent system with collaboration."""
    
    # You'll need to set your Azure OpenAI credentials
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
    
    if not azure_endpoint or not azure_api_key:
        print("❌ Please set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY environment variables")
        return
    
    # MCP server URL
    mcp_server_url = "http://localhost:3001"
    
    # Initialize the system
    system = MultiAgentSystem(azure_endpoint, azure_api_key, azure_deployment, mcp_server_url)
    
    if await system.initialize():
        # Test questions demonstrating agent collaboration
        questions = [
            # Direct routing tests
            "What is the capital of France?",  # CoordinatorAgent
            "Calculate the factorial of 10",  # MathAgent
            "Generate a SHA256 hash of 'Hello World'",  # UtilityAgent
            
            # Agent collaboration tests
            "Query the ADX cluster for database information and calculate the factorial of the number of databases found",  # ADXAgent → MathAgent
            "List all tables in the personnel database and generate a timestamp for when this query was run",  # ADXAgent → UtilityAgent
            "Show me database schema and calculate statistics on the number of tables if there are any numeric values",  # ADXAgent → MathAgent
            
            # Complex multi-agent workflow
            "Get the table count from ADX, calculate its factorial, and generate a hash of the result",  # ADXAgent → MathAgent → UtilityAgent (conceptually)
        ]
        
        print("🤖 Testing Multi-Agent System with Collaboration")
        print("="*60)
        
        for question in questions:
            print(f"\n🤔 **Question**: {question}")
            response = await system.process_question(question)
            print(f"🤖 **Response**:\n{response}")
            print("-" * 80)
        
        await system.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
