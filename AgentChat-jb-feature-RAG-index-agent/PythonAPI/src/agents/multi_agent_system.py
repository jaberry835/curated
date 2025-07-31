"""Multi-agent system using Semantic Kernel and MCP tools with resilient Azure OpenAI integration."""

import asyncio
import os
import logging
from typing import List, Optional, Dict, Any, Annotated

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.agents import ChatCompletionAgent, AgentGroupChat
from semantic_kernel.agents.strategies.termination.kernel_function_termination_strategy import KernelFunctionTerminationStrategy
from semantic_kernel.agents.strategies.selection.kernel_function_selection_strategy import KernelFunctionSelectionStrategy
from semantic_kernel.contents import ChatMessageContent, AuthorRole
from semantic_kernel.functions import KernelArguments, KernelFunction, kernel_function
from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior
from semantic_kernel.contents.history_reducer.chat_history_truncation_reducer import ChatHistoryTruncationReducer

from src.agents.mcp_client import MCPClient
from src.agents.mcp_functions import MCPFunctionWrapper
from src.config.token_limits import token_config
from src.services.resilient_azure_service import create_resilient_azure_service
from src.services.rag_agent_service import rag_agent_service

# Set up logging for agent conversations
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class MultiAgentSystem:
    """Multi-agent system that coordinates specialized agents using AgentGroupChat with proper Semantic Kernel strategies."""
    
    def __init__(self, azure_openai_api_key: str, azure_openai_endpoint: str, azure_openai_deployment: str):
        """Initialize the multi-agent system with Azure OpenAI configuration."""
        self.azure_openai_api_key = azure_openai_api_key
        self.azure_openai_endpoint = azure_openai_endpoint
        self.azure_openai_deployment = azure_openai_deployment
        
        # MCP Client for external tool connections
        self.mcp_client = MCPClient()
        
        # Function wrapper for tool integration  
        self.function_wrapper = MCPFunctionWrapper(self.mcp_client)
        
        # Initialize kernel for strategy functions
        self.kernel = Kernel()
        
        # Add completion service to kernel for strategy functions
        strategy_service = create_resilient_azure_service(
            service_id="strategy_completion",
            api_key=self.azure_openai_api_key,
            endpoint=self.azure_openai_endpoint,
            deployment_name=self.azure_openai_deployment,
            agent_name="StrategyService",
            max_tokens=4000,
            temperature=0.1
        )
        self.kernel.add_service(strategy_service)
        
        # Initialize agents
        self.coordinator_agent: Optional[ChatCompletionAgent] = None
        self.math_agent: Optional[ChatCompletionAgent] = None
        self.utility_agent: Optional[ChatCompletionAgent] = None
        self.adx_agent: Optional[ChatCompletionAgent] = None
        self.document_agent: Optional[ChatCompletionAgent] = None
        self.fictional_companies_agent: Optional[ChatCompletionAgent] = None
        
        # Enhanced agent registry for dynamic selection and tracking
        self.agent_registry = {}
        
        # Memory service for conversation context with CosmosDB integration
        from src.services.memory_service import memory_service
        from src.services.cosmos_service import cosmos_service
        self.memory_service = memory_service
        
        # Initialize cosmos service connection for memory persistence
        if not self.memory_service.cosmos_service and cosmos_service.is_available():
            self.memory_service.cosmos_service = cosmos_service
            logger.info("🔗 Connected memory service to CosmosDB for chat history persistence")
        elif not cosmos_service.is_available():
            logger.warning("⚠️ CosmosDB not available - memory will be session-only")
        
        logger.info("🚀 Initializing Multi-Agent System with Semantic Kernel strategies...")

    def _create_selection_function(self, dynamic_strategy: str = None) -> KernelFunction:
        """Create a KernelFunction for agent selection strategy with optional dynamic strategy from coordinator."""
        
        # Create the selection function using standard Semantic Kernel KernelFunctionFromPrompt
        from semantic_kernel.functions import KernelFunctionFromPrompt
        from semantic_kernel.prompt_template import PromptTemplateConfig
        
        # Use dynamic strategy if provided by coordinator, otherwise use default
        if dynamic_strategy:
            logger.info(f"🧠 Using coordinator-enhanced selection strategy")
            prompt_template = f"""
Determine which agent should respond next based on the conversation context and question type.

Available agents: {{{{$_agent_}}}}

COORDINATOR'S ANALYSIS AND ROUTING STRATEGY:
{dynamic_strategy}

Use the coordinator's strategy above as your primary guidance for agent selection.

Chat History: {{{{$_history_}}}}

Return ONLY the agent name (e.g., "ADXAgent") with no additional text or explanation.
"""
        else:
            # Default selection strategy for initial setup
            prompt_template = """
Determine which agent should respond next based on the conversation context and question type.

Available agents: {{$_agent_}}

AGENT CAPABILITIES:
- DocumentAgent: File operations, reading document content, extracting data from files (.txt, .csv, .pdf, etc.)
- ADXAgent: Database queries, Azure Data Explorer operations, checking data in tables
- FictionalCompaniesAgent: Company lookups by IP address, device information, fictional company data
- MathAgent: Mathematical calculations, statistical analysis, numerical computations
- UtilityAgent: Hash generation, timestamps, system utilities, formatting operations
- CoordinatorAgent: General questions, synthesis of results, final answers, coordination

INTELLIGENT ROUTING LOGIC:
1. DOCUMENT REFERENCES: If question mentions files (.txt, .csv, documents) or "in the file" → START with DocumentAgent
2. DATABASE OPERATIONS: If mentions tables, IP lookups in database, "check if exists" → ADXAgent
3. COMPANY LOOKUPS: If asks for company info, device info, IP company associations → FictionalCompaniesAgent
4. CALCULATIONS: If asks for math, statistics, numerical analysis → MathAgent
5. UTILITIES: If asks for hashes, timestamps, system info → UtilityAgent
6. SYNTHESIS: After specialists provide data → CoordinatorAgent for final answer

MULTI-STEP WORKFLOW DETECTION:
- Questions with "AND" operations need multiple agents in sequence
- File references (.txt, .csv) should ALWAYS start with DocumentAgent first
- After getting file content, route to appropriate specialist for analysis
- Complex workflows: DocumentAgent → SpecialistAgent → CoordinatorAgent

Chat History: {{$_history_}}

Return ONLY the agent name (e.g., "DocumentAgent") with no additional text or explanation.
"""
        
        config = PromptTemplateConfig(
            template=prompt_template,
            name="selection_strategy",
            description="Selects the most appropriate agent for the conversation"
        )
        
        return KernelFunctionFromPrompt(
            function_name="selection_strategy",
            prompt_template_config=config
        )

    def _create_termination_function(self) -> KernelFunction:
        """Create a KernelFunction for termination strategy following Semantic Kernel patterns."""
        
        # Create the termination function using standard Semantic Kernel KernelFunctionFromPrompt
        from semantic_kernel.functions import KernelFunctionFromPrompt
        from semantic_kernel.prompt_template import PromptTemplateConfig
        
        prompt_template = """
Check if the conversation should end.

End the conversation if:
- The CoordinatorAgent has provided a final answer with "Approved" AND all requested tasks are complete
- The user's question has been fully answered by all relevant specialists
- Maximum turns have been reached

For complex questions requiring multiple agents (like "check file content AND verify in database AND get company info"):
- Only terminate if ALL parts have been completed by the appropriate specialists
- If DocumentAgent got file content but ADXAgent hasn't checked database yet → CONTINUE
- If database verification is mentioned but ADXAgent hasn't executed queries → CONTINUE  
- If company lookup is requested but FictionalCompaniesAgent hasn't provided results → CONTINUE

Current agent: {{$_agent_}}
Chat History: {{$_history_}}

Reply with "TERMINATE" to end or "CONTINUE" to keep going:"""
        
        config = PromptTemplateConfig(
            template=prompt_template,
            name="termination_strategy",
            description="Determines if the conversation should terminate"
        )
        
        return KernelFunctionFromPrompt(
            function_name="termination_strategy",
            prompt_template_config=config
        )

    def _parse_termination_result(self, result):
        """Parse termination function result handling both ChatMessageContent lists and FunctionResult objects."""
        try:
            # Handle FunctionResult object
            if hasattr(result, 'value'):
                content = str(result.value).strip().upper()
                return "TERMINATE" in content
            
            # Handle list of ChatMessageContent objects
            if isinstance(result, list) and len(result) > 0:
                chat_message = result[0]
                if hasattr(chat_message, 'items') and chat_message.items and len(chat_message.items) > 0:
                    content = chat_message.items[0].text.strip().upper()
                    return "TERMINATE" in content
                elif hasattr(chat_message, 'content'):
                    content = chat_message.content.strip().upper()
                    return "TERMINATE" in content
            
            # Handle string result directly
            if isinstance(result, str):
                return "TERMINATE" in result.upper()
            
            # Default to continue
            logger.warning(f"Unknown termination result type: {type(result)}, defaulting to CONTINUE")
            return False
            
        except Exception as e:
            logger.error(f"Error parsing termination result: {e}, defaulting to CONTINUE")
            return False

    def _parse_selection_result(self, result):
        """Parse selection function result and return the actual Agent object."""
        try:
            agent_name = None
            logger.debug(f"🔍 Parsing selection result - Type: {type(result)}")
            
            # Handle FunctionResult object - get the actual content
            if hasattr(result, 'value'):
                value = result.value
                logger.debug(f"🔍 FunctionResult.value type: {type(value)}")
                
                # If value is a list of ChatMessageContent objects, get the first one
                if isinstance(value, list) and len(value) > 0:
                    chat_message = value[0]
                    # Get text from the message items
                    if hasattr(chat_message, 'items') and chat_message.items and len(chat_message.items) > 0:
                        text_item = chat_message.items[0]
                        if hasattr(text_item, 'text'):
                            agent_name = text_item.text.strip()
                            logger.debug(f"🔍 Extracted agent name: '{agent_name}'")
                else:
                    # Direct string value
                    agent_name = str(value).strip()
                    logger.debug(f"🔍 Direct string agent name: '{agent_name}'")
            
            # Handle direct string result
            elif isinstance(result, str):
                agent_name = result.strip()
                logger.debug(f"🔍 String result agent name: '{agent_name}'")
            
            # Clean up and validate agent name
            if agent_name:
                # Remove any extra text, just get the agent name
                agent_name = agent_name.split('\n')[0].split('.')[0].strip()
                
                # Map to the exact same agent objects that were passed to AgentGroupChat
                # This ensures object identity consistency throughout the system
                agent_mapping = {
                    'CoordinatorAgent': self.coordinator_agent,
                    'MathAgent': self.math_agent,
                    'UtilityAgent': self.utility_agent,
                    'ADXAgent': self.adx_agent,
                    'DocumentAgent': self.document_agent,
                    'FictionalCompaniesAgent': self.fictional_companies_agent
                }
                
                if agent_name in agent_mapping and agent_mapping[agent_name] is not None:
                    selected_agent = agent_mapping[agent_name]
                    logger.info(f"🎯 Selection strategy selected '{agent_name}' -> {id(selected_agent)}")
                    return selected_agent
                else:
                    logger.warning(f"❌ Unknown agent name '{agent_name}' or agent not initialized, defaulting to CoordinatorAgent")
                    return self.coordinator_agent
            else:
                logger.warning(f"❌ No agent name extracted from result, defaulting to CoordinatorAgent")
                return self.coordinator_agent
            
        except Exception as e:
            logger.error(f"❌ Error parsing selection result: {e}, defaulting to CoordinatorAgent")
            logger.error(f"Result type: {type(result)}, Result: {result}")
            return self.coordinator_agent

    def _parse_strategy_result(self, result):
        """Parse strategy function result and return the agent name as a string."""
        try:
            logger.debug(f"🔍 Parsing strategy result - Type: {type(result)}")
            
            # Handle FunctionResult object - get the actual content
            if hasattr(result, 'value'):
                value = result.value
                logger.debug(f"🔍 FunctionResult.value type: {type(value)}")
                
                # If value is a list of ChatMessageContent objects, get the first one
                if isinstance(value, list) and len(value) > 0:
                    chat_message = value[0]
                    # Get text from the message items
                    if hasattr(chat_message, 'items') and chat_message.items and len(chat_message.items) > 0:
                        text_item = chat_message.items[0]
                        if hasattr(text_item, 'text'):
                            agent_name = text_item.text.strip()
                            logger.debug(f"🔍 Extracted agent name: '{agent_name}'")
                            return agent_name
                    # If no items, try content directly
                    elif hasattr(chat_message, 'content'):
                        agent_name = str(chat_message.content).strip()
                        logger.debug(f"🔍 Content agent name: '{agent_name}'")
                        return agent_name
                else:
                    # Direct string value
                    agent_name = str(value).strip()
                    logger.debug(f"🔍 Direct string agent name: '{agent_name}'")
                    return agent_name
            
            # Handle direct string result
            elif isinstance(result, str):
                agent_name = result.strip()
                logger.debug(f"🔍 String result agent name: '{agent_name}'")
                return agent_name
            
            # Fallback to string conversion
            else:
                agent_name = str(result).strip()
                logger.debug(f"🔍 Fallback string agent name: '{agent_name}'")
                return agent_name
                
        except Exception as e:
            logger.error(f"❌ Error parsing strategy result: {e}, defaulting to 'CoordinatorAgent'")
            logger.error(f"Result type: {type(result)}, Result: {result}")
            return "CoordinatorAgent"

    async def _get_coordinator_analysis(self, question: str, available_agents: list) -> str:
        """Let the coordinator analyze the question and create a dynamic selection strategy."""
        try:
            agent_names = [agent.name for agent in available_agents]
            
            analysis_prompt = f"""
You are the intelligent coordinator for a multi-agent system. Analyze this user question and create a smart routing strategy for the other agents.

AVAILABLE AGENTS AND THEIR CAPABILITIES:
- DocumentAgent: Read files (.txt, .csv, .pdf), extract content, search documents, file operations
- ADXAgent: Database queries, Azure Data Explorer (KQL), check data in tables, database operations  
- FictionalCompaniesAgent: Company info by IP address, device information, fictional company data
- MathAgent: Mathematical calculations, statistics, numerical analysis, computations
- UtilityAgent: Hash generation, timestamps, system utilities, formatting operations
- CoordinatorAgent: General questions, synthesis, final answers, coordination

USER QUESTION: {question}

AVAILABLE AGENTS FOR THIS QUESTION: {', '.join(agent_names)}

Analyze this question and provide intelligent routing guidance:

1. WORKFLOW ANALYSIS: What steps are needed to answer this question completely?
2. AGENT SEQUENCE: Which agents should be used and in what order?
3. PRIORITY ROUTING: Which agent should go first and why?
4. DEPENDENCIES: Are there dependencies between agents (e.g., need file content before database query)?

Create a selection strategy that will guide the system to route intelligently. Consider:
- If the question mentions files (.txt, .csv, etc.), DocumentAgent should usually go first
- If it's about checking data in databases/tables, ADXAgent handles that
- If it needs company/IP lookups, FictionalCompaniesAgent does that
- If it needs calculations, MathAgent handles math
- If it's multi-step (file THEN database THEN company lookup), plan the sequence

Return your routing strategy as clear guidance for intelligent agent selection.
"""

            # Use the coordinator's service to analyze the question
            completion_service = self.coordinator_agent.kernel.get_service()
            
            if hasattr(completion_service, 'get_chat_message_content'):
                # Using resilient service
                from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
                settings = OpenAIChatPromptExecutionSettings(
                    max_tokens=800,
                    temperature=0.1
                )
                
                response = await completion_service.get_chat_message_content(
                    chat_history=[],
                    settings=settings,
                    messages=[{"role": "user", "content": analysis_prompt}]
                )
                
                strategy = response.content.strip()
                logger.info(f"🧠 Coordinator analysis completed ({len(strategy)} chars)")
                return strategy
            else:
                logger.warning("❌ Could not access coordinator's completion service")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error in coordinator analysis: {e}")
            return None

    async def initialize(self) -> bool:
        """Initialize all agents and setup the group chat."""
        logger.info("🔧 Setting up Multi-Agent System...")
        
        # Connect MCP client first
        logger.info("🔌 Connecting MCP client...")
        mcp_connected = await self.mcp_client.connect()
        if mcp_connected:
            logger.info("✅ MCP client connected successfully")
        else:
            logger.warning("⚠️ MCP client connection failed, agents may have limited functionality")
        
        # Create individual agents
        await self._create_agents()
        
        logger.info("✅ Multi-Agent System initialized successfully")
        return True

    async def _create_agents(self):
        """Create the specialized agents."""
        
        # Math Agent with resilient Azure OpenAI service
        logger.info("🧮 Creating Math Agent with Resilient Azure OpenAI...")
        math_kernel = Kernel()
        math_config = token_config.get_agent_config('MathAgent')
        math_execution_settings = token_config.get_agent_execution_settings('MathAgent')
        
        # Create resilient Azure service instead of basic AzureChatCompletion
        math_service = create_resilient_azure_service(
            service_id="math_completion",
            api_key=self.azure_openai_api_key,
            endpoint=self.azure_openai_endpoint,
            deployment_name=self.azure_openai_deployment,
            agent_name="MathAgent",
            **math_config
        )
        math_kernel.add_service(math_service)
        logger.info(f"🔒 Math Agent configured with max_tokens={math_execution_settings['max_tokens']}, temperature={math_execution_settings['temperature']}")
        logger.info(f"🛡️ Math Agent includes rate limiting, retry policies, and circuit breaker protection")
        
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

