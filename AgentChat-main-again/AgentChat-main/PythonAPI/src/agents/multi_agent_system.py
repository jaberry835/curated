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
    """Simplified termination strategy that gives the CoordinatorAgent full control over conversation completion."""
    
    def __init__(self):
        super().__init__()
        self._coordinator_agent = None
        self._max_iterations = 8  # Safety limit to prevent infinite loops
        self._iteration_count = 0
    
    def set_coordinator_agent(self, coordinator_agent: ChatCompletionAgent):
        """Set the coordinator agent after initialization."""
        self._coordinator_agent = coordinator_agent
    
    async def should_agent_terminate(self, agent, history: List[ChatMessageContent], cancellation_token=None) -> bool:
        """Enhanced termination strategy: Only the CoordinatorAgent decides when conversation is complete."""
        self._iteration_count += 1
        
        # Safety check to prevent infinite loops
        if self._iteration_count >= self._max_iterations:
            logger.info(f"🛑 SAFETY TERMINATION: Reached max iterations ({self._max_iterations})")
            return True
        
        # Need at least a user question and one response
        if len(history) < 2:
            return False
        
        # Extract the conversation for analysis
        user_question = ""
        coordinator_responses = []
        specialist_responses = []
        
        for msg in history:
            if msg.role == AuthorRole.USER:
                user_question = str(msg.content)
            elif hasattr(msg, 'name') and msg.name:
                agent_name = msg.name
                content = str(msg.content)
                
                if agent_name == 'CoordinatorAgent':
                    coordinator_responses.append(content)
                elif agent_name in ['MathAgent', 'UtilityAgent', 'ADXAgent', 'DocumentAgent', 'FictionalCompaniesAgent']:
                    specialist_responses.append(f"{agent_name}: {content}")
        
        # CORE PRINCIPLE: Only terminate when CoordinatorAgent explicitly provides a complete final answer
        
        # Must have a response from the coordinator
        if not coordinator_responses:
            logger.info("⏩ CONTINUE: No coordinator response yet")
            return False
        
        # Check if the last response was from the CoordinatorAgent
        last_response = history[-1] if history else None
        last_was_coordinator = (hasattr(last_response, 'name') and 
                               last_response.name == 'CoordinatorAgent')
        
        if not last_was_coordinator:
            # If a specialist just responded, always give coordinator a chance to synthesize
            logger.info("⏩ CONTINUE: Specialist responded, coordinator must synthesize")
            return False
        
        # Get the last coordinator response
        last_coordinator_response = str(last_response.content) if last_response else ""
        
        # Enhanced deferral detection - be more strict about what constitutes a deferral
        coordination_phrases = [
            "let me", "i'll", "i will", "i should", "i need to", "let's", "we need",
            "adxagent", "mathagent", "documentagent", "utilityagent", "fictionalcompaniesagent",
            "defer", "route", "direct", "involve", "delegate", "forward",
            "query", "check", "calculate", "retrieve", "search", "find",
            "asking", "requesting", "need to get", "should get", "will get",
            "let's query", "let's check", "let's calculate", "let's search",
            "first, let", "next, i'll", "then i'll", "i'll need to"
        ]
        
        response_lower = last_coordinator_response.lower()
        is_coordination_message = any(phrase in response_lower for phrase in coordination_phrases)
        
        if is_coordination_message:
            logger.info("⏩ CONTINUE: Coordinator is coordinating/delegating to specialists")
            return False
        
        # Check for incomplete response indicators
        incomplete_indicators = [
            "working on", "processing", "getting", "retrieving", "calculating",
            "let me know", "please provide", "i need", "waiting for", "pending",
            "will provide", "coming up", "shortly", "moment"
        ]
        
        is_incomplete = any(indicator in response_lower for indicator in incomplete_indicators)
        
        if is_incomplete:
            logger.info("⏩ CONTINUE: Coordinator response indicates work in progress")
            return False
        
        # Require substantial content for termination (minimum 80 characters)
        if len(last_coordinator_response.strip()) < 80:
            logger.info("⏩ CONTINUE: Coordinator response too brief for termination")
            return False
        
        # If specialists have provided responses, coordinator must synthesize them
        if len(specialist_responses) > 0:
            # Check if coordinator response actually references or synthesizes specialist input
            specialist_agent_names = ['mathagent', 'utilityagent', 'adxagent', 'documentagent', 'fictionalcompaniesagent']
            references_specialists = any(name in response_lower for name in specialist_agent_names)
            
            # Look for synthesis indicators in coordinator response
            synthesis_indicators = [
                "based on", "according to", "the data shows", "the analysis reveals",
                "the calculation", "the query", "the search", "the results",
                "combining", "together", "overall", "in summary", "to summarize",
                "from the", "using the", "with the", "as shown", "indicates that"
            ]
            
            shows_synthesis = any(indicator in response_lower for indicator in synthesis_indicators)
            
            # If specialists responded but coordinator doesn't appear to synthesize, continue
            if not (references_specialists or shows_synthesis):
                logger.info("⏩ CONTINUE: Coordinator hasn't synthesized specialist responses yet")
                return False
            
            # Additional check: ensure coordinator response is substantially longer than just coordination
            coordination_only_phrases = [
                "let me", "i'll", "i will", "let's", "we need", "i need to", "should get"
            ]
            
            seems_coordination_only = any(phrase in response_lower for phrase in coordination_only_phrases)
            if seems_coordination_only and len(last_coordinator_response.strip()) < 150:
                logger.info("⏩ CONTINUE: Coordinator response appears to be coordination-only, not final synthesis")
                return False
        
        # Enhanced LLM evaluation with stricter criteria
        try:
            evaluation_prompt = f"""You are the CoordinatorAgent making a CRITICAL decision about conversation completion.

USER'S ORIGINAL QUESTION:
{user_question}

YOUR LAST RESPONSE:
{last_coordinator_response}

SPECIALIST RESPONSES (if any):
{chr(10).join(specialist_responses) if specialist_responses else "None provided"}

STRICT COMPLETION CRITERIA - ALL must be true to say COMPLETE:
1. You have directly and fully answered the user's specific question
2. If specialists provided data, you have properly synthesized/used their information  
3. Your response is comprehensive and leaves no important aspects unaddressed
4. You are not delegating, coordinating, or requesting additional information
5. The user would be satisfied with this as a complete, final answer

CRITICAL: If ANY of these criteria are not met, you MUST respond CONTINUE.

Only respond "COMPLETE" if you are absolutely certain your response fully satisfies the user's question and needs no further work.

RESPOND WITH EXACTLY ONE WORD - COMPLETE or CONTINUE:"""

            # Get the completion service from the coordinator agent
            completion_service = self._coordinator_agent.kernel.get_service()
            
            from semantic_kernel.contents import ChatHistory
            from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
            
            chat_history = ChatHistory()
            chat_history.add_user_message(evaluation_prompt)
            
            settings = OpenAIChatPromptExecutionSettings(
                max_tokens=10, 
                temperature=0.0  # More deterministic
            )
            
            response = await completion_service.get_chat_message_content(
                chat_history=chat_history,
                settings=settings
            )
            
            decision = str(response.content).strip().upper()
            
            # Extra validation: even if LLM says complete, do a final sanity check
            if "COMPLETE" in decision:
                # Ensure the response is substantial enough to be considered complete
                if len(last_coordinator_response.strip()) < 50:
                    logger.info("⏩ COORDINATOR OVERRIDE: Response too brief despite COMPLETE decision")
                    return False
                
                # If specialists provided information, ensure coordinator response acknowledges it
                if len(specialist_responses) > 0:
                    # Quick check that coordinator response mentions data/results/findings
                    data_acknowledgment = any(word in response_lower for word in [
                        "data", "result", "finding", "information", "calculation", "query", "analysis"
                    ])
                    
                    if not data_acknowledgment:
                        logger.info("⏩ COORDINATOR OVERRIDE: No acknowledgment of specialist data despite COMPLETE decision")
                        return False
                
                logger.info("🛑 COORDINATOR AUTHORITY: Final answer confirmed as complete")
                return True
            else:
                logger.info("⏩ COORDINATOR AUTHORITY: More work needed - conversation continues")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error in coordinator evaluation: {str(e)}")
            # Conservative fallback - always continue if evaluation fails
            logger.info("⏩ FALLBACK: Continue due to evaluation error")
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
        
        # Agent registry with metadata for dynamic discovery and selection
        self.agent_registry = {}  # Will be populated after agents are created
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

