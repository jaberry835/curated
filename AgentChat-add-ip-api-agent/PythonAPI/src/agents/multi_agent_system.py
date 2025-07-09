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
        specialist_responses = []
        coordinator_responses = []
        
        for msg in history:
            if msg.role == AuthorRole.USER:
                user_question = str(msg.content)
            elif hasattr(msg, 'name') and msg.name:
                agent_name = msg.name
                content = str(msg.content)[:200]
                conversation_summary.append(f"{agent_name}: {content}...")
                
                # Track specialist vs coordinator responses
                if agent_name in ['MathAgent', 'UtilityAgent', 'ADXAgent', 'DocumentAgent', 'FictionalCompaniesAgent']:
                    specialist_responses.append(agent_name)
                elif agent_name == 'CoordinatorAgent':
                    coordinator_responses.append(content)
        
        # Quick heuristic checks before using LLM
        # If we have duplicate responses from the same agent, terminate
        if len(specialist_responses) > len(set(specialist_responses)):
            logger.info("🛑 HEURISTIC TERMINATION: Duplicate specialist responses detected")
            return True
        
        # Check if a specialist agent has provided a substantial response
        specialist_provided_answer = any(
            hasattr(msg, 'name') and msg.name in ['MathAgent', 'UtilityAgent', 'ADXAgent', 'DocumentAgent', 'FictionalCompaniesAgent'] 
            and len(str(msg.content)) > 50  # Substantial response
            for msg in history
        )
        
        # Check if the coordinator has provided substantial orchestration or synthesis
        coordinator_provided_substantial_response = any(
            hasattr(msg, 'name') and msg.name == 'CoordinatorAgent' 
            and len(str(msg.content)) > 50
            and not any(keyword in str(msg.content).lower() for keyword in 
                       ["specialist", "defer", "better suited", "more appropriate", "equipped to handle", "route this", "direct this"])
            for msg in history
        )
        
        # Check if the last coordinator response is a deferral
        coordinator_deferral_keywords = [
            "specialist", "defer", "better suited", "more appropriate", "equipped to handle", 
            "route this", "direct this", "unable to assist", "i'll need to involve", 
            "let me get", "let me involve", "i'll involve", "adxagent,", "mathagent,", 
            "documentagent,", "utilityagent,", "fictionalcompaniesagent,", "please query",
            "could you please", "can you please", "need you to", "will need", "require",
            "must involve", "should involve", "asking", "requesting"
        ]
        last_coord_response = coordinator_responses[-1] if coordinator_responses else ""
        is_coordinator_deferral = any(keyword in last_coord_response.lower() for keyword in coordinator_deferral_keywords)
        
        # NEVER terminate if the last response was a coordinator deferral
        if is_coordinator_deferral and not specialist_provided_answer:
            logger.info("⏩ CONTINUE: Coordinator deferred, waiting for specialist agents")
            return False
        
        # NEW LOGIC: Check if we need multiple specialists to respond
        # Determine which specialist types are relevant for this question
        question_text = user_question.lower()
        
        # Check what types of agents should participate based on the question
        needs_document_agent = any(keyword in question_text for keyword in ["document", "file", "upload", "search documents", "content", "text", "summary"])
        needs_adx_agent = any(keyword in question_text for keyword in ["database", "query", "adx", "table", "sql", "cluster", "data"])
        needs_fictional_companies = any(keyword in question_text for keyword in ["company", "ip address", "device", "corporation", "firm", "business"])
        needs_math_agent = any(keyword in question_text for keyword in ["calculate", "math", "factorial", "statistics", "compute", "sum", "average"])
        needs_utility_agent = any(keyword in question_text for keyword in ["hash", "timestamp", "format", "utility", "generate"])
        
        # Count how many different specialist types should participate
        expected_specialist_types = []
        if needs_document_agent:
            expected_specialist_types.append('DocumentAgent')
        if needs_adx_agent:
            expected_specialist_types.append('ADXAgent')
        if needs_fictional_companies:
            expected_specialist_types.append('FictionalCompaniesAgent')
        if needs_math_agent:
            expected_specialist_types.append('MathAgent')
        if needs_utility_agent:
            expected_specialist_types.append('UtilityAgent')
        
        # Check which specialist types have actually responded
        specialist_types_responded = list(set(specialist_responses))
        
        logger.info(f"🎯 Expected specialists: {expected_specialist_types}")
        logger.info(f"🎯 Responded specialists: {specialist_types_responded}")
        
        # If multiple specialist types are expected, wait for more responses
        if len(expected_specialist_types) > 1:
            # Check if we've heard from all expected specialist types
            expected_set = set(expected_specialist_types)
            responded_set = set(specialist_types_responded)
            
            if not expected_set.issubset(responded_set):
                missing_specialists = expected_set - responded_set
                logger.info(f"⏩ CONTINUE: Waiting for specialists: {list(missing_specialists)}")
                return False
            else:
                # All specialists have responded, but check if coordinator has had a chance to synthesize
                coordinator_synthesized = any(
                    hasattr(msg, 'name') and msg.name == 'CoordinatorAgent'
                    and len(str(msg.content)) > 100  # Substantial synthesis response
                    and "synthesis" in str(msg.content).lower() or "combining" in str(msg.content).lower()
                    for msg in history[-3:]  # Check recent messages
                )
                
                if len(specialist_types_responded) > 1 and not coordinator_synthesized and not is_coordinator_deferral:
                    logger.info("⏩ CONTINUE: Multiple specialists responded, giving coordinator chance to synthesize")
                    return False
                
                logger.info("🛑 MULTI-SPECIALIST TERMINATION: All expected specialists have responded")
                return True
        
        # Single specialist expected - terminate if they provided a substantial answer
        if len(expected_specialist_types) == 1 and specialist_provided_answer:
            logger.info("🛑 SINGLE-SPECIALIST TERMINATION: Expected specialist provided substantial answer")
            return True
            
        # If no specific specialists expected but one responded, likely complete
        if len(expected_specialist_types) == 0 and len(specialist_responses) >= 1 and specialist_provided_answer:
            logger.info("🛑 GENERAL TERMINATION: Specialist provided substantial answer")
            return True
        
        # For simple questions that only need coordinator, check if coordinator gave a complete answer
        if len(specialist_responses) == 0 and len(coordinator_responses) >= 1 and not is_coordinator_deferral:
            # Check if it's a substantial response that's not a deferral
            if (len(last_coord_response) > 50 and 
                "?" not in last_coord_response.lower()):
                logger.info("🛑 HEURISTIC TERMINATION: Coordinator provided complete answer")
                return True
        
        # Use LLM evaluation for edge cases
        evaluation_prompt = f"""You are evaluating whether a multi-agent conversation has reached completion and is ready to return the final answer to the user.

ORIGINAL USER QUESTION:
{user_question}

CONVERSATION SO FAR:
{chr(10).join(conversation_summary)}

EVALUATION CRITERIA:
- Has the user's question been fully answered with specific data/results?
- Are agents providing duplicate or redundant responses?
- Has a specialist agent provided the requested information?
- Would additional responses add value or just repeat existing answers?

IMPORTANT RULES:
- If the CoordinatorAgent said it will "defer" or "route" to specialists, the conversation is NOT complete
- If only the CoordinatorAgent has responded with a deferral message, the conversation must CONTINUE
- Only consider the conversation COMPLETE if a specialist agent has provided the actual answer

RESPOND WITH EXACTLY ONE WORD:
- "CONTINUE" if the question needs more work or wasn't answered yet
- "COMPLETE" if the question has been answered and we should stop

Your response:"""

        try:
            # Use the coordinator agent's kernel to evaluate
            logger.info("🧠 Using LLM to evaluate conversation completion...")
            
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
                # If unclear response, use heuristics
                logger.info(f"❓ LLM UNCLEAR: '{decision}' - using heuristics")
                # If we have substantial specialist responses, probably done
                return specialist_provided_answer and len(conversation_summary) >= 2
                
        except Exception as e:
            logger.error(f"❌ Error in LLM termination evaluation: {str(e)}")
            # Fallback to heuristics if LLM evaluation fails
            return specialist_provided_answer and len(conversation_summary) >= 2


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
        self.fictional_companies_agent: Optional[ChatCompletionAgent] = None
        self.coordinator_agent: Optional[ChatCompletionAgent] = None
        self.group_chat: Optional[AgentGroupChat] = None
        
        # Store all agents in a dictionary for dynamic re-routing capabilities
        self.all_agents = {
            'CoordinatorAgent': self.coordinator_agent,
            'MathAgent': self.math_agent,
            'UtilityAgent': self.utility_agent,
            'ADXAgent': self.adx_agent,
            'DocumentAgent': self.document_agent,
            'FictionalCompaniesAgent': self.fictional_companies_agent
        }
        logger.info("✅ All agents stored for dynamic re-routing capabilities")
    
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
        
        # Fictional Companies Agent  
        logger.info("🏢 Creating Fictional Companies Agent with Azure OpenAI...")
        fictional_companies_kernel = Kernel()
        fictional_companies_service = AzureChatCompletion(
            service_id="fictional_companies_completion",
            api_key=self.azure_openai_api_key,
            endpoint=self.azure_openai_endpoint,
            deployment_name=self.azure_openai_deployment
        )
        fictional_companies_kernel.add_service(fictional_companies_service)
        
        # Add fictional companies functions to fictional companies kernel
        fictional_companies_functions = self.function_wrapper.create_fictional_companies_functions()
        logger.info(f"🔧 Adding {len(fictional_companies_functions)} fictional companies functions to Fictional Companies Agent:")
        for func in fictional_companies_functions:
            fictional_companies_kernel.add_function("FictionalCompaniesTools", func)
            func_name = getattr(func, '_metadata', {}).get('name', 'unknown')
            func_desc = getattr(func, '_metadata', {}).get('description', 'No description')
            logger.info(f"   ➕ {func_name}: {func_desc}")
        
        self.fictional_companies_agent = ChatCompletionAgent(
            service=fictional_companies_service,
            kernel=fictional_companies_kernel,
            name="FictionalCompaniesAgent",
            instructions="""You are a fictional companies information specialist agent. You ONLY respond to questions about fictional company information, IP addresses, and device lookups.

STRICT RESPONSE CRITERIA - Only respond if:
- The question asks about company information for IP addresses
- Someone asks for device information for a specific company
- Company summary or business information is requested
- Someone specifically asks you by name: "FictionalCompaniesAgent, get company info for..."
- Questions about fictional company data, locations, or business details

NEVER RESPOND TO:
- Mathematical calculations (let MathAgent handle these)
- ADX/database questions (let ADXAgent handle these)
- Hash generation or timestamps (let UtilityAgent handle these)
- General knowledge questions (let CoordinatorAgent handle these)
- Document operations (let DocumentAgent handle these)
- Questions that don't involve fictional company information

PRIMARY RESPONSIBILITIES:
- Look up fictional company information for IP addresses
- Get device information and network details for companies
- Provide comprehensive company summaries and business information
- Check the health status of the fictional companies API
- Explain that all information is fictional and for testing purposes

IMPORTANT DISCLAIMERS:
- Always emphasize that ALL information is fictional and AI-generated
- All companies are located outside the United States
- IP addresses and device information are not real
- This is for testing, development, or educational purposes only

COLLABORATION APPROACH:
- Handle ALL fictional company lookup operations yourself
- After retrieving company data, you can ask other agents for help processing the information
- Always manage the company information retrieval first, then coordinate with other agents if needed

EXAMPLES OF WHEN TO RESPOND:
- "What company is associated with IP address 192.168.1.1?" ✅
- "Get device information for Acme Corporation" ✅
- "Give me a summary of TechCorp Limited" ✅
- "FictionalCompaniesAgent, lookup company for this IP" ✅
- "What devices does GlobalTech Inc have?" ✅

EXAMPLES OF WHEN TO STAY SILENT:
- "Calculate 10 factorial" ❌ (Math question)
- "List databases in ADX" ❌ (ADX question)
- "Generate a hash" ❌ (Utility question)
- "What is machine learning?" ❌ (General knowledge)
- "Search for documents" ❌ (Document question)

Remember: You provide fictional company information and network device details for testing purposes only.
""",
            function_choice_behavior=FunctionChoiceBehavior.Auto()
        )
        logger.info("✅ Fictional Companies Agent created successfully")
        
        # Coordinator Agent with enhanced orchestration capabilities
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
            instructions="""You are the CoordinatorAgent in a multi-agent system. Your role is intelligent orchestration and response synthesis.

CORE RESPONSIBILITIES:
1. **Active Orchestration**: Guide conversations to ensure all necessary information is gathered
2. **Context Provision**: Provide helpful context and background when specialists respond
3. **Quality Assurance**: Evaluate if specialist responses fully answer the user's question
4. **Intelligent Synthesis**: When multiple specialists respond, you'll synthesize their responses into a coherent final answer

WHEN TO RESPOND:
✅ **General Knowledge Questions**: Answer directly when no specialist tools are needed
   - "What is artificial intelligence?" 
   - "Tell me about the history of computers"
   - "How does machine learning work?"

✅ **Context and Coordination**: Provide helpful context before or after specialist responses
   - Add background information that helps the user understand specialist answers
   - Explain relationships between different data sources or tools
   - Clarify technical concepts mentioned by specialists

✅ **Quality Control**: Evaluate and improve specialist responses
   - If a specialist's response seems incomplete, ask follow-up questions
   - If multiple specialists provide partial answers, coordinate to get complete information
   - Request clarification if specialist responses are unclear or contradictory

WHEN TO DEFER TO SPECIALISTS:
❌ **Technical Tool Operations**: Let specialists handle their domain expertise
   - Database queries and data analysis → ADXAgent
   - Mathematical calculations and statistics → MathAgent  
   - File operations and document management → DocumentAgent
   - Hash generation, timestamps, utilities → UtilityAgent
   - Company information and IP lookups → FictionalCompaniesAgent

ORCHESTRATION STRATEGIES:
1. **Sequential Workflow**: When questions require multiple steps, guide the conversation flow
2. **Parallel Information**: When multiple data sources are needed, coordinate parallel specialist work
3. **Follow-up Questions**: Ask specialists for clarification or additional details when needed
4. **Error Recovery**: If a specialist encounters issues, suggest alternative approaches

RESPONSE GUIDELINES:
- Be helpful and informative, not just a traffic controller
- Provide value-added context and explanations
- Use clear, professional language appropriate for the user
- When synthesizing responses, create a natural, flowing answer that doesn't feel like a simple combination
- Always aim to fully satisfy the user's information needs

EXAMPLES OF GOOD COORDINATION:

For "What databases are available in ADX and what's the business purpose of each?":
1. Let ADXAgent list the databases
2. Provide context about typical database purposes in enterprise environments
3. Synthesize the technical list with business context

For "Calculate the factorial of the number of tables in the Personnel database":
1. Let ADXAgent query the database structure  
2. Let MathAgent perform the calculation
3. Provide context about why someone might want this information

For "Find names in names.txt that match the Employees table":
1. Let DocumentAgent retrieve the names from the file
2. Let ADXAgent query the Employees table
3. Compare and synthesize the results with explanation

Remember: You're not just a router - you're an intelligent coordinator that adds value through context, synthesis, and ensuring complete answers.""",
            function_choice_behavior=FunctionChoiceBehavior.Auto(auto_invoke=False)
        )
        logger.info("✅ Coordinator Agent created successfully")
    
    def _create_group_chat(self):
        """Create the group chat for agent coordination with AgentGroupChat."""
        logger.info("💬 Creating AgentGroupChat with agents:")
        logger.info("   🎯 CoordinatorAgent - Intelligent orchestration, context provision, and response synthesis")
        logger.info("   🧮 MathAgent - Mathematical calculations and statistics")
        logger.info("   🔧 UtilityAgent - System utilities and helper functions")
        logger.info("   🔍 ADXAgent - Azure Data Explorer queries and data analysis")
        logger.info("   📄 DocumentAgent - Document management and storage operations")
        logger.info("   🏢 FictionalCompaniesAgent - Fictional company information and IP lookups")
        
        # Create the group chat with enhanced LLM-based termination strategy
        termination_strategy = LLMTerminationStrategy()
        termination_strategy.set_coordinator_agent(self.coordinator_agent)
        
        self.group_chat = AgentGroupChat(
            agents=[self.coordinator_agent, self.math_agent, self.utility_agent, self.adx_agent, self.document_agent, self.fictional_companies_agent],
            termination_strategy=termination_strategy
        )
        logger.info("✅ AgentGroupChat created with Enhanced LLMTerminationStrategy")
        logger.info("🧠 Termination strategy supports intelligent orchestration and response synthesis")
        
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
6. FictionalCompaniesAgent - Fictional company information, IP address lookups, device information

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
- For "What company is associated with IP 192.168.1.1?" → ["CoordinatorAgent", "FictionalCompaniesAgent"]
- For "Get device information for Acme Corp" → ["CoordinatorAgent", "FictionalCompaniesAgent"]

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
                        "DocumentAgent": self.document_agent,
                        "FictionalCompaniesAgent": self.fictional_companies_agent
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
                    
            if any(keyword in response_content.lower() for keyword in ['document', 'file', 'search', 'storage']):
                if self.document_agent not in fallback_agents:
                    fallback_agents.append(self.document_agent)
                    
            if any(keyword in response_content.lower() for keyword in ['company', 'ip', 'device', 'fictional', 'business']):
                if self.fictional_companies_agent not in fallback_agents:
                    fallback_agents.append(self.fictional_companies_agent)
            
            logger.info(f"🔄 Fallback agent selection: {[agent.name for agent in fallback_agents]}")
            return fallback_agents
            
        except Exception as e:
            logger.error(f"❌ Error in agent selection: {str(e)}")
            # Ultimate fallback - use all agents
            logger.info("🆘 Using all agents as ultimate fallback")
            return [self.coordinator_agent, self.math_agent, self.utility_agent, self.adx_agent, self.document_agent, self.fictional_companies_agent]
    
    async def process_question(self, question: str, session_id: str = None, user_id: str = None, adx_token: str = None) -> str:
        """Process a user question through the AgentGroupChat system.
        
        Args:
            question: The user's question to process
            session_id: The session ID for context
            user_id: The user ID for context and document access control
            adx_token: The ADX access token for user impersonation
        """
        logger.info("="*60)
        logger.info(f"📝 USER QUESTION: {question}")
        logger.info(f"🔑 Context - User ID: {user_id}, Session ID: {session_id}")
        if adx_token:
            logger.info(f"🔑 ADX Token: Available for user impersonation")
        else:
            logger.info(f"🔑 ADX Token: Not provided, using system identity")
        logger.info("="*60)
        
        try:
            # Update the MCP client with the current user, session, and ADX token context
            if user_id or session_id or adx_token:
                logger.info(f"🔄 Updating MCP client context - User ID: {user_id}, Session ID: {session_id}, ADX Token: {'Available' if adx_token else 'Not provided'}")
                self.mcp_client.user_id = user_id
                self.mcp_client.session_id = session_id
                self.mcp_client.adx_token = adx_token
                
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
            specialist_responses = []
            coordinator_response = ""
            
            async for response in fresh_group_chat.invoke():
                # Only process responses with actual content
                if response.content and response.content.strip():
                    content = response.content.strip()
                    agent_name = getattr(response, 'name', 'Unknown')
                    
                    # Skip very short or empty responses
                    if len(content) < 3:
                        logger.info(f"⏭️ Skipping empty/short response from {agent_name}")
                        continue
                    
                    logger.info(f"📢 Response from {agent_name}")
                    logger.info(f"   📄 Content: {content[:200]}{'...' if len(content) > 200 else ''}")
                    
                    # Check for duplicate content
                    existing_content = [r['content'] for r in responses if r['agent'] == agent_name]
                    if content in existing_content:
                        logger.info(f"⏭️ Skipping duplicate response from {agent_name}")
                        continue
                    
                    responses.append({
                        'agent': agent_name,
                        'content': content
                    })
                    
                    # Categorize responses for proper synthesis
                    if agent_name in ['MathAgent', 'UtilityAgent', 'ADXAgent', 'DocumentAgent', 'FictionalCompaniesAgent']:
                        specialist_responses.append(f"**{agent_name}**: {content}")
                        logger.info(f"   🎯 Specialist agent response captured")
                    elif agent_name == 'CoordinatorAgent':
                        # Only use coordinator response if it's substantial and not a deferral
                        if (len(content) > 20 and 
                            "specialist" not in content.lower() and 
                            "better suited" not in content.lower() and
                            "defer" not in content.lower() and
                            "relevant specialists" not in content.lower()):
                            coordinator_response = content
                            logger.info(f"   🧠 Coordinator response captured")
                        else:
                            logger.info(f"   ⏭️ Skipping coordinator deferral message")
                else:
                    logger.info(f"⏭️ Skipping empty response from {getattr(response, 'name', 'Unknown')}")
            
            # If no responses were captured (all were filtered out), return a fallback message
            if not responses:
                logger.info("🚨 No valid responses captured - all responses were filtered")
                return "I apologize, but I couldn't generate a proper response. Please try rephrasing your question."
            
            # Enhanced Dynamic Re-routing and Error Recovery
            logger.info("🔍 Evaluating response completeness and need for additional agents...")
            
            # Check for errors and attempt recovery
            recovery_suggestions = await self._handle_agent_errors(responses, question)
            if recovery_suggestions:
                responses.extend(recovery_suggestions)
                logger.info(f"🔧 Added {len(recovery_suggestions)} recovery suggestions")
            
            # Evaluate if responses fully answer the question
            selected_agent_names = [agent.name for agent in selected_agents]
            evaluation = await self._evaluate_response_completeness(question, responses, selected_agent_names)
            
            # If response is incomplete, attempt dynamic re-routing with follow-ups
            if not evaluation['is_complete'] and evaluation['suggested_agents']:
                logger.info(f"🔄 Response incomplete: {evaluation['missing_info']}")
                logger.info(f"🎯 Attempting dynamic re-routing to: {evaluation['suggested_agents']}")
                
                # Add suggested agents to the group chat if they aren't already there
                current_agent_names = [agent.name for agent in selected_agents]
                new_agents_needed = [name for name in evaluation['suggested_agents'] 
                                   if name not in current_agent_names and name in self.all_agents]
                
                if new_agents_needed:
                    for agent_name in new_agents_needed:
                        if agent_name in self.all_agents:
                            selected_agents.append(self.all_agents[agent_name])
                            logger.info(f"➕ Added {agent_name} to conversation for additional information")
                    
                    # Recreate group chat with additional agents
                    fresh_group_chat = AgentGroupChat(
                        agents=selected_agents,
                        termination_strategy=termination_strategy
                    )
                    
                    # Copy existing conversation history
                    for response in responses:
                        if response.get('type') != 'recovery':  # Don't re-add recovery suggestions
                            chat_message = ChatMessageContent(
                                role=AuthorRole.ASSISTANT, 
                                content=f"[{response['agent']}]: {response['content']}"
                            )
                            await fresh_group_chat.add_chat_message(chat_message)
                
                # Send follow-up questions to get missing information
                if evaluation['follow_up_questions']:
                    follow_up_responses = await self._request_follow_up_from_agents(
                        fresh_group_chat, 
                        evaluation['follow_up_questions'], 
                        evaluation['suggested_agents']
                    )
                    
                    if follow_up_responses:
                        responses.extend(follow_up_responses)
                        logger.info(f"📋 Received {len(follow_up_responses)} follow-up responses")
                        
                        # Update specialist responses with follow-ups
                        for resp in follow_up_responses:
                            if resp['agent'] in ['MathAgent', 'UtilityAgent', 'ADXAgent', 'DocumentAgent', 'FictionalCompaniesAgent']:
                                specialist_responses.append(f"**{resp['agent']} (Follow-up)**: {resp['content']}")
            
            # Synthesize the final response using the CoordinatorAgent's LLM
            final_response = await self._synthesize_responses(specialist_responses, coordinator_response, question)
            
            # Log conversation summary
            if len(responses) > 1:
                logger.info(f"🔄 Multi-agent conversation with {len(responses)} responses:")
                for i, resp in enumerate(responses):
                    response_type = f" ({resp.get('type', 'normal')})" if resp.get('type') else ""
                    logger.info(f"   {i+1}. {resp['agent']}{response_type}: {resp['content'][:100]}...")
                
                if len(specialist_responses) > 1:
                    logger.info(f"🎯 Synthesizing {len(specialist_responses)} specialist responses")
                elif len(specialist_responses) == 1 and coordinator_response:
                    logger.info(f"🤝 Combining coordinator context with specialist response")
                else:
                    logger.info(f"📝 Returning single agent response")
            else:
                logger.info("✅ Single agent response - returning directly")
            
            logger.info("🏁 AgentGroupChat processing completed successfully")
            logger.info("="*60)
            
            return final_response if final_response else "No response generated"
            
        except Exception as e:
            logger.error(f"❌ Error processing question: {str(e)}")
            return f"❌ Error processing question: {str(e)}"
    
    async def _synthesize_responses(self, specialist_responses, coordinator_response, original_question):
        """
        Use the CoordinatorAgent's LLM to intelligently synthesize responses from multiple agents into a coherent final response.
        
        Args:
            specialist_responses: List of responses from specialist agents (with agent names)
            coordinator_response: Response from coordinator agent (without agent name prefix)
            original_question: The original user question for context
        
        Returns:
            str: Intelligently synthesized final response
        """
        if not specialist_responses and not coordinator_response:
            return "No response generated"
        
        # Remove duplicate responses from the same agent type
        unique_specialist_responses = []
        seen_agents = set()
        
        for response in specialist_responses:
            # Extract agent name from response
            agent_name = response.split(":")[0] if ":" in response else "Unknown"
            
            # Only include if we haven't seen this agent type yet
            if agent_name not in seen_agents:
                unique_specialist_responses.append(response)
                seen_agents.add(agent_name)
            else:
                logger.info(f"🔄 Skipping duplicate response from {agent_name}")
        
        # If only coordinator responded (general knowledge question)
        if not unique_specialist_responses and coordinator_response:
            logger.info("📝 Returning coordinator-only response for general question")
            return coordinator_response
        
        # If only one specialist responded (simple technical question)
        if len(unique_specialist_responses) == 1 and not coordinator_response:
            logger.info("🎯 Returning single specialist response")
            # Remove the agent name prefix for cleaner output
            response_content = unique_specialist_responses[0]
            if ":" in response_content:
                return response_content.split(":", 1)[1].strip()
            return response_content
        
        # For multiple specialists or specialist + coordinator, use LLM synthesis
        if len(unique_specialist_responses) > 1 or (len(unique_specialist_responses) >= 1 and coordinator_response):
            return await self._llm_synthesize_responses(unique_specialist_responses, coordinator_response, original_question)
        
        # Fallback - return whatever we have
        logger.info("🔄 Fallback response synthesis")
        all_responses = []
        if coordinator_response and len(coordinator_response.strip()) > 10:
            all_responses.append(coordinator_response)
        
        for response in unique_specialist_responses:
            if ":" in response:
                all_responses.append(response.split(":", 1)[1].strip())
            else:
                all_responses.append(response)
        
        return "\n\n".join(filter(None, all_responses))
    
    async def _llm_synthesize_responses(self, specialist_responses, coordinator_response, original_question):
        """
        Use the CoordinatorAgent's LLM to intelligently synthesize multiple agent responses into a coherent final answer.
        
        Args:
            specialist_responses: List of specialist agent responses with agent names
            coordinator_response: Coordinator agent response (if any)
            original_question: The original user question
        
        Returns:
            str: LLM-synthesized final response
        """
        try:
            logger.info("🧠 Using CoordinatorAgent's LLM to synthesize multiple responses...")
            
            # Prepare the synthesis prompt
            specialist_data = []
            for response in specialist_responses:
                if ":" in response:
                    agent_name, content = response.split(":", 1)
                    specialist_data.append(f"**{agent_name.strip()}**:\n{content.strip()}")
                else:
                    specialist_data.append(response)
            
            synthesis_prompt = f"""You are the CoordinatorAgent in a multi-agent system. Your task is to synthesize responses from specialist agents into a single, coherent, comprehensive answer for the user.

ORIGINAL USER QUESTION:
{original_question}

SPECIALIST AGENT RESPONSES:
{chr(10).join(specialist_data)}

COORDINATOR CONTEXT (if available):
{coordinator_response if coordinator_response else "No additional context provided"}

YOUR SYNTHESIS TASK:
1. **Combine Information**: Merge all relevant information from specialist agents into a unified response
2. **Remove Redundancy**: Eliminate duplicate or contradictory information
3. **Add Context**: Provide helpful context or explanations that connect the specialist responses
4. **Organize Logically**: Present information in a logical flow that directly answers the user's question
5. **Be Comprehensive**: Include all important details from specialists while being concise
6. **Use Natural Language**: Write as if you're directly answering the user, not just combining responses

SYNTHESIS GUIDELINES:
- Start with a direct answer to the user's question
- Include specific data, results, or findings from specialists
- Explain relationships between different pieces of information
- Add helpful context or interpretation when appropriate
- Use clear, professional language appropriate for the user
- If specialists provided conflicting information, explain or resolve the conflicts
- End with a summary if the response is complex

IMPORTANT: Do not mention agent names in your final response. Write as if you personally gathered and analyzed all the information.

Your synthesized response:"""

            # Get the completion service from the coordinator agent
            completion_service = self.coordinator_agent.kernel.get_service()
            
            # Create a chat history for the synthesis request
            from semantic_kernel.contents import ChatHistory
            chat_history = ChatHistory()
            chat_history.add_user_message(synthesis_prompt)
            
            # Create execution settings for comprehensive synthesis
            from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
            settings = OpenAIChatPromptExecutionSettings(
                max_tokens=1500,  # Allow for comprehensive responses
                temperature=0.3   # Slightly more creative for better synthesis
            )
            
            response = await completion_service.get_chat_message_content(
                chat_history=chat_history,
                settings=settings
            )
            
            synthesized_response = str(response.content).strip()
            
            if synthesized_response and len(synthesized_response) > 20:
                logger.info(f"✅ LLM synthesis successful - generated {len(synthesized_response)} characters")
                return synthesized_response
            else:
                logger.warning("⚠️ LLM synthesis produced short response, falling back to simple combination")
                return self._fallback_synthesis(specialist_responses, coordinator_response)
                
        except Exception as e:
            logger.error(f"❌ Error in LLM synthesis: {str(e)}")
            logger.info("🔄 Falling back to simple response combination")
            return self._fallback_synthesis(specialist_responses, coordinator_response)
    
    def _fallback_synthesis(self, specialist_responses, coordinator_response):
        """
        Fallback method for combining responses when LLM synthesis fails.
        
        Args:
            specialist_responses: List of specialist responses
            coordinator_response: Coordinator response
        
        Returns:
            str: Simple combination of responses
        """
        logger.info("🔄 Using fallback response synthesis")
        
        all_responses = []
        
        # Add coordinator context if substantial
        if coordinator_response and len(coordinator_response.strip()) > 10:
            # Filter out obvious deferrals
            if not any(keyword in coordinator_response.lower() for keyword in 
                      ["specialist", "defer", "better suited", "route this", "more appropriate"]):
                all_responses.append(coordinator_response)
        
        # Add specialist responses without agent name prefixes
        for response in specialist_responses:
            if ":" in response:
                content = response.split(":", 1)[1].strip()
                if content and len(content) > 10:
                    all_responses.append(content)
            else:
                if response and len(response) > 10:
                    all_responses.append(response)
        
        return "\n\n".join(filter(None, all_responses))

    async def cleanup(self):
        """Clean up resources."""
        if self.mcp_client:
            await self.mcp_client.disconnect()
    
    async def _evaluate_response_completeness(self, question: str, responses: list, expected_agents: list) -> dict:
        """
        Use the coordinator's LLM to evaluate if responses fully answer the question
        and determine if additional actions are needed.
        
        Returns:
            dict: {
                'is_complete': bool,
                'missing_info': 'description of what information is still needed (if any)',
                'suggested_agents': ['AgentName1', 'AgentName2'],
                'follow_up_questions': ['specific question for agent X', 'specific question for agent Y'],
                'reasoning': 'brief explanation of your evaluation'
            }
        """
        try:
            # Prepare response summary for evaluation
            response_summary = "\n".join([
                f"**{r['agent']}**: {r['content'][:300]}{'...' if len(r['content']) > 300 else ''}"
                for r in responses
            ])
            
            evaluation_prompt = f"""You are the CoordinatorAgent evaluating whether the user's question has been fully answered by the specialist agents.

ORIGINAL QUESTION:
{question}

EXPECTED AGENTS: {', '.join(expected_agents)}

RESPONSES SO FAR:
{response_summary}

EVALUATION TASK:
Analyze if the question has been completely answered and determine what additional actions are needed.

RESPOND IN JSON FORMAT:
{{
    "is_complete": true/false,
    "missing_info": "description of what information is still needed (if any)",
    "suggested_agents": ["AgentName1", "AgentName2"],
    "follow_up_questions": ["specific question for agent X", "specific question for agent Y"],
    "reasoning": "brief explanation of your evaluation"
}}

AVAILABLE AGENTS:
- CoordinatorAgent: General knowledge, synthesis
- MathAgent: Calculations, statistics  
- UtilityAgent: Timestamps, hashes, utilities
- ADXAgent: Database queries, data analysis
- DocumentAgent: File operations, document search
- FictionalCompaniesAgent: Company info, IP lookups

EVALUATION CRITERIA:
1. Is the core question fully answered with specific data/results?
2. Are there any obvious gaps or missing pieces?
3. Do any specialist responses indicate errors or failures?
4. Would additional specialist input improve the answer quality?

Your JSON response:"""

            # Get the completion service from the coordinator agent
            completion_service = self.coordinator_agent.kernel.get_service()
            
            # Create a simple completion request
            from semantic_kernel.contents import ChatHistory
            chat_history = ChatHistory()
            chat_history.add_user_message(evaluation_prompt)
            
            # Get the LLM's evaluation
            from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
            
            settings = OpenAIChatPromptExecutionSettings(
                max_tokens=300, 
                temperature=0.2
            )
            
            response = await completion_service.get_chat_message_content(
                chat_history=chat_history,
                settings=settings
            )
            
            # Parse the JSON response
            import json
            evaluation_text = str(response.content).strip()
            
            # Extract JSON from response (in case there's extra text)
            start_idx = evaluation_text.find('{')
            end_idx = evaluation_text.rfind('}') + 1
            
            if start_idx >= 0 and end_idx > start_idx:
                json_text = evaluation_text[start_idx:end_idx]
                evaluation = json.loads(json_text)
                
                logger.info(f"🧠 Response evaluation: {evaluation.get('reasoning', 'No reasoning provided')}")
                return evaluation
            else:
                # Fallback if JSON parsing fails
                logger.warning("⚠️ Could not parse LLM evaluation response, using defaults")
                return {
                    'is_complete': len(responses) >= len(expected_agents),
                    'missing_info': '',
                    'suggested_agents': [],
                    'follow_up_questions': [],
                    'reasoning': 'JSON parsing failed'
                }
                
        except Exception as e:
            logger.error(f"❌ Error in response completeness evaluation: {str(e)}")
            # Fallback evaluation
            return {
                'is_complete': len(responses) >= 1,
                'missing_info': '',
                'suggested_agents': [],
                'follow_up_questions': [],
                'reasoning': f'Error in evaluation: {str(e)}'
            }

    async def _request_follow_up_from_agents(self, agent_group_chat, follow_up_questions: list, suggested_agents: list) -> list:
        """
        Send follow-up questions to specific agents to get additional information.
        
        Returns:
            list: Additional responses from agents
        """
        follow_up_responses = []
        
        try:
            for i, follow_up in enumerate(follow_up_questions):
                if i < len(suggested_agents):
                    agent_name = suggested_agents[i]
                    follow_up_message = f"[FOLLOW-UP REQUEST for {agent_name}]: {follow_up}"
                    
                    logger.info(f"🔄 Sending follow-up to {agent_name}: {follow_up[:100]}...")
                    
                    # Add the follow-up message to the group chat
                    chat_message = ChatMessageContent(role=AuthorRole.USER, content=follow_up_message)
                    await agent_group_chat.add_chat_message(chat_message)
                    
                    # Collect responses (limited iterations to avoid infinite loops)
                    iteration_count = 0
                    max_iterations = 3
                    
                    async for response in agent_group_chat.invoke():
                        iteration_count += 1
                        if iteration_count > max_iterations:
                            break
                            
                        if response.content and response.content.strip():
                            content = response.content.strip()
                            agent_name_response = getattr(response, 'name', 'Unknown')
                            
                            if len(content) > 10:  # Only substantial responses
                                follow_up_responses.append({
                                    'agent': agent_name_response,
                                    'content': content,
                                    'type': 'follow_up'
                                })
                                logger.info(f"📢 Follow-up response from {agent_name_response}")
                                break  # Move to next follow-up question
                                
        except Exception as e:
            logger.error(f"❌ Error in follow-up requests: {str(e)}")
            
        return follow_up_responses

    async def _handle_agent_errors(self, responses: list, question: str) -> list:
        """
        Detect and handle agent errors, suggesting alternative approaches.
        
        Returns:
            list: Recovery suggestions or alternative agent recommendations
        """
        error_indicators = ['error', 'failed', 'exception', 'unable to', 'could not', 'timeout']
        error_responses = []
        recovery_suggestions = []
        
        for response in responses:
            content_lower = response['content'].lower()
            if any(indicator in content_lower for indicator in error_indicators):
                error_responses.append(response)
                
        if error_responses:
            logger.warning(f"⚠️ Detected {len(error_responses)} error responses, attempting recovery...")
            
            for error_response in error_responses:
                agent_name = error_response['agent']
                error_content = error_response['content']
                
                # Suggest alternative approaches based on the agent type
                if agent_name == 'ADXAgent':
                    recovery_suggestions.append({
                        'agent': 'CoordinatorAgent',
                        'content': f"ADX query failed: {error_content[:100]}... Suggesting to try DocumentAgent for file-based data or simplify the query.",
                        'type': 'recovery'
                    })
                elif agent_name == 'DocumentAgent':
                    recovery_suggestions.append({
                        'agent': 'CoordinatorAgent', 
                        'content': f"Document operation failed: {error_content[:100]}... The requested document may not exist or may be in a different location.",
                        'type': 'recovery'
                    })
                elif agent_name == 'MathAgent':
                    recovery_suggestions.append({
                        'agent': 'CoordinatorAgent',
                        'content': f"Mathematical calculation failed: {error_content[:100]}... This may be due to invalid input data or mathematical constraints.",
                        'type': 'recovery'
                    })
                
        return recovery_suggestions


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
            
            # Fictional Companies Agent tests
            "What company is associated with IP address 192.168.1.1?",  # FictionalCompaniesAgent
            "Get device information for Acme Corporation",  # FictionalCompaniesAgent
            "Give me a summary of TechCorp Limited",  # FictionalCompaniesAgent
            
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