COMPLETION PROTOCOL:
- After providing your answer, always end with: "My answer is complete - CoordinatorAgent, please approve"
- This signals that you're done and ready for coordinator review
- Stay silent until specifically asked for more information

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
        
        # Utility Agent with resilient Azure OpenAI service
        logger.info("🔧 Creating Utility Agent with Resilient Azure OpenAI...")
        utility_kernel = Kernel()
        utility_config = token_config.get_agent_config('UtilityAgent')
        utility_execution_settings = token_config.get_agent_execution_settings('UtilityAgent')
        
        # Create resilient Azure service
        utility_service = create_resilient_azure_service(
            service_id="utility_completion",
            api_key=self.azure_openai_api_key,
            endpoint=self.azure_openai_endpoint,
            deployment_name=self.azure_openai_deployment,
            agent_name="UtilityAgent",
            **utility_config
        )
        logger.info(f"🔒 Utility Agent configured with max_tokens={utility_execution_settings['max_tokens']}, temperature={utility_execution_settings['temperature']}")
        logger.info(f"🛡️ Utility Agent includes rate limiting, retry policies, and circuit breaker protection")
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

COMPLETION PROTOCOL:
- After providing your answer, always end with: "My answer is complete - CoordinatorAgent, please approve"
- This signals that you're done and ready for coordinator review
- Stay silent until specifically asked for more information

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
        
        # ADX Agent with resilient Azure OpenAI service
        logger.info("🔍 Creating ADX Agent with Resilient Azure OpenAI...")
        adx_kernel = Kernel()
        adx_config = token_config.get_agent_config('ADXAgent')
        adx_execution_settings = token_config.get_agent_execution_settings('ADXAgent')
        
        # Create resilient Azure service
        adx_service = create_resilient_azure_service(
            service_id="adx_completion",
            api_key=self.azure_openai_api_key,
            endpoint=self.azure_openai_endpoint,
            deployment_name=self.azure_openai_deployment,
            agent_name="ADXAgent",
            **adx_config
        )
        logger.info(f"🔒 ADX Agent configured with max_tokens={adx_execution_settings['max_tokens']}, temperature={adx_execution_settings['temperature']}")
        logger.info(f"🛡️ ADX Agent includes rate limiting, retry policies, and circuit breaker protection")
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

🚨 **CRITICAL KQL SYNTAX - CORRECTED BASED ON ACTUAL KQL FUNCTIONS:**

**CORRECT KQL STRING TRUNCATION AND OPERATIONS:**
```kql
// String truncation (substring DOES exist in KQL):
| project ip_address, location, details_summary = substring(details, 0, 100)

// String length (use strlen, not len):
| project details_length = strlen(details)
| summarize max_details = max(details_length)

// String comparison and search:
| where details contains "error"          // Search within string
| where details startswith "ERROR:"       // Starts with pattern
| where details endswith ".log"           // Ends with pattern
| where details has "network"             // Contains whole term

// Complete query pattern with truncation:
TableName
| where column_name == "value"
| project column1, column2, details_summary = substring(details, 0, 100)
| take 50
```

**CRITICAL: KQL ALIAS SYNTAX (This was the main error!):**
- ✅ CORRECT: `details_summary = substring(details, 0, 100)`
- ❌ WRONG: `substring(details, 0, 100) as details_summary`

**KEY KQL FUNCTIONS:**
- `substring(string, start, length)` - Extract substring starting at position
- `strlen(string)` - Get string length
- `contains`, `startswith`, `endswith`, `has` - String searching

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

**STEP 3: MANDATORY FIELD SIZE ANALYSIS - NO EXCEPTIONS**
- After getting schema, you MUST ALWAYS run field size analysis for ALL string columns
- This step is REQUIRED even if columns look simple - no exceptions or shortcuts allowed
- Use this exact pattern for EVERY table: `TableName | take 5 | project column1_length = strlen(column1), column2_length = strlen(column2) | summarize max_column1 = max(column1_length), max_column2 = max(column2_length)`
- Field size analysis is MANDATORY before any data query - this cannot be skipped

**STEP 4: EXECUTE USER'S QUERY WITH APPROPRIATE HANDLING**
- After field size analysis, IMMEDIATELY execute the user's actual query with appropriate truncation
- DO NOT STOP after schema or field analysis - the user needs the actual data results
- Apply truncation only if field size analysis shows large text fields
- If query fails, re-check schema - don't guess alternatives

🚫 **DO NOT GET STUCK AT SCHEMA DISCOVERY OR SKIP FIELD SIZE ANALYSIS!**
Schema discovery → Field size analysis → Query execution. All three steps are mandatory.
The user asked for data, not just table information!

� **CRITICAL NAMING CONVENTIONS:**
- Table names: Usually lowercase (e.g., "scans", "users", "events")
- Column names: Often snake_case (e.g., "ip_address", "user_name", "created_date") 
- BUT schemas vary! Some use camelCase, PascalCase, or other conventions
- The ONLY way to know is to check the schema first!

📝 **REQUIRED WORKFLOW EXAMPLE - ALL STEPS MANDATORY:**
For ANY query involving tables, you MUST complete ALL steps:

```
User: "Find IP X.X.X.X in the [table_name] table"

Step 1: adx_list_tables("[database_name]")  // Confirm table exists
Step 2: adx_describe_table("[database_name]", "[table_name]")  // Get exact column names and types
Step 3: **MANDATORY FIELD SIZE CHECK** - Cannot be skipped even for simple tables:
   [table_name] | take 5 | project ip_address_length = strlen(ip_address), location_length = strlen(location)
   | summarize max_ip = max(ip_address_length), max_location = max(location_length)
Step 4: **IMMEDIATELY** construct and execute query using ACTUAL schema column names:
   [table_name]
   | where [actual_ip_column] == "X.X.X.X"  
   | project [actual_columns_from_schema]
   | take 50
Step 5: Only add substring() truncation IF field size analysis shows large text fields
Step 6: Communicate results based on what was actually found
```

🚨 **CRITICAL: COMPLETE ALL STEPS - FIELD SIZE CHECK IS NOT OPTIONAL!**
- Step 3 (field size check) is MANDATORY for every single table query
- Even tables with simple columns like ip_address, location require field size analysis
- This step cannot be skipped, assumed, or bypassed
- After field size check, IMMEDIATELY proceed to execute the actual query
- DO NOT get stuck in schema checking - complete the workflow and get the data!

⚡ **TOKEN MANAGEMENT - CRITICAL FOR ALL QUERIES:**

**ALWAYS START CONSERVATIVE:**
- Default limit: | take 50 for exploratory queries
- Essential columns only: Use | project to limit columns to what user needs
- Recent data first: Add time filters like | where timestamp >= ago(7d)

**HANDLE LARGE TEXT FIELDS PROACTIVELY - ONLY WHEN THEY EXIST:**
- Check schema first to see what columns exist
- Only apply substring() truncation to columns that actually exist AND are text/string type
- Pattern: `[field_name]_summary = substring([field_name], 0, 100)` for truncation
- If no large text fields exist, just project the actual columns
- Always mention truncation to users: "I've truncated text fields for token efficiency"
- Focus on essential columns based on actual schema, not assumptions

**INTELLIGENT FIELD SIZE CHECKING - MANDATORY AFTER SCHEMA:**
After EVERY schema check, IMMEDIATELY analyze field sizes FOR STRING/TEXT FIELDS THAT EXIST:

1. **ALWAYS run field size check - ONLY for text/string columns that exist:**
   ```kql
   TableName 
   | take 5
   | project [text_column1]_length = strlen([text_column1]), [text_column2]_length = strlen([text_column2])
   | summarize max_[text_column1] = max([text_column1]_length), max_[text_column2] = max([text_column2]_length)
   ```

2. **Based on field size analysis, choose strategy:**
   - **Small fields (<200 chars)**: Include full content
   - **Medium fields (200-1000 chars)**: Truncate to 150 chars using `substring([field], 0, 150)`
   - **Large fields (>1000 chars)**: Truncate to 100 chars using `substring([field], 0, 100)`
   - **Non-text fields**: Include as-is (numbers, dates, etc.)

3. **IMMEDIATELY execute the user's query with appropriate handling:**
   ```kql
   // Use actual column names from schema, apply truncation only where needed
   TableName 
   | where [actual_filter_column] == "criteria"
   | project [required_columns], [large_text_field]_summary = substring([large_text_field], 0, 100)
   | take 50
   ```

🚨 **WORKFLOW ENFORCEMENT - ALL STEPS MANDATORY:**
1. Schema check → 2. **MANDATORY** Field size check → 3. Execute query → 4. Return results
**NEVER SKIP STEP 2** - Field size analysis is required for EVERY query, even simple tables!
**DO NOT STOP** at any intermediate step! The user needs the actual data!

**FIELD SIZE CHECK IS MANDATORY - NO EXCEPTIONS:**
Even if the table looks simple with basic string columns, you MUST run the field size analysis:
```kql
TableName | take 5 | project [all_string_columns]_length = strlen([column_name]) | summarize max_[column] = max([column]_length)
```
This step cannot be skipped, shortened, or assumed unnecessary. It must be done for every table query.

**ADAPTIVE CHUNKING STRATEGIES:**

**When field analysis shows large content:**
1. **Start with overview**: Get counts and categories first
2. **Sample representative data**: Use `sample()` or `take()` with diverse criteria
3. **Offer drill-down**: Let user specify what details they need
4. **Use progressive refinement**: Start broad, then narrow based on user interest

**Self-Chunking Communication Pattern:**
"I detected that [field_name] contains very large text (up to [X] characters). I'll start with a summary view and can provide more detail on specific records if needed."

**Example Adaptive Approach:**
```
User: "Show me error logs from today"

Step 1: Check field sizes
error_logs | take 5 | project strlen(error_message), strlen(stack_trace)

Step 2: If large fields detected, inform user and chunk:
"I found error logs with very detailed messages (up to 5000+ characters). I'll show you a summary view first:

error_logs 
| where timestamp >= ago(1d)
| project timestamp, error_code, severity, error_summary = substring(error_message, 0, 150)
| take 50

Would you like me to show full details for specific errors, or filter by error type?"
```

**TOKEN-CONSCIOUS QUERY STRUCTURE:**
```kql
TableName
| where timestamp >= ago(7d)              // Recent data first
| project essential_cols, details_summary = substring(large_text_field, 0, 100)
| take 50                                 // Conservative limit
```

**QUERY PATTERNS BY USER INTENT:**
- Exploration ("Show me...", "What are..."): | take 30-50 with key columns and truncated text fields
- Investigation ("Find errors...", "Show problems..."): | take 100 with focused where clauses and truncated large fields
- Analysis ("How many...", "What's the trend..."): Use summarize when possible instead of raw data

**PROGRESSIVE REFINEMENT APPROACH:**
1. Start with focused query (50 rows, essential columns, truncated text fields)
2. Explain what you retrieved and truncation applied
3. Offer expansions: "Need more rows/full text for specific records/different fields?"

**INTELLIGENT CHUNKING DECISION TREE:**

**Step 1: Always assess data size first**
```kql
// Quick size check query
TableName 
| take 5
| extend text_field_size = strlen(text_field)
| summarize max_size = max(text_field_size), avg_size = avg(text_field_size)
```

**Step 2: Choose strategy based on assessment**
- **If max_size < 200**: Proceed normally with full fields
- **If max_size 200-1000**: Use `substring(field, 0, 150)` for truncation
- **If max_size > 1000**: Use `substring(field, 0, 100)` for aggressive truncation

**Step 3: Implement appropriate chunking**

**CHUNKING STRATEGIES BY SCENARIO:**

**Large Text Content (>1000 chars per field):**
```kql
// Show structure first, content second
TableName
| summarize record_count = count(), 
           categories = dcount(category_field),
           date_range = strcat(min(timestamp), " to ", max(timestamp))
| extend summary = "Large dataset detected - showing overview first"

// Then show sample with truncated content
TableName 
| sample 20  // Random sample for variety
| project timestamp, category, text_preview = substring(large_text_field, 0, 200)
```

**Many Rows (>100 potential results):**
```kql
// Time-based chunking
TableName
| where timestamp >= ago(6h)  // Recent subset
| project essential_columns, text_summary = substring(large_field, 0, 100)
| take 50
// Offer: "This shows last 6 hours. Need earlier data or full text for specific records?"
```

**Multiple Large Fields:**
```kql
// Progressive disclosure
TableName
| project timestamp, id, category, 
         field1_preview = substring(field1, 0, 100),
         field1_size = strlen(field1),
         field2_size = strlen(field2)
| take 30
// Offer: "Field sizes shown. Need full content for specific records or specific fields?"
```

**COMMUNICATION ABOUT LIMITS:**
Always explain your token-conscious approach:
- "I'll start with a focused query (50 recent records, key columns)"
- "I've truncated large text fields to 100 chars for token efficiency"
- "The results show [insights]. Need full text for specific records?"

**SIZE-AWARE COMMUNICATION PATTERNS:**

**When detecting large fields:**
"I analyzed the data structure and found [field_name] contains very large content (up to [X] characters per record). I'm showing truncated previews (100 chars) to stay within token limits. Let me know if you need full content for specific records."

**When chunking by time:**
"This table has extensive historical data. I'm showing the most recent [time period] to start. Would you like to expand to [earlier period] or focus on specific dates?"

**When chunking by category:**
"I found [X] different categories in this data. Here's an overview of each category. Would you like detailed records for any specific category?"

**When offering drill-down:**
"This summary shows the key patterns. I can provide detailed records for:
• Specific time ranges
• Particular categories or types  
• Individual records by ID
• Full text content for selected items (untruncated)
What would be most helpful?"

**Example Size-Aware Responses:**

*User: "Show me all error logs"*
**Response:** "I'll check the error logs structure first... 

*[runs size check query]*

I found error logs with detailed stack traces (up to 3,000+ characters each). To manage token usage effectively, here's a summary view:

*[shows results with truncated text fields using substring()]*

The data shows [key insights]. Would you like me to:
• Show full details for specific errors (untruncated)
• Filter by error type or severity  
• Focus on a particular time range
• Get complete stack traces for selected records?"

🚫 **NEVER DO THIS:**
- `SCANS | where IPAddress == "1.2.3.4"` (guessing table or column names)
- `Scans | where IP_Address == "1.2.3.4"` (assuming case or format)
- Any query without first checking schema
- Applying substring() to columns that don't exist
- Assuming fields like "details" exist in every table
- Large queries without token considerations (no limits, no projections)
- Returning large text fields without checking if truncation is needed

✅ **ALWAYS DO THIS:**
1. Check schema with adx_describe_table() to see what columns actually exist
2. Use exact names and types from schema results
3. Only apply substring() truncation to text fields that actually exist and are large
4. Construct queries based on actual schema, not assumptions
5. Include appropriate limits and projections for token management
6. Explain your approach to users based on actual data found

🔧 **ERROR HANDLING:**
If you get "Failed to resolve table or column":
1. You skipped schema checking - go back to Step 1
2. Re-run adx_describe_table() to get correct names
3. Do NOT try multiple variations - use schema results only

If you get "Syntax error" in KQL:
1. Check you're using correct alias syntax: `new_name = expression` NOT `expression as new_name`
2. Verify exact column names from schema results
3. Use `substring(field, start, length)` for string truncation - this DOES exist in KQL
4. Use `strlen(field)` for string length - NOT `len(field)`
5. For complex queries, break them into simpler parts to isolate the syntax error

COLLABORATION APPROACH:
- Handle ALL database/ADX parts of questions yourself
- After getting data, coordinate with other agents if needed
- Always get the data first using proper schema workflow

COMPLETION PROTOCOL:
- After providing your query results, always end with: "My answer is complete - CoordinatorAgent, please approve"
- This signals that you're done and ready for coordinator review
- Stay silent until specifically asked for more information
- DO NOT call any other agent functions after providing your data results
- Your job is complete once you've executed the query and shown the results
- The CoordinatorAgent will handle final synthesis and user presentation

EXAMPLES OF PROPER RESPONSES:
❌ BAD: "Let me query the SCANS table..." (guessing table name)
❌ BAD: "I found the scans table with columns ip_address, location" (stopping at schema)
❌ BAD: Trying to use substring() on columns that don't exist like "details"
✅ GOOD: "Let me first check what tables are available, then examine the actual schema, and construct queries using the exact column names found..."
✅ GOOD: "Based on the schema, this table has columns: [actual columns]. I'll query using these exact names."
✅ GOOD: "The table has only basic columns with no large text fields, so no truncation is needed."

**EXECUTION COMMITMENT:**
- After schema discovery, you MUST proceed to query execution using the ACTUAL column names found
- Adapt your queries to match the real schema, not hardcoded examples
- Only apply field size checking and truncation to text columns that actually exist
- The user wants DATA based on the actual table structure, not assumptions
- Complete the full workflow using real schema information