🚨 **MANDATORY SCHEMA-FIRST WORKFLOW - NO EXCEPTIONS:**

**STEP 1: ALWAYS CHECK SCHEMA BEFORE ANY QUERY**
- Use adx_list_tables() to see available tables in the database
- Use adx_describe_table() to get EXACT column names and types
- NEVER guess table or column names - schema discovery is MANDATORY

**STEP 2: CONSTRUCT QUERIES USING EXACT SCHEMA NAMES**
- Use the exact table names returned by adx_list_tables()
- Use the exact column names returned by adx_describe_table()
- Case matters! "scans" ≠ "Scans" ≠ "SCANS"

**STEP 3: EXECUTE QUERY WITH CORRECT SYNTAX**
- Only after confirming schema, execute the query
- If query fails, re-check schema - don't guess alternatives

� **CRITICAL NAMING CONVENTIONS:**
- Table names: Usually lowercase (e.g., "scans", "users", "events")
- Column names: Often snake_case (e.g., "ip_address", "user_name", "created_date") 
- BUT schemas vary! Some use camelCase, PascalCase, or other conventions
- The ONLY way to know is to check the schema first!

📝 **REQUIRED WORKFLOW EXAMPLE:**
For ANY query involving tables:

```
User: "Find IP 1.2.3.4 in the scans table"

Step 1: adx_list_tables("personnel")  // Confirm "scans" exists
Step 2: adx_describe_table("personnel", "scans")  // Get exact column names
Step 3: Based on schema, construct: scans | where ip_address == "1.2.3.4"
```

