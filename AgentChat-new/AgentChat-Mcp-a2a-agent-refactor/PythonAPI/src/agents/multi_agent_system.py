"""DEPRECATED: Legacy multi_agent_system superseded by A2A wrapper.

This file intentionally kept minimal to avoid import errors. The new implementation
is in `src/agents/mas_a2a.py` and is used by `sse_multi_agent_system.py`.
"""

import warnings

warnings.warn(
    "multi_agent_system.py is deprecated. Use src.agents.mas_a2a.MultiAgentSystem instead.",
    DeprecationWarning,
)

# The remaining legacy content is preserved below for reference only and is not executed.
# It is wrapped in a triple-quoted string to avoid syntax issues.
LEGACY_REMOVED = '''

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
- UtilityAgent: NOT IMPLEMENTED (Hash/timestamp generation would go here)
- CoordinatorAgent: General questions, synthesis of results, final answers, coordination

INTELLIGENT ROUTING LOGIC:
1. DOCUMENT REFERENCES: If question mentions files (.txt, .csv, documents) or "in the file" → START with DocumentAgent
2. DATABASE OPERATIONS: If mentions tables, IP lookups in database, "check if exists" → ADXAgent
3. COMPANY LOOKUPS: If asks for company info, device info, IP company associations → FictionalCompaniesAgent
4. UTILITIES: If asks for hashes, timestamps, system info → NOT SUPPORTED (UtilityAgent not implemented)
5. SYNTHESIS: After specialists provide data → CoordinatorAgent for final answer

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
                    'ADXAgent': self.adx_agent,
                    'DocumentAgent': self.document_agent,
                    'FictionalCompaniesAgent': self.fictional_companies_agent,
                    'FEMAAgent': self.fema_agent
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
- UtilityAgent: NOT IMPLEMENTED (Hash/timestamp generation would go here)
- CoordinatorAgent: General questions, synthesis, final answers, coordination

USER QUESTION: {question}

AVAILABLE AGENTS FOR THIS QUESTION: {', '.join(agent_names)}

Analyze this question and provide intelligent routing guidance:

1. WORKFLOW ANALYSIS: What steps are needed to answer this question completely?
2. AGENT SEQUENCE: Which agents should be used and in what order?
3. PRIORITY ROUTING: Which agent should go first and why?
4. DEPENDENCIES: Are there dependencies between agents (e.g., need file content before database query)?

Create a selection strategy that will guide the system to route intelligently. Consider:
"""A2A-first MultiAgentSystem wrapper.

Replaces legacy group-chat orchestration with an Agent-to-Agent (A2A) router
that delegates tasks to remote specialist agents which use MCP tools.

Public API:
- initialize() -> bool
- process_question(question, session_id=None, user_id=None, adx_token=None) -> str
- cleanup() -> None
"""

from typing import List
import os
import logging

from src.a2a.host_router import RoutingHost

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class MultiAgentSystem:
    """Thin facade over the A2A RoutingHost."""

    def __init__(self, azure_openai_api_key: str, azure_openai_endpoint: str, azure_openai_deployment: str):
        self.host = RoutingHost(
            azure_api_key=azure_openai_api_key,
            azure_endpoint=azure_openai_endpoint,
            azure_deployment=azure_openai_deployment,
        )
        self.specialist_urls: List[str] = [
            os.getenv("DOCUMENT_AGENT_URL", "http://localhost:18081"),
            os.getenv("ADX_AGENT_URL", "http://localhost:18082"),
            os.getenv("FEMA_AGENT_URL", "http://localhost:18083"),
            os.getenv("FICTIONAL_COMPANIES_AGENT_URL", "http://localhost:18084"),
        ]

    async def initialize(self) -> bool:
        await self.host.discover_agents([u for u in self.specialist_urls if u])
        await self.host.initialize()
        return True

    async def process_question(self, question: str, session_id: str = None, user_id: str = None, adx_token: str = None) -> str:
        # Note: session/user/adx_token can be forwarded via headers by specialists if needed.
        return await self.host.process_user_message(question)

    async def cleanup(self):
        return None
                "kusto_list_tables",
                "kusto_describe_table",
                "kusto_query",
                "kusto_get_cluster_info",
                "kusto_clear_user_client_cache"
            }
            for attr_name in list(dir(self.adx_mcp_plugin)):
                if hasattr(getattr(self.adx_mcp_plugin, attr_name, None), '__kernel_function_parameters__'):
                    if attr_name not in allowed_tools:
                        delattr(self.adx_mcp_plugin, attr_name)
            
            
            # Add the MCP plugin to the kernel
            adx_kernel.add_plugin(self.adx_mcp_plugin, plugin_name="ADXTools")
            logger.info(f"🔧 Added MCP plugin to ADX Agent kernel with endpoint: {settings.mcp.server_endpoint}")
            
            # Add SSE filter to capture tool calls
            adx_kernel.add_filter("function_invocation", self._sse_tool_filter)
            logger.info("🔧 Added SSE tool filter to ADX Agent kernel")
            
            # Track the initial context used for the plugin
            self.last_mcp_user_id = self.current_user_id
            self.last_mcp_session_id = self.current_session_id
            self.last_mcp_adx_token = self.current_adx_token
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to MCP server: {str(e)}")
            logger.error("❌ ADX Agent will be created without tools - MCP server connection required")
            # Don't add any tools if MCP connection fails
            # The agent will still be created but won't have access to ADX tools
        
        # Note: Using modern Semantic Kernel Filter pipeline for SSE events
        # Function invocation filters capture all tool calls including MCP server calls
        
        logger.info("✅ ADX Agent created with MCP server tools and SSE filter")
        
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
- Use available tools to see available tables in the database
- Use available tools to get EXACT column names and types
- NEVER guess table or column names - schema discovery is MANDATORY

**STEP 2: CONSTRUCT QUERIES USING EXACT SCHEMA NAMES**
- Use the exact table names returned by your table listing tools
- Use the exact column names returned by your schema description tools
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

Step 1: List tables in database to confirm "scans" exists
Step 2: Describe table schema to get exact column names
Step 3: Based on schema, construct: scans | where ip_address == "1.2.3.4"
```

🚫 **NEVER DO THIS:**
- `SCANS | where IPAddress == "1.2.3.4"` (guessing names)
- `Scans | where IP_Address == "1.2.3.4"` (assuming case)
- Any query without first checking schema

✅ **ALWAYS DO THIS:**
1. Check schema with your available tools
2. Use exact names from schema results
3. Construct query with verified names

🔧 **ERROR HANDLING:**
If you get "Failed to resolve table or column":
1. You skipped schema checking - go back to Step 1
2. Re-run your schema tools to get correct names
3. Do NOT try multiple variations - use schema results only

COLLABORATION APPROACH:
- Handle ALL database/ADX parts of questions yourself
- After getting data, coordinate with other agents if needed
- Always get the data first using proper schema workflow

COMPLETION PROTOCOL:
- After providing your answer, always end with: "My answer is complete - CoordinatorAgent, please approve"
- This signals that you're done and ready for coordinator review
- Stay silent until specifically asked for more information

EXAMPLES OF PROPER RESPONSES:
❌ BAD: "Let me query the SCANS table..." (guessing)
✅ GOOD: "Let me first check what tables are available, then examine the schema..."

REMEMBER: No queries without schema verification! Schema first, always!
""",
            function_choice_behavior=FunctionChoiceBehavior.Auto(filters={"included_plugins": ["ADXTools"]})
        )
        logger.info("✅ ADX Agent created successfully")
        
        # Document Agent (Using Semantic Kernel MCP integration)
        logger.info("📄 Creating Document Agent with Azure OpenAI and SK MCP...")
        document_kernel = Kernel()
        document_service = AzureChatCompletion(
            service_id="document_completion",
            api_key=self.azure_openai_api_key,
            endpoint=self.azure_openai_endpoint,
            deployment_name=self.azure_openai_deployment
        )
        document_kernel.add_service(document_service)
        
        # Connect to MCP server and add Document tools using SK MCP plugin
        try:
            # Prepare headers for context
            headers = {}
            if self.current_user_id:
                headers['X-User-ID'] = self.current_user_id
            if self.current_session_id:
                headers['X-Session-ID'] = self.current_session_id
            if self.current_adx_token:
                headers['X-ADX-Token'] = self.current_adx_token
            
            # Create and connect the MCP plugin directly
            self.document_mcp_plugin = MCPStreamableHttpPlugin(
                name="DocumentMCPPlugin",
                url=settings.mcp.server_endpoint or "http://localhost:3001/mcp",
                headers=headers,
                load_tools=True,
                load_prompts=False,
                request_timeout=30,
                sse_read_timeout=300,
                terminate_on_close=True,
                description="Document tools via MCP server"
            )
            
            await self.document_mcp_plugin.connect()
            # Filter tools 
            allowed_tools = {
                "list_documents",
                "search_documents",
                "get_document", 
                "get_document_content_summary"
            }
            for attr_name in list(dir(self.document_mcp_plugin)):
                if hasattr(getattr(self.document_mcp_plugin, attr_name, None), '__kernel_function_parameters__'):
                    if attr_name not in allowed_tools:
                        delattr(self.document_mcp_plugin, attr_name)

            # Add the MCP plugin to the kernel
            document_kernel.add_plugin(self.document_mcp_plugin, plugin_name="DocumentTools")
            logger.info(f"🔧 Added MCP plugin to Document Agent kernel with endpoint: {settings.mcp.server_endpoint}")
            
            # Add SSE filter to capture tool calls
            document_kernel.add_filter("function_invocation", self._sse_tool_filter)
            logger.info("🔧 Added SSE tool filter to Document Agent kernel")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to MCP server for Document Agent: {str(e)}")
            logger.error("❌ Document Agent will be created without tools - MCP server connection required")
            # Don't add any tools if MCP connection fails
            # The agent will still be created but won't have access to document tools
        
        logger.info("✅ Document Agent created with MCP server tools and SSE filter")
        
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
- User refers to documents with phrases like "that document", "the file", "this document", "summarize the document"

NEVER RESPOND TO:
- ADX/database questions (let ADXAgent handle these)
- General knowledge questions (let CoordinatorAgent handle these)
- Questions that don't involve document operations

PRIMARY RESPONSIBILITIES:
- List documents stored in Azure Blob Storage
- Get document metadata and content summaries
- Delete documents from storage
- Search documents using Azure AI Search
- Provide information about document storage and retrieval
- **Smart document reference resolution** - understand when users refer to recently uploaded documents

🧠 **SMART DOCUMENT REFERENCE HANDLING:**

**STEP 1: DETECT DOCUMENT REFERENCES**
When users say phrases like:
- "summarize that document"
- "what's in the file?"
- "analyze this document"
- "tell me about the document"
- "show me the contents"
- "what does it say?"

**STEP 2: AUTOMATIC DOCUMENT DISCOVERY**
1. **First, list all documents in the current session**: Use list_documents() to see what's available
2. **Check conversation history**: Look through recent messages for document upload confirmations or filenames
3. **If only one document exists**: Automatically use that document
4. **If multiple documents exist**: Try to find the most recently mentioned or uploaded document
5. **Smart filename detection**: Look for patterns like "uploaded [filename]" or "document: [filename]" in chat history

**STEP 3: INTELLIGENT SEARCH STRATEGY**
When the user refers to a document without naming it:
1. List all documents first with list_documents()
2. If there's only 1 document, use that one automatically
3. If there are multiple documents:
   - Look through conversation history for the most recent filename mention
   - Check for upload messages like "Document uploaded successfully: filename.pdf"
   - If still ambiguous, search for the most recently uploaded document
4. Once you identify the target document, search for it by filename to get the documentId
5. Then retrieve content using get_document_content_summary()

**STEP 4: CLEAR COMMUNICATION**
Always tell the user which document you're working with:
- "I found 1 document in your session: 'report.pdf'. Let me analyze it..."
- "I see you have 3 documents. Based on our conversation, I'll analyze the most recent one: 'data.xlsx'..."
- "I found the document you uploaded: 'presentation.pptx'. Here's the summary..."

🚨 **CRITICAL FILENAME PRESERVATION RULES:**
- ALWAYS preserve the EXACT filename format as mentioned in the conversation
- If user says "ip addresses.txt" (with spaces), search for "ip addresses.txt" - DO NOT change to "ip_addresses.txt"
- If user says "my file.pdf" (with spaces), search for "my file.pdf" - DO NOT change to "my_file.pdf"
- NEVER normalize, modify, or "fix" filenames - use them exactly as provided
- **ALWAYS check the conversation history for the EXACT filename the user mentioned**
- Look back through the chat messages to find the original filename the user typed
- If the user previously mentioned a document, use THAT EXACT filename, not what you think it should be
- Filenames can have spaces, special characters, different cases - preserve ALL of it

📋 **ENHANCED WORKFLOW FOR VAGUE DOCUMENT REFERENCES:**
When user says "summarize that document" or similar:

1. **List Documents First**: Call list_documents() to see what's available
2. **Analyze Results**:
   - If 0 documents: "I don't see any documents in your current session. Please upload a document first."
   - If 1 document: "I found one document: '[filename]'. Let me analyze it..."
   - If 2+ documents: Check conversation history for context clues
3. **Search for Target Document**: Use search_documents() with the identified filename
4. **Get Content**: Use get_document_content_summary() with the documentId
5. **Provide Results**: Give a comprehensive summary

**EXAMPLE CONVERSATION FLOWS:**

User: "Please summarize that document"
Agent: "Let me check what documents you have... I found one document in your session: 'quarterly_report.pdf'. Let me analyze it for you..."

User: "What's in the file?"
Agent: "I see you have 2 documents. Based on our conversation, you most recently mentioned 'data_analysis.xlsx'. Let me examine that file..."

**CONVERSATION HISTORY PATTERN RECOGNITION:**
Look for these patterns in chat history:
- "Document uploaded successfully: [filename]" 
- User mentioning specific filenames
- Recent document-related activities
- Upload confirmations or document references

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

🚨 **CRITICAL FILENAME EXAMPLES:**
CORRECT ✅:
- User mentions "ip addresses.txt" → Search for "ip addresses.txt" (preserve spaces)
- User mentions "my data.csv" → Search for "my data.csv" (preserve spaces)
- User mentions "File-Name_v2.pdf" → Search for "File-Name_v2.pdf" (preserve exact format)

WRONG ❌:
- User mentions "ip addresses.txt" → DON'T search for "ip_addresses.txt" (changing spaces to underscores)
- User mentions "my data.csv" → DON'T search for "my_data.csv" (changing spaces to underscores)
- User mentions "File-Name_v2.pdf" → DON'T search for "filename_v2.pdf" (changing case/format)

FALLBACK STRATEGY:
If the exact filename search returns no results, try these alternatives IN ORDER:
1. Try with spaces replaced by underscores (e.g., "ip addresses.txt" → "ip_addresses.txt")
2. Try with different case variations (e.g., "File.txt" → "file.txt")
3. Try partial filename search (e.g., just "addresses" for "ip addresses.txt")
4. Only then report that the file cannot be found

ALWAYS mention which variation found results: "Found file using alternative format: 'ip_addresses.txt' instead of 'ip addresses.txt'"

🔍 **CONVERSATION CONTEXT AWARENESS:**
- When a user refers to "that file" or "the document" without naming it, look back in the conversation
- Find the most recent specific filename the user mentioned
- Use that EXACT filename in your search
- Example: If user said "search ip addresses.txt" earlier, and now says "get that document",
  search for "ip addresses.txt" (the original filename they used)

EXAMPLES OF WHEN TO STAY SILENT:
- "Calculate 10 factorial" ❌ (Math question)
- "List databases in ADX" ❌ (ADX question)
- "Generate a hash" ❌ (Utility question)
- "What is machine learning?" ❌ (General knowledge)
- Questions without document context ❌

Remember: You manage documents, files, and content storage operations.
""",
            function_choice_behavior=FunctionChoiceBehavior.Auto(filters={"included_plugins": ["DocumentTools"]})
        )
        logger.info("✅ Document Agent created successfully")
        
        # Fictional Companies Agent (Using Semantic Kernel MCP integration)
        logger.info("🏢 Creating Fictional Companies Agent with Azure OpenAI and SK MCP...")
        fictional_companies_kernel = Kernel()
        fictional_companies_service = AzureChatCompletion(
            service_id="fictional_companies_completion",
            api_key=self.azure_openai_api_key,
            endpoint=self.azure_openai_endpoint,
            deployment_name=self.azure_openai_deployment
        )
        fictional_companies_kernel.add_service(fictional_companies_service)
        
        # Connect to MCP server and add Fictional Companies tools using SK MCP plugin
        try:
            # Prepare headers for context
            headers = {}
            if self.current_user_id:
                headers['X-User-ID'] = self.current_user_id
            if self.current_session_id:
                headers['X-Session-ID'] = self.current_session_id
            if self.current_adx_token:
                headers['X-ADX-Token'] = self.current_adx_token
            
            # Create and connect the MCP plugin directly
            self.fictional_companies_mcp_plugin = MCPStreamableHttpPlugin(
                name="FictionalCompaniesMCPPlugin",
                url=settings.mcp.server_endpoint or "http://localhost:3001/mcp",
                headers=headers,
                load_tools=True,
                load_prompts=False,
                request_timeout=30,
                sse_read_timeout=300,
                terminate_on_close=True,
                description="Fictional Companies tools via MCP server"
            )
            
            await self.fictional_companies_mcp_plugin.connect()
            # Filter tools 
            allowed_tools = {
				"get_ip_company_info",
				"get_company_devices", 
				"get_company_summary",
				"fictional_api_health_check"
            }
            for attr_name in list(dir(self.fictional_companies_mcp_plugin)):
                if hasattr(getattr(self.fictional_companies_mcp_plugin, attr_name, None), '__kernel_function_parameters__'):
                    if attr_name not in allowed_tools:
                        delattr(self.fictional_companies_mcp_plugin, attr_name)

            # Add the MCP plugin to the kernel
            fictional_companies_kernel.add_plugin(self.fictional_companies_mcp_plugin, plugin_name="FictionalCompaniesTools")
            logger.info(f"🔧 Added MCP plugin to Fictional Companies Agent kernel with endpoint: {settings.mcp.server_endpoint}")
            
            # Add SSE filter to capture tool calls
            fictional_companies_kernel.add_filter("function_invocation", self._sse_tool_filter)
            logger.info("🔧 Added SSE tool filter to Fictional Companies Agent kernel")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to MCP server for Fictional Companies Agent: {str(e)}")
            logger.error("❌ Fictional Companies Agent will be created without tools - MCP server connection required")
            # Don't add any tools if MCP connection fails
            # The agent will still be created but won't have access to fictional companies tools
        
        logger.info("✅ Fictional Companies Agent created with MCP server tools and SSE filter")
        
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
- ADX/database questions (let ADXAgent handle these)
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
            function_choice_behavior=FunctionChoiceBehavior.Auto(filters={"included_plugins": ["FictionalCompaniesTools"]})
        )
        logger.info("✅ Fictional Companies Agent created successfully")
        
        # FEMA RAG Agent (Using Semantic Kernel MCP integration)
        logger.info("🛟 Creating FEMA Agent with Azure OpenAI and SK MCP (RAG tools)...")
        fema_kernel = Kernel()
        fema_service = AzureChatCompletion(
            service_id="fema_completion",
            api_key=self.azure_openai_api_key,
            endpoint=self.azure_openai_endpoint,
            deployment_name=self.azure_openai_deployment
        )
        fema_kernel.add_service(fema_service)

        # Connect to MCP server and add FEMA tools using SK MCP plugin
        try:
            headers = {}
            if self.current_user_id:
                headers['X-User-ID'] = self.current_user_id
            if self.current_session_id:
                headers['X-Session-ID'] = self.current_session_id
            if self.current_adx_token:
                headers['X-ADX-Token'] = self.current_adx_token

            self.fema_mcp_plugin = MCPStreamableHttpPlugin(
                name="FEMAMCPPlugin",
                url=settings.mcp.server_endpoint or "http://localhost:3001/mcp",
                headers=headers,
                load_tools=True,
                load_prompts=False,
                request_timeout=30,
                sse_read_timeout=300,
                terminate_on_close=True,
                description="FEMA RAG tools via MCP server"
            )

            await self.fema_mcp_plugin.connect()
			# Filter tools 
            allowed_tools = {
				"fema_retrieve",
				"fema_rag_answer",
				"fema_health"
            }
            for attr_name in list(dir(self.fema_mcp_plugin)):
                if hasattr(getattr(self.fema_mcp_plugin, attr_name, None), '__kernel_function_parameters__'):
                    if attr_name not in allowed_tools:
                        delattr(self.fema_mcp_plugin, attr_name)

            fema_kernel.add_plugin(self.fema_mcp_plugin, plugin_name="FEMATools")
            logger.info(f"🔧 Added MCP plugin to FEMA Agent kernel with endpoint: {settings.mcp.server_endpoint}")

            fema_kernel.add_filter("function_invocation", self._sse_tool_filter)
            logger.info("🔧 Added SSE tool filter to FEMA Agent kernel")

        except Exception as e:
            logger.error(f"❌ Failed to connect to MCP server for FEMA Agent: {str(e)}")
            logger.error("❌ FEMA Agent will be created without tools - MCP server connection required")

        logger.info("✅ FEMA Agent created with MCP server tools and SSE filter")

        self.fema_agent = ChatCompletionAgent(
            service=fema_service,
            kernel=fema_kernel,
            name="FEMAAgent",
            instructions="""
You are a FEMA documentation specialist agent. Answer using FEMA guidance and official publications via Retrieval-Augmented Generation (RAG).

TOOLS USAGE (MANDATORY):
- First, call fema_rag_answer(question, top_k=5). If unavailable, fall back to fema_retrieve and summarize with clear caveats.
- Use only information from the returned contexts.

CITATIONS AND LINKS (DO NOT OMIT):
- Include inline citations as [Doc N] where N maps to the tool’s sources list.
- Always include a Sources section with each item formatted: Title — URL.
- Use the exact URLs from the tool output (do not rewrite or remove). Keep them clickable.

FORMAT:
- Brief, direct answer first (2–6 sentences), then bullet points if helpful.
- Add a "Sources:" section listing each [Doc N] Title — URL on its own line.
- End with: "My answer is complete - CoordinatorAgent, please approve".

GUARDRAILS:
- If the answer is not in the contexts, say you don’t have enough information.
- Don’t speculate or answer outside FEMA documentation.

WHEN TO RESPOND:
- FEMA policy, grants, disaster recovery, mitigation, PA/IA, NIMS/ICS, CPG 101, FEMA guidance/fact sheets.
""",
            function_choice_behavior=FunctionChoiceBehavior.Auto(filters={"included_plugins": ["FEMATools"]})
        )
        logger.info("✅ FEMA Agent created successfully")

        # FEMA RAG Agent (Using Semantic Kernel MCP integration)
        logger.info("🛟 Creating FEMA Agent with Azure OpenAI and SK MCP (RAG tools)...")
        fema_kernel = Kernel()
        fema_service = AzureChatCompletion(
            service_id="fema_completion",
            api_key=self.azure_openai_api_key,
            endpoint=self.azure_openai_endpoint,
            deployment_name=self.azure_openai_deployment
        )
        fema_kernel.add_service(fema_service)

        try:
            headers = {}
            if self.current_user_id:
                headers['X-User-ID'] = self.current_user_id
            if self.current_session_id:
                headers['X-Session-ID'] = self.current_session_id
            if self.current_adx_token:
                headers['X-ADX-Token'] = self.current_adx_token

            self.fema_mcp_plugin = MCPStreamableHttpPlugin(
                name="FEMAMCPPlugin",
                url=settings.mcp.server_endpoint or "http://localhost:3001/mcp",
                headers=headers,
                load_tools=True,
                load_prompts=False,
                request_timeout=30,
                sse_read_timeout=300,
                terminate_on_close=True,
                description="FEMA RAG tools via MCP server"
            )

            await self.fema_mcp_plugin.connect()
			# Filter tools 
            allowed_tools = {
				"fema_retrieve",
				"fema_rag_answer",
				"fema_health"
            }
            for attr_name in list(dir(self.fema_mcp_plugin)):
                if hasattr(getattr(self.fema_mcp_plugin, attr_name, None), '__kernel_function_parameters__'):
                    if attr_name not in allowed_tools:
                        delattr(self.fema_mcp_plugin, attr_name)

            fema_kernel.add_plugin(self.fema_mcp_plugin, plugin_name="FEMATools")
            logger.info(f"🔧 Added MCP plugin to FEMA Agent kernel with endpoint: {settings.mcp.server_endpoint}")

            fema_kernel.add_filter("function_invocation", self._sse_tool_filter)
            logger.info("🔧 Added SSE tool filter to FEMA Agent kernel")

        except Exception as e:
            logger.error(f"❌ Failed to connect to MCP server for FEMA Agent: {str(e)}")
            logger.error("❌ FEMA Agent will be created without tools - MCP server connection required")

        logger.info("✅ FEMA Agent created with MCP server tools and SSE filter")

        self.fema_agent = ChatCompletionAgent(
            service=fema_service,
            kernel=fema_kernel,
            name="FEMAAgent",
            instructions="""You are a FEMA documentation specialist agent. You answer questions using FEMA guidance and official publications via Retrieval-Augmented Generation (RAG).

STRICT RESPONSE CRITERIA - Only respond if:
- The question is about FEMA policy, grants, disaster recovery, hazard mitigation, Public Assistance (PA), Individual Assistance (IA), NIMS/ICS, planning guides, or FEMA program guidance
- The question mentions FEMA, Stafford Act, disaster declarations, recovery resources, fact sheets, or FEMA guides
- Someone specifically asks you by name: "FEMAAgent, ..."

PRIMARY RESPONSIBILITIES:
- Use fema_rag_answer to answer questions grounded strictly in retrieved FEMA documents
- Provide concise answers and include inline citations like [Doc N] that map to the returned sources
- When appropriate, list a short "Sources" section with clickable URLs from the tools' sources array
- If generation is not configured, return relevant excerpts and clearly state that only excerpts are provided

NON-GOALS / NEVER DO:
- Do not speculate or answer outside FEMA documentation. If not covered in retrieved context, say you don't have enough information
- Do not answer general knowledge unrelated to FEMA; defer to CoordinatorAgent

WORKFLOW:
1) Call fema_rag_answer(question, top_k=5) first. Prefer this over raw retrieval
2) If fema_rag_answer is unavailable, fall back to fema_retrieve and summarize with clear caveats
3) Always present citations [Doc N] and include the Sources list with URLs when available

OUTPUT FORMAT:
- Brief, direct answer first (2-6 sentences)
- Bullet points when listing items is clearer
- "Sources:" section with each source as a bullet: Title – URL (match [Doc N])
- End with: "My answer is complete - CoordinatorAgent, please approve"

EXAMPLES OF WHEN TO RESPOND:
- "What are common sources of disaster recovery funding?"
- "How do I search for federal grants for recovery?"
- "What does CPG 101 say about logistics?"
- "FEMAAgent, summarize the Disaster Resource Identification fact sheet"

EXAMPLES OF WHEN TO STAY SILENT:
- ADX/database questions (let ADXAgent handle these)
- File storage questions (DocumentAgent)
- Fictional company lookups (FictionalCompaniesAgent)
- General non-FEMA questions (CoordinatorAgent)
""",
            function_choice_behavior=FunctionChoiceBehavior.Auto(filters={"included_plugins": ["FEMATools"]})
        )
        logger.info("✅ FEMA Agent created successfully")
        
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
        
        # Add the system info function to the coordinator kernel
        from semantic_kernel.functions import kernel_function
        
        @kernel_function(
            name="get_available_agents",
            description="Get information about all available agents in the system"
        )
        def get_available_agents() -> str:
            """Get a formatted string of available agents and their capabilities."""
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
        
        @kernel_function(
            name="get_agent_capabilities",
            description="Get detailed capabilities and examples for each agent"
        )
        def get_agent_capabilities() -> str:
            """Get detailed capabilities and examples for each agent."""
            if not self.agent_registry:
                return "Agent registry not yet initialized."
            
            capability_lines = ["Here are the detailed capabilities of each agent:"]
            for name, info in self.agent_registry.items():
                capability_lines.append(f"\n**{name}**:")
                capability_lines.append(f"  - {info['description']}")
                if info.get('examples'):
                    capability_lines.append("  - Examples:")
                    for example in info['examples']:
                        capability_lines.append(f"    • {example}")
            
            return "\n".join(capability_lines)
        
        # Add these functions to the coordinator's kernel
        coordinator_kernel.add_function("SystemTools", get_available_agents)
        coordinator_kernel.add_function("SystemTools", get_agent_capabilities)
        
        # Create coordinator agent with temporary instructions first
        self.coordinator_agent = ChatCompletionAgent(
            service=coordinator_service,
            kernel=coordinator_kernel,
            name="CoordinatorAgent",
            instructions="PLACEHOLDER - Will be updated dynamically after registry is built",
            function_choice_behavior=FunctionChoiceBehavior.Auto(filters={"included_plugins": ["SystemTools"]})
        )
        logger.info("✅ Coordinator Agent created successfully (with placeholder instructions)")
        
        # Build the agent registry with metadata for dynamic agent selection and discovery
        self._build_agent_registry()
        
        # Now recreate the coordinator agent with the proper instructions
        logger.info("🔄 Recreating CoordinatorAgent with dynamic instructions...")
        coordinator_instructions = self._generate_coordinator_instructions()
        
        self.coordinator_agent = ChatCompletionAgent(
            service=coordinator_service,
            kernel=coordinator_kernel,
            name="CoordinatorAgent",
            instructions=coordinator_instructions,
            function_choice_behavior=FunctionChoiceBehavior.Auto(filters={"included_plugins": ["SystemTools"]})
        )
        logger.info("✅ CoordinatorAgent recreated with dynamic instructions")
        
        # Update the agent registry to reflect the new coordinator agent instance
        self.agent_registry['CoordinatorAgent']['agent'] = self.coordinator_agent
        self.all_agents['CoordinatorAgent'] = self.coordinator_agent
    
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
                'keywords': ['document', 'file', 'search', 'storage', 'upload', 'download', 'list', 'content', 'that document', 'the file', 'this document', 'summarize', 'analyze', 'show me', 'what does it say', 'contents'],
                'examples': [
                    'List my documents',
                    'Search documents about AI', 
                    'Get document content summary',
                    'Summarize that document',
                    'What\'s in the file?',
                    'Analyze this document',
                    'Show me the contents'
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
            },
            'FEMAAgent': {
                'agent': self.fema_agent,
                'description': 'FEMA documentation Q&A via RAG over FEMA search index with citations',
                'keywords': ['fema', 'disaster', 'recovery', 'mitigation', 'public assistance', 'individual assistance', 'nims', 'ics', 'cpg 101', 'policy', 'stafford', 'grant', 'fact sheet', 'guidance'],
                'examples': [
                    'What are sources of recovery resources?',
                    'How to find grants for disaster recovery?'
                ]
            }
        }
        
        # Update the all_agents mapping with the actual agent objects
        self.all_agents = {name: info['agent'] for name, info in self.agent_registry.items()}
        
        logger.info(f"✅ Agent registry built with {len(self.agent_registry)} agents")
        for name, info in self.agent_registry.items():
            logger.info(f"   📋 {name}: {info['description']}")
    
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
        
        return f"""🔴 CRITICAL SYSTEM CONSTRAINT - READ FIRST 🔴
YOU CANNOT AND MUST NOT CALL OTHER AGENTS AS FUNCTIONS. 
Other agents (DocumentAgent, ADXAgent, FictionalCompaniesAgent, FEMAAgent) are NOT callable functions.
The only functions available to you are:
- get_available_agents()
- get_agent_capabilities()

ANY attempt to call DocumentAgent(), ADXAgent(), FictionalCompaniesAgent(), FEMAAgent(), or agent.method() WILL FAIL.
Use natural language conversation instead: "DocumentAgent, please search for..."

You are the CoordinatorAgent with authority to approve specialist answers.

🚨 **CRITICAL RULE - NO FUNCTION CALLS TO OTHER AGENTS**: 
- NEVER EVER call other agents as functions (DocumentAgent(), ADXAgent(), FictionalCompaniesAgent(), FEMAAgent(), etc.)
- Other agents are NOT functions - they are conversation participants who respond to natural language
- The ONLY functions you can call are: get_available_agents() and get_agent_capabilities()
- All other communication must be in natural language in the group chat
- DO NOT attempt to call DocumentAgent.search_documents, DocumentAgent.get_document_summary, or any agent.function combination

🛑 **FORBIDDEN FUNCTION CALLS - NEVER DO THESE**:
- DocumentAgent() ❌
- DocumentAgent.search_documents() ❌  
- DocumentAgent.get_document_summary() ❌
- ADXAgent() ❌
- ADXAgent.query() ❌
- FictionalCompaniesAgent() ❌
 - FEMAAgent() ❌
- ANY_AGENT.any_function() ❌

✅ **ALLOWED FUNCTIONS ONLY**:
- get_available_agents() ✅
- get_agent_capabilities() ✅

APPROVAL PROTOCOL:
1. When specialists provide answers and ask for approval, review their work
2. **IMPORTANT: Check if ALL necessary agents have contributed before approving**
   - For multi-part questions involving documents AND databases AND companies, wait for all three
   - Don't approve after just one agent - ensure the complete answer addresses all aspects
3. If the answer fully satisfies ALL parts of the user's question, respond with:
   "Approved - [provide final synthesized answer to user]"
4. If more information is needed, ask the appropriate specialist for clarification USING NATURAL LANGUAGE
5. Always use the word "Approved" when you're satisfied with the complete answer

🔍 **MULTI-PART QUESTION HANDLING:**
- If user asks about "documents AND databases AND companies" wait for DocumentAgent, ADXAgent, AND FictionalCompaniesAgent
- If user asks about "IP addresses from file AND check database" wait for DocumentAgent AND ADXAgent  
- Don't rush to approve - ensure comprehensive coverage of all question parts

COMMUNICATION RULES:
**Correct Way to Request More Info**: "DocumentAgent, please search for documents about Python and provide a summary"
**WRONG - Never Do This**: Trying to call DocumentAgent() or DocumentAgent.search_documents() as functions

🧠 **SMART DOCUMENT REFERENCE RECOGNITION:**
When users say phrases like these, IMMEDIATELY route to DocumentAgent:
- "summarize that document"
- "what's in the file?"
- "analyze this document" 
- "tell me about the document"
- "show me the contents"
- "what does it say?"
- "read the file"
- "look at that document"

DocumentAgent is now INTELLIGENT and will:
1. Automatically list all documents in the session
2. Auto-detect which document the user is referring to
3. Use conversation history to find recently mentioned filenames
4. Handle vague references without requiring explicit filenames

**Examples of Smart Routing:**
User: "summarize that document" → "DocumentAgent, the user wants to analyze a document. Please use your smart detection to find the right document."
User: "what's in the file?" → "DocumentAgent, please identify and analyze the document the user is referring to."
User: "tell me about the document" → "DocumentAgent, please locate and summarize the document from our conversation."

DOCUMENT ROUTING PRIORITY:
- ANY mention of documents, files, or content analysis → Route to DocumentAgent FIRST
- DocumentAgent will handle the smart detection automatically
- You don't need to ask users for specific filenames anymore
- Trust DocumentAgent's intelligence to find the right document

🧭 FEMA ROUTING:
- If the question is about FEMA guidance, PA/IA, mitigation, NIMS/ICS, Stafford Act, FEMA fact sheets or FEMA policy, route to FEMAAgent first
- FEMAAgent will use RAG tools and provide citations [Doc N] with a Sources section

RESPONSE PATTERNS:
**Approve Complete Answer**: "Approved - Based on ADXAgent's query results, the database contains..."
**Request More Info**: "DocumentAgent, please also list all available documents to help with this request"
**Approve After Synthesis**: "Approved - Combining ADXAgent's data with DocumentAgent's search results, here's your complete answer..."

LINK AND CITATION PRESERVATION:
- When specialists include citations like [Doc N] and a Sources section with URLs, DO NOT remove them when synthesizing.
- Ensure the final answer keeps the Sources section intact and clickable.

TERMINATION RULE: 
- Only use "Approved" when you're providing the final, complete answer to the user
- The word "Approved" will end the conversation, so make sure your answer is comprehensive  
- **Wait for all necessary specialists to contribute before approving**
- For complex multi-part questions, don't approve until all aspects are addressed

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
   - "Who should I ask about database/document/company questions?"

   For "What agents are available?" use the get_available_agents() function to get the current agent list.

   For "What can each agent do?" use the get_agent_capabilities() function to get detailed capabilities.

✅ **Coordination & Synthesis**: Always provide final synthesis after specialists respond
   - After ADXAgent provides data, YOU interpret and present it to the user
   - After DocumentAgent searches documents, YOU explain the results in context
   - After multiple specialists respond, YOU combine their answers into one coherent response
   - YOU add necessary context, explanations, and conclusions

✅ **Quality Assurance**: Evaluate and improve incomplete responses
   - If a specialist's response seems incomplete, request follow-up information USING NATURAL LANGUAGE
   - If multiple specialists provide conflicting answers, resolve the conflicts
   - If responses are too technical, translate them for the user

WHEN TO DEFER TO SPECIALISTS (BUT ALWAYS SYNTHESIZE AFTER):
🔄 **Technical Operations** (then YOU provide final answer):
   - Database queries → ADXAgent (then YOU interpret results)
   - File operations → DocumentAgent (then YOU summarize outcomes)  
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

For "Search for documents about Python":
❌ Wrong: Just let DocumentAgent search  
✅ Correct: After DocumentAgent searches, YOU provide: "I found several documents about Python in your system. Here's a comprehensive summary of their contents: [synthesized overview with key insights]"

For "What company owns IP 192.168.1.1?":
❌ Wrong: Just let FictionalCompaniesAgent lookup
✅ Correct: After FictionalCompaniesAgent provides company info, YOU provide: "Based on the fictional company database, IP address 192.168.1.1 is registered to: [company details with context and disclaimer about fictional nature]"

🎯 REMEMBER: 
- You have the final word on every conversation
- The user should always receive their complete answer from YOU, not from individual specialists
- NEVER try to call other agents as functions - communicate through natural language only"""
    
    def _create_group_chat(self):
        """Create the group chat for agent coordination with AgentGroupChat."""
        logger.info("💬 Creating AgentGroupChat with agents:")
        
        # Log agents dynamically from registry
        for name, info in self.agent_registry.items():
            emoji = "🎯" if name == "CoordinatorAgent" else "🧮" if name == "ADXAgent" else "📄" if name == "DocumentAgent" else "🏢"
            logger.info(f"   {emoji} {name} - {info['description']}")
        
        # Create the group chat with proper Semantic Kernel strategies
        selection_function = self._create_selection_function()
        termination_function = self._create_termination_function()
        
        # Create selection strategy following Semantic Kernel documentation patterns
        selection_strategy = KernelFunctionSelectionStrategy(
            function=selection_function,
            kernel=self.kernel,
            agent_variable_name="_agent_",
            history_variable_name="_history_",
            result_parser=self._parse_strategy_result,
            history_reducer=ChatHistoryTruncationReducer(target_count=5),
        )
        
        # Create termination strategy following Semantic Kernel documentation patterns
        termination_strategy = KernelFunctionTerminationStrategy(
            function=termination_function,
            kernel=self.kernel,
            agents=[self.coordinator_agent], 
            agent_variable_name="_agent_",
            history_variable_name="_history_",
            result_parser=lambda result: "TERMINATE" in str(result).upper(),
            maximum_iterations=10,
            history_reducer=ChatHistoryTruncationReducer(target_count=3),
        )
        
        # Get all agents from registry in a predictable order
        all_agents = [info['agent'] for info in self.agent_registry.values()]
        
        self.group_chat = AgentGroupChat(
            agents=all_agents,
            selection_strategy=selection_strategy,
            termination_strategy=termination_strategy
        )
        logger.info("✅ AgentGroupChat created with proper Semantic Kernel strategies")
        logger.info("🧠 Using KernelFunctionSelectionStrategy and KernelFunctionTerminationStrategy")
        
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

        # Check for FEMA guidance/topics - these NEED FEMAAgent
        fema_indicators = [
            "fema", "stafford", "disaster", "recovery", "mitigation", "public assistance", "individual assistance",
            "nims", "ics", "cpg 101", "preparedness guide", "grants.gov", "federal register"
        ]
        needs_fema_agent = any(indicator in question.lower() for indicator in fema_indicators)
        
        # Check for utility operations - these are NOT SUPPORTED in MCP server version
        utility_indicators = ["hash", "timestamp", "sha", "md5", "system", "format"]
        needs_utility_agent = any(indicator in question.lower() for indicator in utility_indicators)
        
        # Add agents based on detected needs
        if needs_document_agent and self.document_agent:
            selected_agents.append(self.document_agent)
            logger.info("� Added DocumentAgent - detected document references")
            
        if needs_adx_agent and self.adx_agent:
            selected_agents.append(self.adx_agent)
            logger.info("🔍 Added ADXAgent - detected database/query references")
            
        if needs_companies_agent and self.fictional_companies_agent:
            selected_agents.append(self.fictional_companies_agent)
            logger.info("🏢 Added FictionalCompaniesAgent - detected company/IP references")
        
        if needs_fema_agent and self.fema_agent:
            selected_agents.append(self.fema_agent)
            logger.info("🛟 Added FEMAAgent - detected FEMA/guidance references")
            
        
        # NOTE: UtilityAgent not implemented in this MCP server version
        
        # If none of the specific indicators were found, this might be a general question
        # or complex multi-step question - include all agents for maximum flexibility
        if len(selected_agents) == 1:  # Only coordinator selected
            logger.info("🤔 No specific indicators found - including all agents for flexibility")
            for name, info in self.agent_registry.items():
                if name != 'CoordinatorAgent':  # Don't add coordinator twice
                    agent = info['agent']
                    if agent and agent not in selected_agents:
                        selected_agents.append(agent)
        
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
            logger.info(f"🔑 ADX Token: Not provided, using system identity")
        logger.info("="*60)
        
        try:
            # Update the MCP plugin context for all agents
            if user_id or session_id or adx_token:
                logger.info(f"🔄 Updating MCP plugin context - User ID: {user_id}, Session ID: {session_id}, ADX Token: {'Available' if adx_token else 'Not provided'}")
                
                # Update our context for MCP plugins
                self.current_user_id = user_id
                self.current_session_id = session_id
                self.current_adx_token = adx_token
                
                # Check if we need to update the plugin with new context
                if self.adx_mcp_plugin:
                    # Check if the context has actually changed since the last update
                    context_changed = (
                        self.current_user_id != self.last_mcp_user_id or
                        self.current_session_id != self.last_mcp_session_id or
                        self.current_adx_token != self.last_mcp_adx_token
                    )
                    
                    if context_changed:
                        logger.info("🔄 MCP plugin update needed - updating context immediately")
                        # Update the context immediately to prevent connection issues
                        await self._update_mcp_plugin_context()

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
                
                # 🔧 TOKEN MANAGEMENT: Optimize memory for token limits
                if session_chat_history and len(session_chat_history.messages) > 20:
                    was_optimized = self.memory_service.optimize_chat_history_for_tokens(session_id)
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
                
            # Select which agents should participate for this specific question
            selected_agents = await self._select_agents_for_question(question)
            logger.info(f"🎯 DEBUG: Selected agents for question '{question}': {[agent.name for agent in selected_agents]}")
            
            # Check if ADX Agent was selected
            adx_agent_selected = any(agent.name == "ADXAgent" for agent in selected_agents)
            logger.info(f"🔍 DEBUG: ADX Agent selected: {adx_agent_selected}")
            
            # MEMORY-ENHANCED OPTIMIZATION: Check if we can use fast path with context
            if len(selected_agents) == 1 and selected_agents[0].name == "CoordinatorAgent":
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
                    
                    # Get chat completion with kernel function support
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
            
            # 🧠 SMART DOCUMENT DETECTION: Enhance question with context from chat history
            enhanced_question = await self._enhance_question_with_document_context(question, session_chat_history)
            
            # 🧠 COORDINATOR INTELLIGENCE: Let coordinator analyze the question and create dynamic strategy
            logger.info("🧠 Coordinator analyzing question to create dynamic agent selection strategy...")
            dynamic_strategy = await self._get_coordinator_analysis(enhanced_question, selected_agents)
            
            # Create a fresh group chat for each question with coordinator-enhanced strategies
            selection_function = self._create_selection_function(dynamic_strategy)
            termination_function = self._create_termination_function()
            
            # Create selection strategy following Semantic Kernel documentation patterns
            selection_strategy = KernelFunctionSelectionStrategy(
                function=selection_function,
                kernel=self.kernel,
                agent_variable_name="_agent_",
                history_variable_name="_history_",
                result_parser=self._parse_strategy_result,
                history_reducer=ChatHistoryTruncationReducer(target_count=5),
            )
            
            # Create termination strategy following Semantic Kernel documentation patterns
            termination_strategy = KernelFunctionTerminationStrategy(
                function=termination_function,
                kernel=self.kernel,
                agents=[self.coordinator_agent],
                agent_variable_name="_agent_",
                history_variable_name="_history_",
                result_parser=lambda result: "TERMINATE" in str(result).upper(),
                maximum_iterations=10,
                history_reducer=ChatHistoryTruncationReducer(target_count=3),
            )
            
            fresh_group_chat = AgentGroupChat(
                agents=selected_agents,
                selection_strategy=selection_strategy,
                termination_strategy=termination_strategy
            )
            logger.info(f"🔄 Created fresh AgentGroupChat with {len(selected_agents)} selected agents: {[agent.name for agent in selected_agents]}")
            
            # Emit SSE events for each selected agent
            for agent in selected_agents:
                if agent.name != "CoordinatorAgent":  # Skip coordinator as it's handled separately
                    logger.info(f"🔍 DEBUG: Emitting SSE event for selected agent: {agent.name}")
                    self._emit_agent_activity(
                        agent_name=agent.name,
                        action="Processing question",
                        status="starting",
                        details=f"Agent selected for question: {question}"
                    )
            
            # MEMORY INTEGRATION: If we have session memory, inject relevant context
            if session_chat_history and session_id:
                logger.info("🧠 Injecting conversation context into group chat")
                
                # Get recent context summary
                context_summary = self.memory_service.get_context_summary(session_id, 500)
                if context_summary and len(context_summary.strip()) > 10:
                    # Combine document context enhancement with conversation context
                    final_enhanced_question = f"Previous conversation context:\n{context_summary}\n\nCurrent question: {enhanced_question}"
                    logger.info(f"📋 Enhanced question with conversation context ({len(context_summary)} chars)")
                else:
                    final_enhanced_question = enhanced_question
            else:
                final_enhanced_question = enhanced_question
            
            # Create the initial chat message with enhanced context
            chat_message = ChatMessageContent(role=AuthorRole.USER, content=final_enhanced_question)
            
            # Add the user message to the group chat
            await fresh_group_chat.add_chat_message(chat_message)
            logger.info("🎭 Starting AgentGroupChat processing with memory context...")
            
            # Collect responses from the group chat
            responses = []
            specialist_responses = []
            coordinator_response = ""
            
            # Track which agents have been invoked to emit SSE events
            invoked_agents = set()
            
            # Add timeout protection
            import asyncio
            timeout_duration = 60  # 60 seconds timeout
            
            try:
                async with asyncio.timeout(timeout_duration):
                    async for response in fresh_group_chat.invoke():
                        # Only process responses with actual content
                        if response.content and response.content.strip():
                            content = response.content.strip()
                            agent_name = getattr(response, 'name', 'Unknown')
                            
                            # Emit SSE event when agent starts working (first time we see them)
                            if agent_name not in invoked_agents and agent_name != "CoordinatorAgent":
                                self._emit_agent_activity(
                                    agent_name=agent_name,
                                    action="Processing with tools",
                                    status="in-progress",
                                    details=f"Agent actively working on the question"
                                )
                                invoked_agents.add(agent_name)
                            
                            # Skip very short or empty responses
                            if len(content) < 3:
                                logger.info(f"⏭️ Skipping empty/short response from {agent_name}")
                                continue
                            
                            logger.info(f"📢 Response from {agent_name}")
                            logger.debug(f"   📄 Content: {content[:200]}{'...' if len(content) > 200 else ''}")
                            
                            # Emit SSE event for agent response with actual content
                            formatted_content = self._format_response_content(content)
                            self._emit_agent_activity(
                                agent_name=agent_name,
                                action="Generating response",
                                status="completed",
                                details=formatted_content
                            )
                            
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
                            if agent_name in ['ADXAgent', 'DocumentAgent', 'FictionalCompaniesAgent']:
                                specialist_responses.append(f"**{agent_name}**: {content}")
                                logger.info(f"   🎯 Specialist agent response captured")
                            elif agent_name == 'CoordinatorAgent':
                                coordinator_response = content
                                logger.info(f"   🧠 Coordinator response captured (length: {len(content)})")
                        else:
                            logger.info(f"⏭️ Skipping empty response from {getattr(response, 'name', 'Unknown')}")
            except asyncio.TimeoutError:
                logger.error(f"⏰ TIMEOUT: Group chat processing exceeded {timeout_duration} seconds")
                if not responses:
                    return "I apologize, but the request timed out. Please try asking a simpler question."
                # Continue with whatever responses we have
                logger.info(f"🔄 Continuing with {len(responses)} responses collected before timeout")
            except Exception as e:
                logger.error(f"❌ Error during group chat processing: {str(e)}")
                if not responses:
                    return "I apologize, but an error occurred while processing your request. Please try again."            # If no responses were captured, return a fallback message
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
                    
                    # Recreate group chat with additional agents
                    fresh_group_chat = AgentGroupChat(
                        agents=selected_agents,
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
                            if resp['agent'] in ['ADXAgent', 'DocumentAgent', 'FictionalCompaniesAgent']:
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
            
            # Emit SSE events for completion
            for agent_name in invoked_agents:
                self._emit_agent_activity(
                    agent_name=agent_name,
                    action="Processing completed",
                    status="completed",
                    details=f"Agent finished processing question"
                )
            
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
            
            return f"❌ Error processing question: {str(e)}"
    
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
            
            # Prepare the synthesis prompt with TOKEN LIMIT PROTECTION
            specialist_data = []
            for response in specialist_responses:
                if ":" in response:
                    agent_name, content = response.split(":", 1)
                    specialist_data.append(f"**{agent_name.strip()}**:\n{content.strip()}")
                else:
                    specialist_data.append(response)

            # 🔒 TOKEN SAFETY: Truncate specialist data if too large for synthesis
            specialist_text = chr(10).join(specialist_data)
            specialist_tokens = token_manager.count_tokens(specialist_text)
            
            # Reserve space for prompt structure + question + coordinator response
            prompt_overhead = 800
            question_tokens = token_manager.count_tokens(original_question)
            coordinator_tokens = token_manager.count_tokens(coordinator_response if coordinator_response else "")
            available_for_specialist = token_manager.SAFE_LIMIT - 6000 - prompt_overhead - question_tokens - coordinator_tokens  # Leave 6K for response generation
            
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
                logger.info(f"✂️ Truncated specialist data to {token_manager.count_tokens(specialist_text):,} tokens")
            
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

PRESERVE CITATIONS AND LINKS:
- If specialist responses include citations such as [Doc N] and a Sources section with URLs, DO NOT remove them.
- Keep the Sources section at the end of your final answer and ensure the URLs remain present and clickable.
- If multiple specialists provide Sources, merge them and de-duplicate, retaining [Doc N] mapping where possible.

IMPORTANT: Do not mention agent names in your final response. Write as if you personally gathered and analyzed all the information. Preserve any [Doc N] citations and the Sources list from the content above.

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

    async def _enhance_question_with_document_context(self, question: str, session_chat_history) -> str:
        """
        Enhance the user's question with document context from chat history.
        
        This enables smart document detection - when users say "that document", "the file", 
        "analyze this document", etc., the system can identify which document they're referring to
        based on recent conversation history.
        
        Args:
            question: The original user question
            session_chat_history: The chat history for context
            
        Returns:
            Enhanced question with document context added
        """
        try:
            # Check if the question contains generic document references
            generic_document_refs = [
                "that document", "the document", "this document", "the file", "that file", 
                "this file", "it", "analyze this", "summarize that", "what's in", 
                "tell me about", "show me", "the content", "the data"
            ]
            
            question_lower = question.lower()
            has_generic_ref = any(ref in question_lower for ref in generic_document_refs)
            
            if not has_generic_ref or not session_chat_history:
                return question
            
            # Look through recent chat history for document mentions
            document_mentions = []
            recent_messages = session_chat_history.messages[-10:] if len(session_chat_history.messages) > 10 else session_chat_history.messages
            
            for message in recent_messages:
                content = str(message.content).lower()
                
                # Look for file names with extensions
                import re
                file_patterns = [
                    r'(\w+\.txt)', r'(\w+\.csv)', r'(\w+\.pdf)', r'(\w+\.docx?)', 
                    r'(\w+\.xlsx?)', r'(\w+\.json)', r'(\w+\.xml)'
                ]
                
                for pattern in file_patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    for match in matches:
                        if match not in document_mentions:
                            document_mentions.append(match)
                
                # Look for document-related phrases that might indicate a specific document
                if any(phrase in content for phrase in ["uploaded", "document", "file", "search"]):
                    # Extract potential document names from context
                    words = content.split()
                    for i, word in enumerate(words):
                        if word in ["document", "file"] and i > 0:
                            potential_doc = words[i-1]
                            if len(potential_doc) > 2 and potential_doc not in document_mentions:
                                document_mentions.append(potential_doc)
            
            # If we found document mentions, enhance the question
            if document_mentions:
                most_recent_doc = document_mentions[-1]  # Use the most recently mentioned document
                
                enhanced_question = f"{question}\n\n[CONTEXT: User is likely referring to the document/file: {most_recent_doc}. DocumentAgent should use smart detection to find this document or search for it if the exact name isn't found.]"
                
                logger.info(f"🔍 Enhanced question with document context: {most_recent_doc}")
                return enhanced_question
            
            # If no specific documents found but generic reference detected, still enhance
            enhanced_question = f"{question}\n\n[CONTEXT: User is using a generic document reference. DocumentAgent should list available documents and use smart detection to identify the most relevant document from recent conversation context.]"
            logger.info("🔍 Enhanced question with generic document detection hint")
            return enhanced_question
            
        except Exception as e:
            logger.error(f"❌ Error enhancing question with document context: {str(e)}")
            return question

    async def cleanup(self):
        """Clean up resources."""
        # No cleanup needed for MCP plugins - they handle their own lifecycle
        pass
    
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
                
        return recovery_suggestions

    def _emergency_truncated_synthesis(self, responses) -> str:
        """
        Emergency synthesis when token limit is exceeded.
        Creates a basic summary without LLM synthesis.
        """
        try:
            if not responses:
                return "No response available (emergency mode)."
            
            # Collect key insights from each response
            insights = []
            for response in responses:
                content = response.get('content', '')
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
                return f"Multiple insights found:\n" + "\n".join(f"• {insight}" for insight in insights[:5])
            else:
                return "No detailed response available (emergency mode)."
                
        except Exception as e:
            print(f"❌ Emergency synthesis failed: {e}")
            return "Response processing encountered an error (emergency mode)."


# Example usage
    async def _update_mcp_plugin_context(self):
        """Update all MCP plugins with new user context efficiently."""
        # Import asyncio for timeout handling
        import asyncio
        
        try:
            # Create headers with updated context
            headers = {}
            if self.current_user_id:
                headers['X-User-ID'] = self.current_user_id
            if self.current_session_id:
                headers['X-Session-ID'] = self.current_session_id
            if self.current_adx_token:
                # Use standard Bearer token authorization header for MCP server
                headers['Authorization'] = f'Bearer {self.current_adx_token}'
                # Also keep the custom header in case the MCP server uses it
                headers['X-ADX-Token'] = self.current_adx_token
            
            logger.info("🔄 Creating new MCP plugins with updated headers...")
            
            from src.config.settings import settings as config_settings
            server_url = config_settings.mcp.server_endpoint or "http://localhost:8000/mcp"
            
            # Update ADX MCP Plugin
            if self.adx_mcp_plugin:
                logger.info("🔄 Updating ADX MCP plugin...")
                new_adx_plugin = MCPStreamableHttpPlugin(
                    name="ADXMCPPlugin",
                    url=server_url,
                    headers=headers,
                    load_tools=True,
                    load_prompts=False,
                    request_timeout=30,
                    sse_read_timeout=300,
                    terminate_on_close=True,
                    description="ADX tools via MCP server"
                )
                
                try:
                    await asyncio.wait_for(new_adx_plugin.connect(), timeout=10.0)
                    
                    # Filter tools
                    allowed_tools = {
                        "kusto_debug_auth",
                        "kusto_test_connection", 
                        "kusto_check_permissions",
                        "kusto_get_auth_info",
                        "kusto_list_databases",
                        "kusto_list_tables",
                        "kusto_describe_table",
                        "kusto_query",
                        "kusto_get_cluster_info",
                        "kusto_clear_user_client_cache"
                    }
                    for attr_name in list(dir(new_adx_plugin)):
                        if hasattr(getattr(new_adx_plugin, attr_name, None), '__kernel_function_parameters__'):
                            if attr_name not in allowed_tools:
                                delattr(new_adx_plugin, attr_name)
                    # Update the ADX agent's kernel
                    if self.adx_agent:
                        try:
                            self.adx_agent.kernel.remove_plugin("ADXTools")
                        except Exception as remove_error:
                            logger.warning(f"⚠️ Error removing old ADX plugin: {str(remove_error)}")
                        
                        self.adx_agent.kernel.add_plugin(new_adx_plugin, plugin_name="ADXTools")
                    
                    # Close old plugin in background
                    old_plugin = self.adx_mcp_plugin
                    self.adx_mcp_plugin = new_adx_plugin
                    
                    if old_plugin:
                        asyncio.create_task(self._close_plugin_background(old_plugin, "ADX"))
                    
                    logger.info("✅ ADX MCP plugin updated successfully")
                    
                except asyncio.TimeoutError:
                    logger.error("❌ ADX MCP plugin connection timed out (10s)")
                except Exception as e:
                    logger.error(f"❌ Error updating ADX MCP plugin: {str(e)}")
            
            # Update Document MCP Plugin
            if self.document_mcp_plugin:
                logger.info("🔄 Updating Document MCP plugin...")
                new_document_plugin = MCPStreamableHttpPlugin(
                    name="DocumentMCPPlugin",
                    url=server_url,
                    headers=headers,
                    load_tools=True,
                    load_prompts=False,
                    request_timeout=30,
                    sse_read_timeout=300,
                    terminate_on_close=True,
                    description="Document tools via MCP server"
                )
                
                try:
                    await asyncio.wait_for(new_document_plugin.connect(), timeout=10.0)
                    # Filter tools 
                    allowed_tools = {
                        "list_documents",
                        "search_documents",
                        "get_document", 
                        "get_document_content_summary"
                    }
                    for attr_name in list(dir(new_document_plugin)):
                        if hasattr(getattr(new_document_plugin, attr_name, None), '__kernel_function_parameters__'):
                            if attr_name not in allowed_tools:
                                delattr(new_document_plugin, attr_name)
                    # Update the Document agent's kernel
                    if self.document_agent:
                        try:
                            self.document_agent.kernel.remove_plugin("DocumentTools")
                        except Exception as remove_error:
                            logger.warning(f"⚠️ Error removing old Document plugin: {str(remove_error)}")
                        
                        self.document_agent.kernel.add_plugin(new_document_plugin, plugin_name="DocumentTools")
                    
                    # Close old plugin in background
                    old_plugin = self.document_mcp_plugin
                    self.document_mcp_plugin = new_document_plugin
                    
                    if old_plugin:
                        asyncio.create_task(self._close_plugin_background(old_plugin, "Document"))
                    
                    logger.info("✅ Document MCP plugin updated successfully")
                    
                except asyncio.TimeoutError:
                    logger.error("❌ Document MCP plugin connection timed out (10s)")
                except Exception as e:
                    logger.error(f"❌ Error updating Document MCP plugin: {str(e)}")
            
            # Update Fictional Companies MCP Plugin
            if self.fictional_companies_mcp_plugin:
                logger.info("🔄 Updating Fictional Companies MCP plugin...")
                new_fictional_plugin = MCPStreamableHttpPlugin(
                    name="FictionalCompaniesMCPPlugin",
                    url=server_url,
                    headers=headers,
                    load_tools=True,
                    load_prompts=False,
                    request_timeout=30,
                    sse_read_timeout=300,
                    terminate_on_close=True,
                    description="Fictional Companies tools via MCP server"
                )
                
                try:
                    await asyncio.wait_for(new_fictional_plugin.connect(), timeout=10.0)
                    			# Filter tools 
                    allowed_tools = {
                        "get_ip_company_info",
                        "get_company_devices", 
                        "get_company_summary",
                        "fictional_api_health_check"
                    }
                    for attr_name in list(dir(new_fictional_plugin)):
                        if hasattr(getattr(new_fictional_plugin, attr_name, None), '__kernel_function_parameters__'):
                            if attr_name not in allowed_tools:
                                delattr(new_fictional_plugin, attr_name)
                    # Update the Fictional Companies agent's kernel
                    if self.fictional_companies_agent:
                        try:
                            self.fictional_companies_agent.kernel.remove_plugin("FictionalCompaniesTools")
                        except Exception as remove_error:
                            logger.warning(f"⚠️ Error removing old Fictional Companies plugin: {str(remove_error)}")
                        
                        self.fictional_companies_agent.kernel.add_plugin(new_fictional_plugin, plugin_name="FictionalCompaniesTools")
                    
                    # Close old plugin in background
                    old_plugin = self.fictional_companies_mcp_plugin
                    self.fictional_companies_mcp_plugin = new_fictional_plugin
                    
                    if old_plugin:
                        asyncio.create_task(self._close_plugin_background(old_plugin, "FictionalCompanies"))
                    
                    logger.info("✅ Fictional Companies MCP plugin updated successfully")
                    
                except asyncio.TimeoutError:
                    logger.error("❌ Fictional Companies MCP plugin connection timed out (10s)")
                except Exception as e:
                    logger.error(f"❌ Error updating Fictional Companies MCP plugin: {str(e)}")
            
            # Update FEMA MCP Plugin
            if self.fema_mcp_plugin:
                logger.info("🔄 Updating FEMA MCP plugin...")
                new_fema_plugin = MCPStreamableHttpPlugin(
                    name="FEMAMCPPlugin",
                    url=server_url,
                    headers=headers,
                    load_tools=True,
                    load_prompts=False,
                    request_timeout=30,
                    sse_read_timeout=300,
                    terminate_on_close=True,
                    description="FEMA RAG tools via MCP server"
                )

                try:
                    await asyncio.wait_for(new_fema_plugin.connect(), timeout=10.0)
                    # Filter tools 
                    allowed_tools = {
                        "fema_retrieve",
                        "fema_rag_answer",
                        "fema_health"
                    }
                    for attr_name in list(dir(new_fema_plugin)):
                        if hasattr(getattr(new_fema_plugin, attr_name, None), '__kernel_function_parameters__'):
                            if attr_name not in allowed_tools:
                                delattr(new_fema_plugin, attr_name)
                    # Update the FEMA agent's kernel
                    if self.fema_agent:
                        try:
                            self.fema_agent.kernel.remove_plugin("FEMATools")
                        except Exception as remove_error:
                            logger.warning(f"⚠️ Error removing old FEMA plugin: {str(remove_error)}")

                        self.fema_agent.kernel.add_plugin(new_fema_plugin, plugin_name="FEMATools")

                    # Close old plugin in background
                    old_plugin = self.fema_mcp_plugin
                    self.fema_mcp_plugin = new_fema_plugin

                    if old_plugin:
                        asyncio.create_task(self._close_plugin_background(old_plugin, "FEMA"))

                    logger.info("✅ FEMA MCP plugin updated successfully")

                except asyncio.TimeoutError:
                    logger.error("❌ FEMA MCP plugin connection timed out (10s)")
                except Exception as e:
                    logger.error(f"❌ Error updating FEMA MCP plugin: {str(e)}")
            
            # Track the context we just used for the plugins
            self.last_mcp_user_id = self.current_user_id
            self.last_mcp_session_id = self.current_session_id
            self.last_mcp_adx_token = self.current_adx_token
            
            logger.info("✅ All MCP plugin contexts updated successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to update MCP plugin contexts: {str(e)}")
            # Don't re-raise to prevent blocking the entire system
            # The agents will continue working with the old plugins
    
    async def _close_plugin_background(self, plugin, plugin_name: str):
        """Close an old MCP plugin in the background without blocking."""
        try:
            await asyncio.wait_for(plugin.close(), timeout=5.0)
            logger.info(f"✅ Old {plugin_name} MCP plugin closed successfully")
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Old {plugin_name} MCP plugin close timed out, but new plugin is working")
        except Exception as close_error:
            logger.warning(f"⚠️ Error closing old {plugin_name} MCP plugin: {str(close_error)}")


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
            "List ADX databases",  # ADXAgent
            "Search for documents about Python",  # DocumentAgent
            
            # Fictional Companies Agent tests
            "What company is associated with IP address 192.168.1.1?",  # FictionalCompaniesAgent
            "Get device information for Acme Corporation",  # FictionalCompaniesAgent
            "Give me a summary of TechCorp Limited",  # FictionalCompaniesAgent
            
            # FEMA Agent tests
            "What are the sources of recovery resources according to FEMA?",  # FEMAAgent
            "How can jurisdictions search for disaster recovery funding?",  # FEMAAgent

            # Agent collaboration tests
            "Query the ADX cluster for database information",  # ADXAgent
            "List all tables in the personnel database",  # ADXAgent
            "Show me database schema",  # ADXAgent
            "List my documents and summarize their content",  # DocumentAgent
            
            # Complex multi-agent workflow
            "Get the list of databases from ADX and tell me about each one",  # ADXAgent
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
'''