REMEMBER: Schema first, then adapt field handling to ACTUAL columns found, then EXECUTE THE QUERY using the real schema structure!
""",
            function_choice_behavior=FunctionChoiceBehavior.Auto()
        )
        logger.info("✅ ADX Agent created successfully")
        
        # Document Agent with resilient Azure OpenAI service
        logger.info("📄 Creating Document Agent with Resilient Azure OpenAI...")
        document_kernel = Kernel()
        document_config = token_config.get_agent_config('DocumentAgent')
        document_execution_settings = token_config.get_agent_execution_settings('DocumentAgent')
        
        # Create resilient Azure service
        document_service = create_resilient_azure_service(
            service_id="document_completion",
            api_key=self.azure_openai_api_key,
            endpoint=self.azure_openai_endpoint,
            deployment_name=self.azure_openai_deployment,
            agent_name="DocumentAgent",
            **document_config
        )
        logger.info(f"🔒 Document Agent configured with max_tokens={document_execution_settings['max_tokens']}, temperature={document_execution_settings['temperature']}")
        logger.info(f"🛡️ Document Agent includes rate limiting, retry policies, and circuit breaker protection")
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
- User refers to documents contextually ("that document", "the file", "summarize it")

NEVER RESPOND TO:
- Mathematical calculations (let MathAgent handle these)
- ADX/database questions (let ADXAgent handle these)
- Hash generation or timestamps (let UtilityAgent handle these)
- General knowledge questions (let CoordinatorAgent handle these)
- Questions that don't involve document operations

📄 **DOCUMENT CONTEXT AWARENESS:**
When the CoordinatorAgent provides document context (available documents in session), use that information to resolve contextual references:

CONTEXTUAL DOCUMENT HANDLING:
- If user says "summarize that document" and there's only one document in session → automatically use that document
- If user says "the file I uploaded" → use the most recently uploaded document  
- If user says "analyze the PDF" and there's only one PDF → use that PDF
- If multiple matches possible → ask CoordinatorAgent for clarification

ENHANCED WORKFLOW:
1. Check if CoordinatorAgent provided session document context
2. If contextual reference + single matching document → proceed directly
3. If contextual reference + multiple matches → ask for clarification
4. If explicit filename → search as normal
5. Always extract documentId from search results before using get_document_content_summary

PRIORITY ORDER:
1. Session context documents (when provided by CoordinatorAgent)
2. Search results (for explicit filenames)
3. Clarification request (when ambiguous)

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

COMPLETION PROTOCOL:
- After providing your answer, always end with: "My answer is complete - CoordinatorAgent, please approve"
- This signals that you're done and ready for coordinator review
- Stay silent until specifically asked for more information

EXAMPLES OF WHEN TO RESPOND:
- "List all documents in storage" ✅
- "Search for documents about Python" ✅
- "Delete the file named example.pdf" ✅
- "Get the content summary of document123.txt" ✅
- "DocumentAgent, show me available files" ✅
- "Can you summarize that document?" ✅ (when document context is provided)
- "What's in the file I uploaded?" ✅ (when document context is provided)

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

CONTEXTUAL REFERENCE WORKFLOW EXAMPLE:
1. User asks: "Can you summarize that document?"
2. Check if CoordinatorAgent provided document context
3. If only one document in context: "I see you're referring to [filename]. Let me get that for you."
4. Use the documentId from the context to get content: get_document_content_summary("[documentId]")
5. If multiple documents: "I see several documents in this session. Which one would you like me to summarize: [list files]?"
6. If NO session documents but contextual reference detected: Search for recent documents using list_documents() or search_documents() to find what the user might be referring to

CONTEXTUAL REFERENCE HANDLING WITHOUT SESSION CONTEXT:
- If user makes contextual reference ("that document", "the file", etc.) but no session documents are provided
- Use list_documents() to get available documents
- If only one document exists, assume that's what they're referring to
- If multiple documents exist, ask for clarification: "I found several documents. Which one would you like me to work with?"
- Always try to be helpful and proactive in finding the document they're referring to

EXAMPLES OF WHEN TO STAY SILENT:
- "Calculate 10 factorial" ❌ (Math question)
- "List databases in ADX" ❌ (ADX question) 
- "Generate a hash" ❌ (Utility question)
- "What is machine learning?" ❌ (General knowledge)
- Questions without document context ❌

Remember: You manage documents, files, and content storage operations with contextual awareness.
""",
            function_choice_behavior=FunctionChoiceBehavior.Auto()
        )
        logger.info("✅ Document Agent created successfully")
        
        # Fictional Companies Agent with resilient Azure OpenAI service
        logger.info("🏢 Creating Fictional Companies Agent with Resilient Azure OpenAI...")
        fictional_companies_kernel = Kernel()
        fictional_companies_config = token_config.get_agent_config('FictionalCompaniesAgent')
        fictional_companies_execution_settings = token_config.get_agent_execution_settings('FictionalCompaniesAgent')
        
        # Create resilient Azure service
        fictional_companies_service = create_resilient_azure_service(
            service_id="fictional_companies_completion",
            api_key=self.azure_openai_api_key,
            endpoint=self.azure_openai_endpoint,
            deployment_name=self.azure_openai_deployment,
            agent_name="FictionalCompaniesAgent",
            **fictional_companies_config
        )
        logger.info(f"🔒 Fictional Companies Agent configured with max_tokens={fictional_companies_execution_settings['max_tokens']}, temperature={fictional_companies_execution_settings['temperature']}")
        logger.info(f"🛡️ Fictional Companies Agent includes rate limiting, retry policies, and circuit breaker protection")
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