🚫 **NEVER DO THIS:**
- `SCANS | where IPAddress == "1.2.3.4"` (guessing names)
- `Scans | where IP_Address == "1.2.3.4"` (assuming case)
- Any query without first checking schema

✅ **ALWAYS DO THIS:**
1. Check schema with adx_describe_table()
2. Use exact names from schema results
3. Construct query with verified names

🔧 **ERROR HANDLING:**
If you get "Failed to resolve table or column":
1. You skipped schema checking - go back to Step 1
2. Re-run adx_describe_table() to get correct names
3. Do NOT try multiple variations - use schema results only

COLLABORATION APPROACH:
- Handle ALL database/ADX parts of questions yourself
- After getting data, coordinate with other agents if needed
- Always get the data first using proper schema workflow

EXAMPLES OF PROPER RESPONSES:
❌ BAD: "Let me query the SCANS table..." (guessing)
✅ GOOD: "Let me first check what tables are available, then examine the schema..."

REMEMBER: No queries without schema verification! Schema first, always!
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
            instructions="PLACEHOLDER - Will be updated dynamically after registry is built",
            function_choice_behavior=FunctionChoiceBehavior.Auto(auto_invoke=False)
        )
        logger.info("✅ Coordinator Agent created successfully")
        
        # Build the agent registry with metadata for dynamic discovery
        self._build_agent_registry()
        
        # Update coordinator instructions with dynamic agent information
        self._update_coordinator_instructions()
    
    def _build_agent_registry(self):
        """Build the agent registry with metadata for dynamic agent selection and discovery."""
        logger.info("📋 Building dynamic agent registry...")
        
        self.agent_registry = {
            'CoordinatorAgent': {
                'agent': self.coordinator_agent,
                'description': 'General knowledge, orchestration, system information, and response synthesis',
                'keywords': ['general', 'what', 'how', 'explain', 'agents', 'system', 'available', 'help', 'guide'],
                'examples': [
                    'What is Python?',
                    'What agents are available?', 
                    'How does this system work?',
                    'Tell me about artificial intelligence'
                ]
            },
            'MathAgent': {
                'agent': self.math_agent,
                'description': 'Mathematical calculations, statistics, and numerical analysis',
                'keywords': ['math', 'calculate', 'factorial', 'statistics', 'add', 'subtract', 'multiply', 'divide', 'average', 'sum'],
                'examples': [
                    'Calculate 5 factorial',
                    'What is 25 + 37?',
                    'Find the average of these numbers'
                ]
            },
            'UtilityAgent': {
                'agent': self.utility_agent,
                'description': 'Hash generation, timestamps, system utilities, and formatting',
                'keywords': ['hash', 'timestamp', 'utility', 'format', 'sha256', 'md5', 'health', 'json'],
                'examples': [
                    'Generate a SHA256 hash',
                    'What is the current timestamp?',
                    'Check system health'
                ]
            },
            'ADXAgent': {
                'agent': self.adx_agent,
                'description': 'Azure Data Explorer queries, database operations, and data retrieval',
                'keywords': ['adx', 'database', 'query', 'data', 'table', 'schema', 'kusto', 'kql', 'list', 'search'],
                'examples': [
                    'List ADX databases',
                    'Query the scans table',
                    'Show me database schemas'
                ]
            },
            'DocumentAgent': {
                'agent': self.document_agent,
                'description': 'Document management, file storage, search, and retrieval operations',
                'keywords': ['document', 'file', 'search', 'storage', 'upload', 'download', 'list', 'content'],
                'examples': [
                    'List my documents',
                    'Search documents about AI',
                    'Get document content summary'
                ]
            },
            'FictionalCompaniesAgent': {
                'agent': self.fictional_companies_agent,
                'description': 'Fictional company information, IP address lookups, and device information',
                'keywords': ['company', 'ip', 'device', 'fictional', 'business', 'lookup', 'network'],
                'examples': [
                    'What company owns IP 192.168.1.1?',
                    'Get device information for Acme Corp',
                    'Lookup company details'
                ]
            }
        }
        
        # Update the all_agents mapping with the actual agent objects
        self.all_agents = {name: info['agent'] for name, info in self.agent_registry.items()}
        
        logger.info(f"✅ Agent registry built with {len(self.agent_registry)} agents")
        for name, info in self.agent_registry.items():
            logger.info(f"   📋 {name}: {info['description']}")
    
    def _update_coordinator_instructions(self):
        """Update the coordinator agent's instructions with dynamic agent information."""
        logger.info("🔄 Updating CoordinatorAgent instructions with dynamic agent information...")
        
        # Update the coordinator agent's instructions
        self.coordinator_agent._instructions = self._generate_coordinator_instructions()
        logger.info("✅ CoordinatorAgent instructions updated with current agent registry")
    
    def get_available_agents_info(self) -> str:
        """Get a formatted string of available agents and their capabilities - useful for testing."""
        if not self.agent_registry:
            return "Agent registry not yet initialized."
        
        info_lines = [f"This multi-agent system includes {len(self.agent_registry)} specialized agents:"]
        for name, info in self.agent_registry.items():
            if name == 'CoordinatorAgent':
                info_lines.append(f"• **{name}** (orchestration) - {info['description']}")
            else:
                info_lines.append(f"• **{name}** - {info['description']}")
        
        info_lines.append("\nEach agent has specialized tools to help answer questions in their domain.")
        return "\n".join(info_lines)
    
    
    def _generate_coordinator_instructions(self) -> str:
        """Generate dynamic coordinator instructions based on the current agent registry."""
        
        # Generate system information from registry
        agent_descriptions = []
        for name, info in self.agent_registry.items():
            if name != 'CoordinatorAgent':  # Don't describe self
                agent_descriptions.append(f"**{name}** for {info['description'].lower()}")
        
        agents_info = ", ".join(agent_descriptions)
        
        return f"""You are the CoordinatorAgent with ABSOLUTE AUTHORITY over conversation completion in this multi-agent system.

🎯 CRITICAL RESPONSIBILITY: You are the ONLY agent who decides when a conversation is complete. No conversation ends without your explicit final answer.

CORE RESPONSIBILITIES:
1. **Orchestration Authority**: Guide conversations to ensure all necessary information is gathered
2. **Context Leadership**: Provide comprehensive context and background for all responses  
3. **Quality Control**: Ensure all specialist responses fully answer the user's question
4. **Final Answer Authority**: You MUST provide the definitive, complete final answer that satisfies the user

🛑 CONVERSATION COMPLETION RULES:
- A conversation is ONLY complete when YOU provide a comprehensive final answer
- YOU must synthesize all specialist responses into a complete, cohesive response
- YOU decide if more information is needed from specialists
- NEVER let a conversation end with just specialist responses - you must always provide the final synthesis

WHEN TO RESPOND:
✅ **General Knowledge Questions**: Answer directly when no specialist tools are needed
   - "What is artificial intelligence?"
   - "Tell me about the history of computers"  
   - "How does machine learning work?"

✅ **System/Meta Questions**: Answer questions about this multi-agent system itself
   - "What agents are available?"
   - "What can each agent do?"
   - "How does this system work?"
   - "What tools are available?"
   - "Who should I ask about math/database/document questions?"

   For "What agents are available?" specifically, respond with:
   "This multi-agent system includes {len(self.agent_registry)} specialized agents: **CoordinatorAgent** (me) for orchestration and general knowledge, {agents_info}. Each agent has specialized tools to help answer questions in their domain."

✅ **Coordination & Synthesis**: Always provide final synthesis after specialists respond
   - After ADXAgent provides data, YOU interpret and present it to the user
   - After MathAgent calculates, YOU explain the result in context
   - After multiple specialists respond, YOU combine their answers into one coherent response
   - YOU add necessary context, explanations, and conclusions

✅ **Quality Assurance**: Evaluate and improve incomplete responses
   - If a specialist's response seems incomplete, request follow-up information
   - If multiple specialists provide conflicting answers, resolve the conflicts
   - If responses are too technical, translate them for the user

WHEN TO DEFER TO SPECIALISTS (BUT ALWAYS SYNTHESIZE AFTER):
🔄 **Technical Operations** (then YOU provide final answer):
   - Database queries → ADXAgent (then YOU interpret results)
   - Mathematical calculations → MathAgent (then YOU explain results)
   - File operations → DocumentAgent (then YOU summarize outcomes)  
   - Utilities → UtilityAgent (then YOU present results)
   - Company lookups → FictionalCompaniesAgent (then YOU contextualize)

RESPONSE PATTERNS:
1. **Direct Questions**: Answer immediately with comprehensive information
2. **Technical Questions**: Coordinate specialists, then provide synthesized final answer
3. **Multi-part Questions**: Orchestrate multiple specialists, then provide unified response
4. **Follow-up Needed**: Request clarification from specialists, then synthesize complete answer

SYNTHESIS REQUIREMENTS:
- Always create a natural, flowing final answer (not just a list of agent responses)
- Include all relevant information from specialists
- Add helpful context and explanations
- Ensure the user gets a complete, satisfying answer
- Use clear, professional language appropriate for the user

EXAMPLES OF PROPER FINAL ANSWERS:

For "List ADX databases and their purposes":
❌ Wrong: Just let ADXAgent respond
✅ Correct: After ADXAgent lists databases, YOU provide: "Based on the analysis of your Azure Data Explorer instance, here are the available databases and their business purposes: [synthesized explanation with context]"

For "Calculate factorial of 10 and explain when this is useful":
❌ Wrong: Just let MathAgent calculate  
✅ Correct: After MathAgent calculates, YOU provide: "The factorial of 10 is 3,628,800. This calculation is particularly useful in [explain real-world applications and significance]"

For "Find documents about AI and tell me what they contain":
❌ Wrong: Just let DocumentAgent search
✅ Correct: After DocumentAgent searches, YOU provide: "I found several documents about AI in your system. Here's a comprehensive summary of their contents: [synthesized overview with key insights]"

🎯 REMEMBER: You have the final word on every conversation. The user should always receive their complete answer from YOU, not from individual specialists."""
    
    def _create_group_chat(self):
        """Create the group chat for agent coordination with AgentGroupChat."""
        logger.info("💬 Creating AgentGroupChat with agents:")
        
        # Log agents dynamically from registry
        for name, info in self.agent_registry.items():
            emoji = "🎯" if name == "CoordinatorAgent" else "🧮" if name == "MathAgent" else "🔧" if name == "UtilityAgent" else "🔍" if name == "ADXAgent" else "📄" if name == "DocumentAgent" else "🏢"
            logger.info(f"   {emoji} {name} - {info['description']}")
        
        # Create the group chat with enhanced LLM-based termination strategy
        termination_strategy = LLMTerminationStrategy()
        termination_strategy.set_coordinator_agent(self.coordinator_agent)
        
        # Get all agents from registry in a predictable order
        all_agents = [info['agent'] for info in self.agent_registry.values()]
        
        self.group_chat = AgentGroupChat(
            agents=all_agents,
            termination_strategy=termination_strategy
        )
        logger.info("✅ AgentGroupChat created with Enhanced LLMTerminationStrategy")
        logger.info("🧠 Termination strategy supports intelligent orchestration and response synthesis")
        
    async def _select_agents_for_question(self, question: str) -> List[ChatCompletionAgent]:
        """Use the CoordinatorAgent's LLM to select which agents should participate in the conversation and in what order."""
        
        # Generate the agent list dynamically from the registry
        agent_list = []
        examples = []
        
        for i, (name, info) in enumerate(self.agent_registry.items(), 1):
            agent_list.append(f"{i}. {name} - {info['description']}")
            # Add some examples for this agent
            for example in info['examples'][:2]:  # Limit to 2 examples per agent
                examples.append(f'- For "{example}" → ["CoordinatorAgent"' + 
                              (f', "{name}"]' if name != 'CoordinatorAgent' else ']'))
        
        # Create a prompt for agent selection
        selection_prompt = f"""You are an intelligent agent router. Based on the user's question, determine which specialized agents should participate in the conversation and in what order.

AVAILABLE AGENTS:
{chr(10).join(agent_list)}

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
{chr(10).join(examples)}

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
                    
                    # Map agent names to actual agent objects using the registry
                    selected_agents = []
                    for agent_name in selected_agent_names:
                        if agent_name in self.agent_registry:
                            selected_agents.append(self.agent_registry[agent_name]['agent'])
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
            
            # Fallback parsing - use registry keywords to match agents
            fallback_agents = [self.coordinator_agent]  # Always include coordinator
            response_lower = response_content.lower()
            
            for agent_name, info in self.agent_registry.items():
                if agent_name == 'CoordinatorAgent':
                    continue  # Already included
                    
                # Check if any of this agent's keywords appear in the response
                if any(keyword in response_lower for keyword in info['keywords']):
                    agent = info['agent']
                    if agent not in fallback_agents:
                        fallback_agents.append(agent)
                        logger.info(f"   ✅ Added {agent_name} based on keyword match")
            
            logger.info(f"🔄 Fallback agent selection: {[agent.name for agent in fallback_agents]}")
            return fallback_agents
            
        except Exception as e:
            logger.error(f"❌ Error in agent selection: {str(e)}")
            # Ultimate fallback - use all agents from registry
            logger.info("🆘 Using all agents as ultimate fallback")
            return list(self.all_agents.values())
    
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
            
            # OPTIMIZATION: If only CoordinatorAgent is selected, handle as direct general knowledge question
            if len(selected_agents) == 1 and selected_agents[0].name == "CoordinatorAgent":
                logger.info("🚀 FAST PATH: Only CoordinatorAgent selected - handling as direct question")
                logger.info("⚡ Using CoordinatorAgent kernel directly for system questions")
                
                # Use the coordinator's kernel service directly instead of agent.invoke() 
                try:
                    from semantic_kernel.contents import ChatHistory
                    from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
                    
                    # Create a chat history with system instructions and the user's question
                    chat_history = ChatHistory()
                    
                    # Add the coordinator's instructions as system message
                    chat_history.add_system_message(self.coordinator_agent._instructions)
                    chat_history.add_user_message(question)
                    
                    logger.info("🧠 Getting response from CoordinatorAgent kernel with full instructions...")
                    
                    # Get the completion service from the coordinator agent's kernel
                    completion_service = self.coordinator_agent.kernel.get_service()
                    
                    # Create execution settings for focused response
                    settings = OpenAIChatPromptExecutionSettings(
                        max_tokens=1000, 
                        temperature=0.3
                    )
                    
                    # Get response using the service directly with instructions preserved
                    response = await completion_service.get_chat_message_content(
                        chat_history=chat_history,
                        settings=settings
                    )
                    
                    final_response = str(response.content).strip() if response and response.content else ""
                    
                    if final_response and len(final_response) > 50:
                        logger.info(f"✅ FAST PATH SUCCESS: Generated {len(final_response)} characters")
                        logger.info("📊 COMPLETION SUMMARY:")
                        logger.info(f"    📝 Final response length: {len(final_response)} characters")
                        logger.info(f"    🧠 Coordinator response: YES (with full instructions)")
                        logger.info(f"    🎯 Specialist responses: 0 (direct answer)")
                        logger.info(f"    🎭 Total conversation turns: 1 (optimized)")
                        logger.info("============================================================")
                        return final_response
                    else:
                        logger.warning("⚠️ FAST PATH: Coordinator response too short, falling back to group chat")
                        
                except Exception as e:
                    logger.error(f"❌ FAST PATH ERROR: {str(e)}, falling back to group chat")
                
                # If fast path fails, continue with normal group chat processing
                logger.info("🔄 FALLBACK: Proceeding with normal group chat workflow")
            
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
                    # Reduced verbosity - only log response length, not content
                    logger.debug(f"   📄 Content: {content[:200]}{'...' if len(content) > 200 else ''}")
                    
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
                        # ALWAYS capture coordinator responses - let termination strategy decide completion
                        coordinator_response = content  # Always use the latest coordinator response
                        logger.info(f"   🧠 Coordinator response captured (length: {len(content)})")
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
            
            # Enhanced completion logging for debugging
            final_length = len(final_response) if final_response else 0
            has_coordinator = bool(coordinator_response)
            specialist_count = len(specialist_responses)
            
            logger.info(f"📊 COMPLETION SUMMARY:")
            logger.info(f"   📝 Final response length: {final_length} characters")
            logger.info(f"   🧠 Coordinator response: {'YES' if has_coordinator else 'NO'}")
            logger.info(f"   🎯 Specialist responses: {specialist_count}")
            logger.info(f"   🎭 Total conversation turns: {len(responses)}")
            
            if final_length < 50:
                logger.warning(f"⚠️ WARNING: Final response seems short ({final_length} chars) - may be incomplete")
            
            if specialist_count > 0 and not has_coordinator:
                logger.warning(f"⚠️ WARNING: Specialists responded but no coordinator synthesis - potential incomplete answer")
            
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
        
        # PRIORITY: If coordinator provided a substantial final response, use it directly
        if coordinator_response and len(coordinator_response) > 80:
            # Check if coordinator response appears to be synthesizing specialist responses
            synthesis_indicators = [
                "based on", "according to", "the data shows", "the analysis", "the calculation",
                "the query", "the search", "the results", "combining", "together", "overall",
                "in summary", "to summarize", "from the", "using the", "with the"
            ]
            
            response_lower = coordinator_response.lower()
            appears_synthesized = any(indicator in response_lower for indicator in synthesis_indicators)
            
            # If it looks like coordinator already synthesized, return that response
            if appears_synthesized or len(unique_specialist_responses) == 0:
                logger.info("🧠 Using coordinator's synthesized response as final answer")
                return coordinator_response
        
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