COMPLETION PROTOCOL:
- After providing your answer, always end with: "My answer is complete - CoordinatorAgent, please approve"
- This signals that you're done and ready for coordinator review
- Stay silent until specifically asked for more information

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
        
        # Coordinator Agent with enhanced orchestration capabilities and resilient Azure OpenAI service
        logger.info("🎯 Creating Coordinator Agent with Resilient Azure OpenAI...")
        coordinator_kernel = Kernel()
        coordinator_config = token_config.get_agent_config('CoordinatorAgent')
        coordinator_execution_settings = token_config.get_agent_execution_settings('CoordinatorAgent')
        
        # Create resilient Azure service
        coordinator_service = create_resilient_azure_service(
            service_id="coordinator_completion",
            api_key=self.azure_openai_api_key,
            endpoint=self.azure_openai_endpoint,
            deployment_name=self.azure_openai_deployment,
            agent_name="CoordinatorAgent",
            **coordinator_config
        )
        logger.info(f"🔒 Coordinator Agent configured with max_tokens={coordinator_execution_settings['max_tokens']}, temperature={coordinator_execution_settings['temperature']}")
        logger.info(f"🛡️ Coordinator Agent includes rate limiting, retry policies, and circuit breaker protection")
        coordinator_kernel.add_service(coordinator_service)
        
        # Add the system info function to the coordinator kernel
        # COMMENTED OUT: Function calling capabilities can cause tool call context issues in AgentGroupChat
        # from semantic_kernel.functions import kernel_function
        
        # @kernel_function(
        #     name="get_available_agents",
        #     description="Get information about all available agents in the system"
        # )
        # def get_available_agents() -> str:
        #     """Get a formatted string of available agents and their capabilities."""
        #     if not self.agent_registry:
        #         return "Agent registry not yet initialized."
        #     
        #     info_lines = [f"This multi-agent system includes {len(self.agent_registry)} specialized agents:"]
        #     for name, info in self.agent_registry.items():
        #         if name == 'CoordinatorAgent':
        #             info_lines.append(f"• **{name}** (orchestration) - {info['description']}")
        #         else:
        #             info_lines.append(f"• **{name}** - {info['description']}")
        #     
        #     info_lines.append("\nEach agent has specialized tools to help answer questions in their domain.")
        #     return "\n".join(info_lines)
        
        # @kernel_function(
        #     name="get_agent_capabilities",
        #     description="Get detailed capabilities and examples for each agent"
        # )
        # def get_agent_capabilities() -> str:
        #     """Get detailed capabilities and examples for each agent."""
        #     if not self.agent_registry:
        #         return "Agent registry not yet initialized."
        #     
        #     capability_lines = ["Here are the detailed capabilities of each agent:"]
        #     for name, info in self.agent_registry.items():
        #         capability_lines.append(f"\n**{name}**:")
        #         capability_lines.append(f"  - {info['description']}")
        #         if info.get('examples'):
        #             capability_lines.append("  - Examples:")
        #             for example in info['examples']:
        #                 capability_lines.append(f"    • {example}")
        #     
        #     return "\n".join(capability_lines)
        
        # Add these functions to the coordinator's kernel
        # COMMENTED OUT: Disabling function registration to avoid tool call context issues
        # coordinator_kernel.add_function("SystemTools", get_available_agents)
        # coordinator_kernel.add_function("SystemTools", get_agent_capabilities)
        
        self.coordinator_agent = ChatCompletionAgent(
            service=coordinator_service,
            kernel=coordinator_kernel,
            name="CoordinatorAgent",
            instructions="PLACEHOLDER - Will be updated dynamically after registry is built",
            function_choice_behavior=FunctionChoiceBehavior.Auto()  # Changed back to Auto() to avoid Required function calls
        )
        logger.info("✅ Coordinator Agent created successfully")
        
        # Build the agent registry with metadata for dynamic agent selection and discovery
        await self._build_agent_registry()
        
        # Update coordinator instructions with dynamic agent information
        self._update_coordinator_instructions()
    
    async def _build_agent_registry(self):
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
        
        # Add RAG agents dynamically
        try:
            rag_agents = rag_agent_service.get_all_agents()
            logger.info(f"🔍 Found {len(rag_agents)} RAG agents to add to registry")
            
            for dataset_name, rag_agent in rag_agents.items():
                # Create Semantic Kernel ChatCompletionAgent wrapper for the RAG agent
                rag_sk_agent = await self._create_rag_semantic_kernel_agent(dataset_name, rag_agent)
                
                if rag_sk_agent:
                    agent_key = f"RAG_{dataset_name.capitalize()}Agent"
                    
                    # Create keywords from dataset name and description
                    keywords = [
                        dataset_name.lower(),
                        rag_agent.dataset_config.display_name.lower(),
                        'rag', 'search', 'dataset', 'knowledge'
                    ]
                    
                    # Add words from description
                    desc_words = rag_agent.dataset_config.description.lower().split()
                    keywords.extend([word.strip('.,!?()[]{}') for word in desc_words if len(word) > 3])
                    
                    self.agent_registry[agent_key] = {
                        'agent': rag_sk_agent,  # Use the Semantic Kernel agent wrapper
                        'description': f'RAG dataset agent for {rag_agent.dataset_config.display_name}: {rag_agent.dataset_config.description}',
                        'keywords': list(set(keywords)),  # Remove duplicates
                        'examples': [
                            f'Search {rag_agent.dataset_config.display_name} dataset',
                            f'What do you know about {rag_agent.dataset_config.display_name}?',
                            f'Tell me about {dataset_name}',
                            f'Query {dataset_name} for information about...'
                        ],
                        'dataset_name': dataset_name,
                        'is_rag_agent': True,
                        'rag_agent_impl': rag_agent  # Keep reference to original RAG agent
                    }
                    
                    logger.info(f"✅ Added RAG agent to registry: {agent_key} - {rag_agent.dataset_config.display_name}")
            
            if rag_agents:
                logger.info(f"🤖 Added {len(rag_agents)} RAG agents to registry")
        
        except Exception as e:
            logger.error(f"❌ Error adding RAG agents to registry: {e}")
        
        # Update the all_agents mapping with the actual agent objects
        logger.info(f"✅ Agent registry built with {len(self.agent_registry)} agents")
        for name, info in self.agent_registry.items():
            logger.info(f"   📋 {name}: {info['description']}")
    
    async def _create_rag_semantic_kernel_agent(self, dataset_name: str, rag_agent) -> Optional[ChatCompletionAgent]:
        """Create a Semantic Kernel ChatCompletionAgent wrapper for a RAG agent."""
        try:
            agent_name = f"RAG_{dataset_name.capitalize()}Agent"
            
            # Create a kernel for the RAG agent
            rag_kernel = Kernel()
            
            # Create a resilient Azure service for the RAG agent
            rag_service = create_resilient_azure_service(
                service_id=f"rag_{dataset_name}_completion",
                api_key=self.azure_openai_api_key,
                endpoint=self.azure_openai_endpoint,
                deployment_name=self.azure_openai_deployment,
                agent_name=agent_name,
                max_tokens=2000,
                temperature=0.3
            )
            
            rag_kernel.add_service(rag_service)
            
            # Create custom RAG search function for this agent
            from semantic_kernel.functions import kernel_function
            
            @kernel_function(
                name=f"search_{dataset_name}_dataset",
                description=f"Search the {rag_agent.dataset_config.display_name} dataset for relevant information"
            )
            async def search_rag_dataset(query: str) -> str:
                """Search the RAG dataset and return results."""
                try:
                    result = await rag_agent.process_query(query)
                    if result.get("success", False):
                        return result.get("response", "No response generated")
                    else:
                        return f"Search failed: {result.get('error', 'Unknown error')}"
                except Exception as e:
                    return f"Error searching {dataset_name} dataset: {str(e)}"
            
            # Add the search function to the kernel
            rag_kernel.add_function("RAGTools", search_rag_dataset)
            
            # Create instructions for the RAG agent
            instructions = f"""You are the {agent_name} specializing in the {rag_agent.dataset_config.display_name} dataset.

DATASET INFORMATION:
- Name: {rag_agent.dataset_config.display_name}
- Description: {rag_agent.dataset_config.description}
- Index: {rag_agent.dataset_config.azure_search_index}

STRICT RESPONSE CRITERIA - Only respond when:
- Questions specifically mention "{dataset_name.lower()}" or "{rag_agent.dataset_config.display_name.lower()}"
- Someone asks you directly by name: "{agent_name}, please..."
- Questions are about topics related to: {rag_agent.dataset_config.description}
- Someone asks to "search {dataset_name}" or "query {dataset_name}"

NEVER RESPOND TO:
- General questions unrelated to your dataset
- Questions about other datasets or agents
- Mathematical calculations (let MathAgent handle)
- Database queries (let ADXAgent handle)
- Document operations outside your dataset (let DocumentAgent handle)

RESPONSE PROTOCOL:
1. Use your search_{dataset_name}_dataset function to find relevant information
2. Provide comprehensive answers based on the search results
3. If no relevant information is found, clearly state this
4. Always end with "My answer is complete - CoordinatorAgent, please approve"

COLLABORATION RULES:
- If another agent asks you to search your dataset, respond immediately
- Focus only on information from the {rag_agent.dataset_config.display_name} dataset
- Be thorough but concise in your responses
- Cite relevant sources when possible"""
            
            # Create the ChatCompletionAgent
            sk_agent = ChatCompletionAgent(
                service=rag_service,
                kernel=rag_kernel,
                name=agent_name,
                instructions=instructions,
                function_choice_behavior=FunctionChoiceBehavior.Auto()
            )
            
            logger.info(f"✅ Created Semantic Kernel wrapper for RAG agent: {agent_name}")
            return sk_agent
            
        except Exception as e:
            logger.error(f"❌ Failed to create Semantic Kernel agent for {dataset_name}: {e}")
            return None
    
    def _update_coordinator_instructions(self):
        """Update the coordinator agent's instructions with dynamic agent information."""
        logger.info("🔄 Updating CoordinatorAgent instructions with dynamic agent information...")
        
        # Generate new instructions
        new_instructions = self._generate_coordinator_instructions()
        
        # Update the coordinator agent's instructions using the proper attribute
        self.coordinator_agent._instructions = new_instructions
        
        # Also try setting the instructions property if it exists
        if hasattr(self.coordinator_agent, 'instructions'):
            self.coordinator_agent.instructions = new_instructions
            
        logger.info("✅ CoordinatorAgent instructions updated with current agent registry")
        logger.info(f"📝 Instructions length: {len(new_instructions)} characters")
        logger.info(f"🔍 Instructions preview: {new_instructions[:200]}...")
    
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
        agent_count = len(self.agent_registry)
        
        for name, info in self.agent_registry.items():
            if name != 'CoordinatorAgent':  # Don't describe self
                agent_descriptions.append(f"**{name}** for {info['description'].lower()}")
        
        agents_info = ", ".join(agent_descriptions)
        
        return f"""You are the CoordinatorAgent with authority to approve specialist answers.

📄 **DOCUMENT CONTEXT AWARENESS:**
When users refer to documents contextually (e.g., "that document", "the file I uploaded", "summarize it"), you have access to the session's uploaded documents. 

CONTEXTUAL DOCUMENT REFERENCES:
- "summarize that document" → Check recent uploads, use the most recent if only one
- "what's in the file I uploaded" → Reference the current session's documents
- "analyze the document" → Look at available documents in session context
- "tell me about that PDF" → Find the PDF in current session

DOCUMENT COORDINATION WORKFLOW:
1. When user references documents contextually, first identify which document they mean
2. If only one document in session, assume that's the target
3. If multiple documents, ask for clarification OR use the most recently uploaded
4. Then coordinate with DocumentAgent using the specific document information

For contextual document requests:
- "DocumentAgent, please search for and summarize [filename from session context]"
- "DocumentAgent, the user is referring to [specific document], please retrieve its content"

APPROVAL PROTOCOL:
1. When specialists provide answers and ask for approval, review their work
2. If the answer fully satisfies the user's question, respond with:
   "Approved - [provide final synthesized answer to user]"
3. If more information is needed, ask the appropriate specialist for clarification
4. Always use the word "Approved" when you're satisfied with the complete answer

🚨 CRITICAL: COMPLETION SIGNAL HANDLING
When a specialist says "My answer is complete - CoordinatorAgent, please approve":
- This means they have successfully provided all the data/results
- You should IMMEDIATELY respond with "Approved - [final answer]"
- DO NOT try to call additional functions or ask for more data
- The specialist has already done their job completely

⚠️ FUNCTION CALLING RULES - ABSOLUTELY CRITICAL:
- NEVER EVER try to call agent functions directly
- Agent names (ADXAgent, FictionalCompaniesAgent, MathAgent, etc.) are NOT functions
- Agents are conversation participants, not callable functions
- If you try to call ADXAgent() or any agent name as a function, it will FAIL
- Your job is to coordinate through natural language, not function calls
- Only use your own available functions: get_available_agents() and get_agent_capabilities()
- NEVER use function call syntax like AgentName() - this will always error

🚫 **ABSOLUTELY FORBIDDEN - THESE WILL ALWAYS FAIL:**
- ADXAgent() ❌ (Function not found error) 
- MathAgent() ❌ (Function not found error)
- UtilityAgent() ❌ (Function not found error) 
- DocumentAgent() ❌ (Function not found error)
- FictionalCompaniesAgent() ❌ (Function not found error)
- Any agent name followed by () ❌

✅ **ONLY CORRECT APPROACH - USE NATURAL LANGUAGE:**
- "ADXAgent, please find IP 10.0.0.3 in the largescans table" ✅
- "DocumentAgent, please retrieve the content of file.txt" ✅
- "FictionalCompaniesAgent, please get company info for this IP" ✅
- Use get_available_agents() to list available agents ✅
- Use get_agent_capabilities() for detailed agent information ✅

🚨 CRITICAL: If you see function call syntax errors in the log, STOP trying to call functions. Use natural language instead.

🚫 **FORBIDDEN FUNCTION CALLS:**
- ADXAgent() ❌ 
- MathAgent() ❌
- UtilityAgent() ❌ 
- DocumentAgent() ❌
- FictionalCompaniesAgent() ❌
- Any agent name as a function ❌

✅ **CORRECT APPROACH:**
- "ADXAgent, please find IP 10.0.0.3 in the largescans table" ✅
- Use get_available_agents() to list agents ✅
- Use get_agent_capabilities() for agent info ✅

RESPONSE PATTERNS:
✅ **Approve Complete Answer**: "Approved - Based on MathAgent's calculation, the factorial of 10 is 3,628,800..."
✅ **Request More Info**: "MathAgent, please also calculate the factorial of 5 for comparison"
✅ **Approve After Synthesis**: "Approved - Combining ADXAgent's data with MathAgent's calculation, here's your complete answer..."
❌ **NEVER DO**: Try to call "ADXAgent()", "MathAgent()", or any agent name as a function
❌ **NEVER DO**: Call functions like "ADXAgent-query_table" or "FictionalCompaniesAgent-get_device_info"

🎯 **WHEN AGENTS SAY "MY ANSWER IS COMPLETE":**
This is your signal to immediately approve and provide the final synthesized answer to the user.
Example:
- ADXAgent: "Found IP 10.0.0.3 in Chicago. My answer is complete - CoordinatorAgent, please approve"
- YOU: "Approved - Based on the database search, IP address 10.0.0.3 is located in Chicago with [relevant details]. This information was retrieved from the largescans table in your Azure Data Explorer instance."

TERMINATION RULE: 
- Only use "Approved" when you're providing the final, complete answer to the user
- The word "Approved" will end the conversation, so make sure your answer is comprehensive
- When specialist says "My answer is complete", that's your cue to approve and synthesize

WHEN TO RESPOND:
✅ **General Knowledge Questions**: Answer directly when no specialist tools are needed
   - "What is artificial intelligence?"
   - "Tell me about the history of computers"  
   - "How does machine learning work?"

✅ **System/Meta Questions**: Answer questions about this multi-agent system itself
   - "What agents are available?"
   - "What can each agent do?"
   - "How does this system work?"
   - "Tell me about the available tools"
   - "Who should I ask about math/database/document questions?"

   For "What agents are available?" use the get_available_agents() function to get the current agent list.

   For "What can each agent do?" use the get_agent_capabilities() function to get detailed capabilities.

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

For "Find IP 10.0.0.3 in the largescans table":
❌ Wrong: Just let ADXAgent respond  
✅ Correct: After ADXAgent provides data, YOU provide: "Approved - Based on the database search, IP address 10.0.0.3 is located in Chicago. The query was executed against the largescans table in your Azure Data Explorer Personnel database. [Add any relevant context about the findings]"

For "Can you summarize that document?" (with document context):
✅ Correct: "I see you're referring to [filename from session context]. DocumentAgent, please retrieve and summarize [specific document]"
Then after DocumentAgent responds: "Approved - Based on the document analysis, here's a comprehensive summary: [synthesized content]"

🎯 **MULTI-AGENT ORCHESTRATION:**
When a question requires multiple specialists, coordinate them step by step:

1. **Sequential Workflow**: Guide agents in logical order
   - First get data from DocumentAgent or ADXAgent
   - Then analyze with MathAgent or look up with FictionalCompaniesAgent
   - Finally synthesize all results into complete answer

2. **Wait for Each Specialist**: Don't terminate early
   - When one specialist says "My answer is complete", acknowledge their work
   - If more specialists are needed, ask them to proceed with their part
   - Only say "Approved" when ALL required work is done

3. **Example Multi-Agent Coordination**:
   User: "Check if IP addresses in file.txt are in our database and get company info"
   
   Step 1: "DocumentAgent, please retrieve the IP addresses from file.txt"
   DocumentAgent: "Found IP 1.2.3.4. My answer is complete - CoordinatorAgent, please approve"
   
   Step 2: "Thank you DocumentAgent. Now ADXAgent, please check if IP 1.2.3.4 exists in our scans table"
   ADXAgent: "Found IP 1.2.3.4 in Chicago. My answer is complete - CoordinatorAgent, please approve"
   
   Step 3: "Thank you ADXAgent. Now FictionalCompaniesAgent, please get company information for IP 1.2.3.4"
   FictionalCompaniesAgent: "IP belongs to TechCorp Inc. My answer is complete - CoordinatorAgent, please approve"
   
   Step 4: "Approved - Based on my analysis: The IP address 1.2.3.4 from your file was found in the database located in Chicago and belongs to TechCorp Inc. [complete synthesis]"

ORCHESTRATION PATTERNS:
- Acknowledge each specialist: "Thank you [AgentName]. Now [NextAgent], please..."
- Don't approve until all work is complete
- Guide the workflow: "First let's get the data, then analyze it, then look up company info"
- Synthesize everything at the end with "Approved - [comprehensive answer]"

🎯 REMEMBER: You have the final word on every conversation. The user should always receive their complete answer from YOU, not from individual specialists.

CURRENT AVAILABLE AGENTS:
{agents_info}

Your specialized agents will handle technical operations, but you coordinate the conversation and provide the final complete answer to the user."""
    async def _select_agents_for_question(self, question: str) -> List[ChatCompletionAgent]:
        """
        Intelligent agent selection based on question content.
        Ensures document questions get DocumentAgent, and multi-step questions get appropriate agents.
        """
        
        # Always include CoordinatorAgent as it will orchestrate the conversation
        selected_agents = [self.coordinator_agent]
        
        # Check for document references - these NEED DocumentAgent
        document_indicators = ["document", "file", ".txt", ".csv", ".pdf", "uploaded", "summarize", "analyze", "that document", "the file"]
        needs_document_agent = any(indicator in question.lower() for indicator in document_indicators)
        
        # Check for database references - these NEED ADXAgent  
        database_indicators = ["database", "table", "query", "adx", "scans", "data", "check if", "exists", "ip", "personnel"]
        needs_adx_agent = any(indicator in question.lower() for indicator in database_indicators)
        
        # Check for company/IP lookups - these NEED FictionalCompaniesAgent
        company_indicators = ["company", "ip", "device", "fictional", "business"]
        needs_companies_agent = any(indicator in question.lower() for indicator in company_indicators)
        
        # Check for math operations - these NEED MathAgent
        math_indicators = ["calculate", "math", "factorial", "average", "sum", "count", "statistics"]
        needs_math_agent = any(indicator in question.lower() for indicator in math_indicators)
        
        # Check for utility operations - these NEED UtilityAgent
        utility_indicators = ["hash", "timestamp", "sha", "md5", "system", "format"]
        needs_utility_agent = any(indicator in question.lower() for indicator in utility_indicators)
        
        # Check for RAG dataset references - these NEED specific RAG agents
        needs_rag_agents = []
        try:
            # Get RAG agents from the registry instead of the service directly
            for agent_key, agent_info in self.agent_registry.items():
                if agent_info.get('is_rag_agent', False):
                    dataset_name = agent_info['dataset_name']
                    rag_agent = agent_info['agent']  # This is now the Semantic Kernel agent
                    
                    # Check if question mentions this dataset specifically
                    dataset_indicators = [
                        dataset_name.lower(), 
                        f"{dataset_name.lower()} dataset",
                        f"{dataset_name.lower()} knowledge",
                        agent_info.get('rag_agent_impl', {}).dataset_config.display_name.lower() if agent_info.get('rag_agent_impl') else ""
                    ]
                    if any(indicator in question.lower() for indicator in dataset_indicators if indicator):
                        needs_rag_agents.append(rag_agent)
                        logger.info(f"🔍 Detected reference to {dataset_name} RAG dataset")
            
            # Also check for general RAG/knowledge base indicators
            general_rag_indicators = ["rag", "knowledge base", "search documents", "dataset", "index", "using", "query"]
            if any(indicator in question.lower() for indicator in general_rag_indicators):
                # If general RAG reference but no specific dataset, potentially include all RAG agents
                if not needs_rag_agents and len(question.split()) > 3:  # Only for substantial queries
                    for agent_key, agent_info in self.agent_registry.items():
                        if agent_info.get('is_rag_agent', False):
                            needs_rag_agents.append(agent_info['agent'])
                    logger.info(f"🔍 General RAG reference detected - including all {len(needs_rag_agents)} RAG agents")
                        
        except Exception as e:
            logger.error(f"❌ Error checking RAG agent needs: {e}")
        
        # Add agents based on detected needs
        if needs_document_agent and self.document_agent:
            selected_agents.append(self.document_agent)
            logger.info("📄 Added DocumentAgent - detected document references")
            
        if needs_adx_agent and self.adx_agent:
            selected_agents.append(self.adx_agent)
            logger.info("🔍 Added ADXAgent - detected database/query references")
            
        if needs_companies_agent and self.fictional_companies_agent:
            selected_agents.append(self.fictional_companies_agent)
            logger.info("� Added FictionalCompaniesAgent - detected company/IP references")
            
        if needs_math_agent and self.math_agent:
            selected_agents.append(self.math_agent)
            logger.info("🧮 Added MathAgent - detected mathematical operations")
            
        if needs_utility_agent and self.utility_agent:
            selected_agents.append(self.utility_agent)
            logger.info("🔧 Added UtilityAgent - detected utility operations")
        
        # Add specific RAG agents
        if needs_rag_agents:
            for rag_agent in needs_rag_agents:
                selected_agents.append(rag_agent)
                logger.info(f"📚 Added {rag_agent.name} - detected RAG dataset reference")
        
        # If none of the specific indicators were found, this might be a general question
        # or complex multi-step question - include all agents for maximum flexibility
        if len(selected_agents) == 1:  # Only coordinator selected
            logger.info("🤔 No specific indicators found - including all agents for flexibility")
            for name, info in self.agent_registry.items():
                if name != 'CoordinatorAgent':  # Don't add coordinator twice
                    selected_agents.append(info['agent'])
        
        logger.info(f"🎯 Selected {len(selected_agents)} agents: {[agent.name for agent in selected_agents]}")
        
        return selected_agents
    
    async def process_question(self, question: str, session_id: str = None, user_id: str = None, adx_token: str = None) -> str:
        """Process a user question through the AgentGroupChat system with memory context.
        
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
            logger.info(f"🔑 ADX Token: Not provided - using default authentication")
        logger.info("="*60)

        
        try:
            # Update the MCP client with the current user, session, and ADX token context
            if user_id or session_id or adx_token:
                logger.info(f"🔄 Updating MCP client context - User ID: {user_id}, Session ID: {session_id}, ADX Token: {'Available' if adx_token else 'Not provided'}")
                self.mcp_client.user_id = user_id
                self.mcp_client.session_id = session_id
                self.mcp_client.adx_token = adx_token

            # MEMORY INTEGRATION: Load or create chat history for the session
            session_chat_history = None
            if session_id and user_id:
                logger.info(f"🧠 Loading conversation memory for session {session_id}")
                session_chat_history = await self.memory_service.load_chat_history(session_id, user_id)
                if not session_chat_history:
                    session_chat_history = self.memory_service.create_chat_history(session_id)
                    logger.info(f"🆕 Created new memory for session {session_id}")
                else:
                    logger.info(f"📚 Loaded existing memory with {len(session_chat_history.messages)} messages")
                
                # Add the current user question to memory
                # Use a simple "User" name to avoid OpenAI's 64-character limit for message names
                self.memory_service.add_user_message(session_id, question, "User")
                
                # 🔧 ENHANCED TOKEN MANAGEMENT: Monitor and optimize memory for token limits
                if session_chat_history and len(session_chat_history.messages) > 20:
                    # Check current token usage
                    token_stats = self.memory_service.get_token_stats(session_id)
                    current_usage = token_stats.get('usage_percentage', 0)
                    
                    if token_config.is_critical_usage(token_stats.get('messages_tokens', 0)):
                        logger.critical(f"🚨 CRITICAL MEMORY TOKEN USAGE: {current_usage}% - Immediate optimization required")
                        was_optimized = self.memory_service.optimize_chat_history_for_tokens(session_id)
                    elif token_config.should_truncate(token_stats.get('messages_tokens', 0)):
                        logger.warning(f"⚠️ HIGH MEMORY TOKEN USAGE: {current_usage}% - Optimization recommended")
                        was_optimized = self.memory_service.optimize_chat_history_for_tokens(session_id)
                    else:
                        logger.info(f"✅ MEMORY TOKEN USAGE OK: {current_usage}%")
                        was_optimized = False
                    
                    if was_optimized:
                        logger.info("🔧 Memory optimized for token limits")
                        # Reload the optimized history
                        session_chat_history = self.memory_service.get_chat_history(session_id)
                
                # Log token usage statistics
                token_stats = self.memory_service.get_token_stats(session_id)
                logger.info(f"📊 Token usage: {token_stats['messages_tokens']}/{token_stats['max_tokens']} "
                           f"({token_stats['usage_percentage']}%) - {token_stats['total_messages']} messages")
                
                # Warn if approaching token limit
                if token_stats['usage_percentage'] > 80:
                    logger.warning(f"⚠️ High token usage: {token_stats['usage_percentage']}% - consider conversation summarization")
                
                # Check if memory needs reduction (legacy fallback)
                if len(session_chat_history.messages) > 40:  # Reduce when getting large
                    was_reduced = await self.memory_service.reduce_chat_history(session_id, 30)
                    if was_reduced:
                        logger.info(f"🗂️ Reduced session memory to manage context length")

            # DOCUMENT CONTEXT INTEGRATION: Load session documents for context
            session_documents = []
            if session_id and user_id:
                try:
                    # Try to import document_service - it may not be available in all environments
                    try:
                        from src.services.document_service import document_service
                        user_docs_result = await document_service.get_user_documents(user_id, session_id)
                        
                        # Handle the response structure correctly
                        if user_docs_result.get("success", False):
                            session_documents = user_docs_result.get("documents", [])
                            logger.info(f"📄 Loaded {len(session_documents)} documents for session context")
                        else:
                            logger.debug(f"📄 No documents found for session: {user_docs_result.get('message', 'Unknown error')}")
                    except ImportError:
                        logger.info("📄 Document service not available - skipping document context")
                    except AttributeError:
                        logger.info("📄 Document service method not available - skipping document context")
                except Exception as e:
                    logger.warning(f"Failed to load session documents: {e}")
            else:
                logger.debug(f"📄 Session document loading skipped - session_id: {session_id}, user_id: {user_id}")

            # Enhance the question with document context if documents exist and question seems contextual
            contextual_phrases = ["that document", "the file", "the document", "it", "this file", "uploaded", "summarize", "analyze"]
            has_contextual_reference = any(phrase in question.lower() for phrase in contextual_phrases)
            
            logger.debug(f"📄 Document context check - has_contextual_reference: {has_contextual_reference}, session_documents: {len(session_documents)}")

            if session_documents and has_contextual_reference:
                # Handle both dict objects and objects with to_dict() method
                doc_context_lines = []
                for doc in session_documents:
                    if isinstance(doc, dict):
                        doc_context_lines.append(f"- {doc.get('fileName', 'Unknown')} (ID: {doc.get('documentId', 'Unknown')})")
                    elif hasattr(doc, 'to_dict'):
                        doc_dict = doc.to_dict()
                        doc_context_lines.append(f"- {doc_dict.get('fileName', 'Unknown')} (ID: {doc_dict.get('documentId', 'Unknown')})")
                    else:
                        doc_context_lines.append(f"- Document (type: {type(doc).__name__})")
                
                doc_context = "\n".join(doc_context_lines)
                enhanced_question = f"""DOCUMENT CONTEXT - Available documents in this session:
{doc_context}

User question: {question}

Note: User may be referring to one of these documents contextually."""
                logger.info(f"📄 Enhanced question with document context ({len(session_documents)} docs)")
            elif has_contextual_reference and not session_documents:
                # User is making contextual reference but no session documents found
                enhanced_question = f"""CONTEXTUAL DOCUMENT REFERENCE DETECTED: The user is asking about a document contextually ("{question}"), but no session documents were found. 

User question: {question}

IMPORTANT: DocumentAgent should check if documents are available in storage and handle this contextual reference appropriately. The user may be referring to a document they uploaded previously."""
                logger.info(f"📄 Enhanced question with contextual reference guidance (no session docs found)")
            else:
                enhanced_question = question
                
            # Select which agents should participate for this specific question
            selected_agents = await self._select_agents_for_question(enhanced_question)
            
            # 🧠 COORDINATOR INTELLIGENCE: Let coordinator analyze the question and create dynamic strategy
            # Do this BEFORE fast path check so document context is considered
            logger.info("🧠 Coordinator analyzing question to create dynamic agent selection strategy...")
            dynamic_strategy = await self._get_coordinator_analysis(enhanced_question, selected_agents)
            
            # MEMORY-ENHANCED OPTIMIZATION: Check if we can use fast path with context
            # BUT NOT for contextual document questions that need agent coordination
            should_use_fast_path = (len(selected_agents) == 1 and 
                                  selected_agents[0].name == "CoordinatorAgent" and 
                                  not has_contextual_reference)  # Don't fast path document questions
            
            if should_use_fast_path:
                logger.info("🚀 FAST PATH: Only CoordinatorAgent selected - handling with memory context")
                
                try:
                    from semantic_kernel.contents import ChatHistory
                    from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
                    
                    # Use session memory if available, otherwise create temporary history
                    if session_chat_history:
                        chat_history = session_chat_history
                        logger.info(f"🧠 Using session memory with {len(chat_history.messages)} messages")
                    else:
                        # Create temporary history for non-session requests
                        chat_history = ChatHistory()
                        chat_history.add_system_message(self.coordinator_agent._instructions)
                        chat_history.add_user_message(question)
                        logger.info("🧠 Using temporary memory for non-session request")
                    
                    # Add the user's question to the session history
                    if session_chat_history:
                        session_chat_history.add_user_message(question)
                    
                    # Use the coordinator agent's completion service with kernel functions enabled
                    completion_service = self.coordinator_agent.kernel.get_service()
                    
                    # Create execution settings that enable function calling
                    settings = OpenAIChatPromptExecutionSettings(
                        max_tokens=1000,
                        temperature=0.1,
                        function_choice_behavior=self.coordinator_agent.function_choice_behavior
                    )
                    
                    # Get chat completion with kernel function support and resilient Azure service
                    if hasattr(completion_service, 'get_chat_message_content'):
                        # Using resilient service
                        response = await completion_service.get_chat_message_content(
                            chat_history=chat_history,
                            settings=settings,
                            kernel=self.coordinator_agent.kernel
                        )
                    else:
                        # Fallback for compatibility
                        response = await completion_service.get_chat_message_content(
                            chat_history=chat_history,
                            settings=settings,
                            kernel=self.coordinator_agent.kernel
                        )
                    
                    final_response = str(response.content).strip() if response and response.content else ""
                    
                    if final_response and len(final_response) > 50:
                        # Add response to memory
                        if session_id:
                            self.memory_service.add_assistant_message(session_id, final_response, "CoordinatorAgent")
                            # Save memory periodically
                            await self.memory_service.save_chat_history(session_id, user_id)
                        
                        logger.info(f"✅ FAST PATH SUCCESS with memory: Generated {len(final_response)} characters")
                        logger.info("📊 COMPLETION SUMMARY:")
                        logger.info(f"    📝 Final response length: {len(final_response)} characters")
                        logger.info(f"    🧠 Memory context: {'YES' if session_chat_history else 'NO'}")
                        logger.info(f"    🎯 Memory messages: {len(session_chat_history.messages) if session_chat_history else 0}")
                        logger.info("============================================================")
                        return final_response
                    else:
                        logger.warning("⚠️ FAST PATH: Response too short, falling back to group chat")
                        
                except Exception as e:
                    logger.error(f"❌ FAST PATH ERROR: {str(e)}, falling back to group chat")
                
                # If fast path fails, continue with normal group chat processing
                logger.info("🔄 FALLBACK: Proceeding with normal group chat workflow")
            
            # Create a fresh group chat for each question with coordinator-enhanced strategies
            # (coordinator analysis already done above before fast path check)
            selection_function = self._create_selection_function(dynamic_strategy)
            termination_function = self._create_termination_function()
            
            # Create selection strategy following Semantic Kernel documentation patterns
            selection_strategy = KernelFunctionSelectionStrategy(
                function=selection_function,
                kernel=self.kernel,  # Use the main kernel
                agent_variable_name="_agent_",  # Use standard SK parameter name
                history_variable_name="_history_",  # Use standard SK parameter name
                result_parser=self._parse_strategy_result,  # Use proper result parser for ChatMessageContent lists
                history_reducer=ChatHistoryTruncationReducer(target_count=5),
            )
            
            # Create termination strategy following Semantic Kernel documentation patterns
            termination_strategy = KernelFunctionTerminationStrategy(
                function=termination_function,
                kernel=self.kernel,  # Use the main kernel
                agents=[self.coordinator_agent],  # Only coordinator can trigger termination
                agent_variable_name="_agent_",  # Use standard SK parameter name
                history_variable_name="_history_",  # Use standard SK parameter name
                result_parser=lambda result: "TERMINATE" in str(result).upper(),  # Simple terminate check
                maximum_iterations=10,
                history_reducer=ChatHistoryTruncationReducer(target_count=3),
            )
            
            fresh_group_chat = AgentGroupChat(
                agents=selected_agents,
                selection_strategy=selection_strategy,
                termination_strategy=termination_strategy
            )
            logger.info(f"🔄 Created fresh AgentGroupChat with {len(selected_agents)} selected agents: {[agent.name for agent in selected_agents]}")
            
            # MEMORY INTEGRATION: If we have session memory, inject relevant context
            if session_chat_history and session_id:
                logger.info("🧠 Injecting conversation context into group chat")
                
                # Get recent context summary
                context_summary = self.memory_service.get_context_summary(session_id, 500)
                if context_summary and len(context_summary.strip()) > 10:
                    # If we already have document context or contextual reference, combine it with conversation context
                    if (session_documents and has_contextual_reference) or (has_contextual_reference and not session_documents):
                        enhanced_question = f"Previous conversation context:\n{context_summary}\n\n{enhanced_question}"
                        logger.info(f"📋 Enhanced question with both document/contextual and conversation context")
                    else:
                        # Only conversation context
                        enhanced_question = f"Previous conversation context:\n{context_summary}\n\nCurrent question: {question}"
                        logger.info(f"📋 Enhanced question with conversation context ({len(context_summary)} chars)")
            
            # Create the initial chat message with enhanced context
            chat_message = ChatMessageContent(role=AuthorRole.USER, content=enhanced_question)
            
            # Add the user message to the group chat
            await fresh_group_chat.add_chat_message(chat_message)
            logger.info("🎭 Starting AgentGroupChat processing with memory context...")
            
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
                        coordinator_response = content
                        logger.info(f"   🧠 Coordinator response captured (length: {len(content)})")
                else:
                    logger.info(f"⏭️ Skipping empty response from {getattr(response, 'name', 'Unknown')}")
            
            # If no responses were captured, return a fallback message
            if not responses:
                logger.info("🚨 No valid responses captured - all responses were filtered")
                return "I apologize, but I couldn't generate a proper response. Please try rephrasing your question."
            
            # Enhanced Dynamic Re-routing (same as before)
            logger.info("🔍 Evaluating response completeness and need for additional agents...")
            
            # Check for errors and attempt recovery
            recovery_suggestions = await self._handle_agent_errors(responses, question)
            if recovery_suggestions:
                responses.extend(recovery_suggestions)
                logger.info(f"🔧 Added {len(recovery_suggestions)} recovery suggestions")
            
            # Evaluate if responses fully answer the question
            selected_agent_names = [agent.name for agent in selected_agents]
            evaluation = await self._evaluate_response_completeness(question, responses, selected_agent_names)
            
            # If response is incomplete, attempt dynamic re-routing
            if not evaluation['is_complete'] and evaluation['suggested_agents']:
                logger.info(f"🔄 Response incomplete: {evaluation['missing_info']}")
                logger.info(f"🎯 Attempting dynamic re-routing to: {evaluation['suggested_agents']}")
                
                # Add suggested agents and get follow-up responses (same logic as before)
                current_agent_names = [agent.name for agent in selected_agents]
                new_agents_needed = [name for name in evaluation['suggested_agents'] 
                                   if name not in current_agent_names and name in self.agent_registry]
                
                if new_agents_needed:
                    for agent_name in new_agents_needed:
                        if agent_name in self.agent_registry:
                            selected_agents.append(self.agent_registry[agent_name]['agent'])
                            logger.info(f"➕ Added {agent_name} to conversation for additional information")
                    
                    # Recreate group chat with additional agents using proper strategies
                    fresh_group_chat = AgentGroupChat(
                        agents=selected_agents,
                        selection_strategy=selection_strategy,
                        termination_strategy=termination_strategy
                    )
                    
                    # Copy existing conversation history
                    for response in responses:
                        if response.get('type') != 'recovery':
                            chat_message = ChatMessageContent(
                                role=AuthorRole.ASSISTANT, 
                                content=f"[{response['agent']}]: {response['content']}"
                            )
                            await fresh_group_chat.add_chat_message(chat_message)
                
                # Send follow-up questions
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
            
            # MEMORY INTEGRATION: Add the final response to memory
            if session_id and user_id and final_response:
                self.memory_service.add_assistant_message(session_id, final_response, "MultiAgentSystem")
                # Save memory after successful completion
                await self.memory_service.save_chat_history(session_id, user_id)
                logger.info(f"💾 Saved conversation to memory for session {session_id}")
            
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
            
            logger.info("🏁 AgentGroupChat processing completed successfully with memory")
            
            # Enhanced completion logging
            final_length = len(final_response) if final_response else 0
            has_coordinator = bool(coordinator_response)
            specialist_count = len(specialist_responses)
            memory_messages = len(session_chat_history.messages) if session_chat_history else 0
            
            logger.info(f"📊 COMPLETION SUMMARY:")
            logger.info(f"   📝 Final response length: {final_length} characters")
            logger.info(f"   🧠 Coordinator response: {'YES' if has_coordinator else 'NO'}")
            logger.info(f"   🎯 Specialist responses: {specialist_count}")
            logger.info(f"   🎭 Total conversation turns: {len(responses)}")
            logger.info(f"   💾 Memory context messages: {memory_messages}")
            
            if final_length < 50:
                logger.warning(f"⚠️ WARNING: Final response seems short ({final_length} chars) - may be incomplete")
            
            if specialist_count > 0 and not has_coordinator:
                logger.warning(f"⚠️ WARNING: Specialists responded but no coordinator synthesis - potential incomplete answer")
            
            logger.info("="*60)
            
            return final_response if final_response else "No response generated"
            
        except Exception as e:
            logger.error(f"❌ Error processing question: {str(e)}")
            
            # Log resilience statistics for debugging
            try:
                from src.services.resilient_azure_service import get_all_resilience_stats
                resilience_stats = get_all_resilience_stats()
                logger.error(f"🛡️ Resilience Stats at Error Time: {resilience_stats}")
            except Exception as stats_error:
                logger.warning(f"⚠️ Could not retrieve resilience stats: {stats_error}")
            
            return f"❌ Error processing question: {str(e)}"
    
    def get_resilience_stats(self) -> Dict[str, Any]:
        """Get comprehensive resilience statistics from all agent services.
        
        Returns:
            Dict containing resilience statistics for monitoring and debugging
        """
        try:
            from src.services.resilient_azure_service import get_all_resilience_stats
            stats = get_all_resilience_stats()
            
            # Add multi-agent system specific stats
            stats['multi_agent_system'] = {
                'total_agents': len(self.agent_registry),
                'agent_names': list(self.agent_registry.keys()),
                'mcp_connected': hasattr(self.mcp_client, 'is_connected') and self.mcp_client.is_connected(),
                'memory_service_available': self.memory_service is not None
            }
            
            return stats
        except Exception as e:
            logger.warning(f"⚠️ Could not retrieve resilience stats: {e}")
            return {
                'error': str(e),
                'multi_agent_system': {
                    'total_agents': len(self.agent_registry) if hasattr(self, 'agent_registry') else 0,
                    'stats_unavailable': True
                }
            }
    
    def reset_circuit_breakers(self):
        """Reset all circuit breakers in the agent services - useful for recovery or testing."""
        try:
            from src.services.resilient_azure_service import reset_all_circuit_breakers
            reset_all_circuit_breakers()
            logger.info("🔄 All circuit breakers reset for multi-agent system")
        except Exception as e:
            logger.error(f"❌ Error resetting circuit breakers: {e}")
    
    async def _synthesize_responses(self, specialist_responses, coordinator_response, original_question):
        """
        Use the CoordinatorAgent's LLM to intelligently synthesize responses from multiple agents into a coherent final response.
        
        INCLUDES TOKEN LIMIT PROTECTION to prevent synthesis prompts from exceeding limits.
        
        Args:
            specialist_responses: List of responses from specialist agents (with agent names)
            coordinator_response: Response from coordinator agent (without agent name prefix)
            original_question: The original user question for context
        
        Returns:
            str: Intelligently synthesized final response
        """
        if not specialist_responses and not coordinator_response:
            return "No response generated"

        # 🔒 TOKEN SAFETY: Check total response size before synthesis
        try:
            from src.services.token_management import token_manager
        except:
            # Fallback if token manager import fails
            from services.token_management import TokenManager
            token_manager = TokenManager()
        
        total_content = original_question + (coordinator_response or "")
        for response in specialist_responses:
            total_content += response
        
        total_tokens = token_manager.count_tokens(total_content)
        synthesis_overhead = 1000  # Estimate for synthesis prompt structure
        
        # If combined content + synthesis overhead would exceed safe limits, use emergency fallback
        if total_tokens + synthesis_overhead > token_manager.SAFE_LIMIT - 5000:  # Leave 5K buffer for response generation
            logger.warning(f"🚨 TOKEN OVERFLOW PREVENTION: Combined responses ({total_tokens:,} tokens) too large for LLM synthesis")
            logger.info("🔄 Using emergency truncated synthesis to prevent token overflow")
            return self._emergency_truncated_synthesis(specialist_responses, coordinator_response, total_tokens)
        
        logger.info(f"📊 Synthesis token check: {total_tokens:,} tokens + {synthesis_overhead} overhead - proceeding with LLM synthesis")
        
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
        if coordinator_response and len(coordinator_response) > 200:  # Increased threshold for substantial response
            # Check if coordinator response appears to be synthesizing specialist responses
            # More specific indicators that suggest actual synthesis, not initial coordination
            synthesis_indicators = [
                "based on the analysis", "according to the data", "the results show", 
                "combining the information", "together these findings", "overall the data",
                "in summary, the", "to summarize the results", "from the analysis",
                "the investigation reveals", "the findings indicate", "conclusively",
                "the evidence shows", "after checking", "upon examination"
            ]
            
            response_lower = coordinator_response.lower()
            appears_synthesized = any(indicator in response_lower for indicator in synthesis_indicators)
            
            # Additional check: does it contain agent names suggesting synthesis?
            contains_agent_references = any(agent in response_lower for agent in 
                ['documentagent', 'adxagent', 'fictionalcompaniesagent', 'mathagent', 'utilityagent'])
            
            # Only use coordinator response if it truly appears to be a synthesis
            if appears_synthesized and contains_agent_references and len(unique_specialist_responses) > 0:
                logger.info("🧠 Using coordinator's pre-synthesized response as final answer")
                return coordinator_response
            elif len(unique_specialist_responses) == 0:
                logger.info("📝 Using coordinator-only response (no specialists responded)")
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
        
        INCLUDES TOKEN LIMIT PROTECTION to prevent synthesis prompts from exceeding limits.
        
        Args:
            specialist_responses: List of specialist agent responses with agent names
            coordinator_response: Coordinator agent response (if any)
            original_question: The original user question
        
        Returns:
            str: LLM-synthesized final response
        """
        # Get token manager
        try:
            from src.services.token_management import token_manager
        except:
            from services.token_management import TokenManager
            token_manager = TokenManager()
        
        try:
            logger.info("🧠 Using CoordinatorAgent's LLM to synthesize multiple responses...")
            
            # Prepare the synthesis prompt with ENHANCED TOKEN LIMIT PROTECTION
            specialist_data = []
            for response in specialist_responses:
                if ":" in response:
                    agent_name, content = response.split(":", 1)
                    specialist_data.append(f"**{agent_name.strip()}**:\n{content.strip()}")
                else:
                    specialist_data.append(response)

            # 🔒 ENHANCED TOKEN SAFETY: Use centralized configuration for limits
            specialist_text = chr(10).join(specialist_data)
            specialist_tokens = token_manager.count_tokens(specialist_text)
            
            # Calculate available space using centralized config
            prompt_overhead = 800
            question_tokens = token_manager.count_tokens(original_question)
            coordinator_tokens = token_manager.count_tokens(coordinator_response if coordinator_response else "")
            
            # Use synthesis config for response generation space
            synthesis_config = token_config.get_synthesis_config()
            response_reserve = synthesis_config['max_tokens']
            
            available_for_specialist = token_config.get_available_tokens(
                prompt_overhead + question_tokens + coordinator_tokens + response_reserve
            )
            
            # Enhanced token monitoring with alerts
            usage_percentage = (specialist_tokens / available_for_specialist) * 100 if available_for_specialist > 0 else 100
            
            if token_config.is_critical_usage(specialist_tokens + prompt_overhead + question_tokens + coordinator_tokens):
                logger.critical(f"🚨 CRITICAL TOKEN USAGE: {usage_percentage:.1f}% - Emergency truncation required")
            elif token_config.should_truncate(specialist_tokens + prompt_overhead + question_tokens + coordinator_tokens):
                logger.warning(f"⚠️ HIGH TOKEN USAGE: {usage_percentage:.1f}% - Truncation recommended")
            else:
                logger.info(f"✅ TOKEN USAGE OK: {usage_percentage:.1f}% of available synthesis space")
            
            if specialist_tokens > available_for_specialist:
                logger.warning(f"🚨 SYNTHESIS TOKEN OVERFLOW: Specialist data ({specialist_tokens:,} tokens) exceeds safe limit ({available_for_specialist:,} tokens)")
                logger.info("✂️ Truncating specialist responses to fit within token limits")
                
                # Truncate specialist data to fit
                truncated_specialist_data = []
                current_tokens = 0
                
                for response_text in specialist_data:
                    response_tokens = token_manager.count_tokens(response_text)
                    if current_tokens + response_tokens <= available_for_specialist:
                        truncated_specialist_data.append(response_text)
                        current_tokens += response_tokens
                    else:
                        # Truncate this response to fit remaining space
                        remaining_space = available_for_specialist - current_tokens
                        if remaining_space > 100:  # Only include if we have meaningful space
                            # Estimate characters from remaining tokens (rough: 3.5 chars/token)
                            max_chars = int(remaining_space * 3.5)
                            truncated_response = response_text[:max_chars] + "... [TRUNCATED DUE TO TOKEN LIMITS]"
                            truncated_specialist_data.append(truncated_response)
                        break
                
                specialist_text = chr(10).join(truncated_specialist_data)
                final_tokens = token_manager.count_tokens(specialist_text)
                logger.info(f"✂️ Truncated specialist data: {specialist_tokens:,} → {final_tokens:,} tokens ({((specialist_tokens - final_tokens) / specialist_tokens * 100):.1f}% reduction)")
            
            synthesis_prompt = f"""You are the CoordinatorAgent in a multi-agent system. Your task is to synthesize responses from specialist agents into a single, coherent, comprehensive answer for the user.

ORIGINAL USER QUESTION:
{original_question}

SPECIALIST AGENT RESPONSES:
{specialist_text}

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

    def _emergency_truncated_synthesis(self, specialist_responses, coordinator_response, total_tokens) -> str:
        """
        Emergency synthesis when token limit is exceeded.
        Creates a basic summary without LLM synthesis.
        """
        try:
            logger.warning(f"🚨 EMERGENCY SYNTHESIS: {total_tokens:,} tokens exceeded limit - using truncated fallback")
            
            if not specialist_responses and not coordinator_response:
                return "No response available (emergency mode)."
            
            # Prioritize coordinator response if substantial
            if coordinator_response and len(coordinator_response) > 100:
                return f"Response: {coordinator_response[:500]}{'...' if len(coordinator_response) > 500 else ''}"
            
            # Collect key insights from specialist responses
            insights = []
            for response in specialist_responses:
                if ":" in response:
                    content = response.split(":", 1)[1].strip()
                else:
                    content = response
                    
                if content:
                    # Take first sentence or up to 200 characters
                    if '.' in content:
                        first_sentence = content.split('.')[0] + '.'
                        insights.append(first_sentence[:200])
                    else:
                        insights.append(content[:200])
            
            # Create simple aggregated response
            if len(insights) == 1:
                return f"Response: {insights[0]}"
            elif len(insights) > 1:
                return f"Multiple insights found:\n" + "\n".join(f"• {insight}" for insight in insights[:3])  # Limit to 3 for emergency mode
            else:
                return "No detailed response available (emergency mode)."
                
        except Exception as e:
            print(f"❌ Emergency synthesis failed: {e}")
            return "Response processing encountered an error (emergency mode)."


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
    system = MultiAgentSystem(azure_api_key, azure_endpoint, azure_deployment)
    
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
