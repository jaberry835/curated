import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion, OpenAIChatPromptExecutionSettings
from semantic_kernel.functions import kernel_function
from semantic_kernel.contents import ChatHistory
from src.utils.sse_emitter import sse_emitter

logger = logging.getLogger(__name__)


@dataclass
class AgentCard:
    name: str
    description: str
    endpoint: str  # full URL for JSON-RPC
    raw: Dict[str, Any]


class A2ARemoteAgent:
    def __init__(self, base_url: str, card: AgentCard):
        self.base_url = base_url.rstrip("/")
        self.card = card

    async def send_message(
        self,
        task: str,
        thread_id: Optional[str] = None,
        timeout: int = 60,
        headers: Optional[Dict[str, str]] = None,
    ) -> str:
        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",  # Use canonical A2A method name
            "params": {"task": task, "threadId": thread_id},
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(self.card.endpoint, json=payload, headers=headers or {})
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"A2A error from {self.card.name}: {data['error']}")
            result = data.get("result") or {}
            return result.get("content") or ""


class RoutingHost:
    """
    A2A-compliant router:
      - Discovers remote agents via RFC 8615 well-known URIs (/.well-known/agent-card.json)
      - Uses SK ChatCompletionAgent with a single function: delegate_task(agent_name, task)
      - LLM decides when to delegate; execution happens over A2A with canonical method names
    """

    def __init__(self, azure_api_key: str, azure_endpoint: str, azure_deployment: str):
        self.azure_api_key = azure_api_key
        self.azure_endpoint = azure_endpoint
        self.azure_deployment = azure_deployment

        self.kernel = Kernel()
        self.kernel.add_service(
            AzureChatCompletion(
                service_id="router",
                api_key=self.azure_api_key,
                endpoint=self.azure_endpoint,
                deployment_name=self.azure_deployment,
            )
        )
        # Router internal state
        self.remote_agents: Dict[str, A2ARemoteAgent] = {}
        self.router: Optional[ChatCompletionAgent] = None
        self._context_headers: Dict[str, str] = {}
        self._session_id: Optional[str] = None

    async def _delegate(self, agent_name: str, task: str) -> str:
        """Shared delegation path with SSE instrumentation."""
        agent = self.remote_agents.get(agent_name)
        if not agent:
            return f"Agent '{agent_name}' not found."
        try:
            session_id = self._session_id or self._context_headers.get("X-Session-ID")
            if session_id:
                sse_emitter.emit_agent_activity(
                    session_id=session_id,
                    agent_name="Multi-Agent System",
                    action=f"Delegating to {agent_name}",
                    status="in-progress",
                    details=(task[:200] + ("..." if len(task) > 200 else "")),
                )
                sse_emitter.emit_agent_activity(
                    session_id=session_id,
                    agent_name=agent_name,
                    action="Invoked by router",
                    status="starting",
                    details=(task[:200] + ("..." if len(task) > 200 else "")),
                )

            t0 = time.perf_counter()
            content = await agent.send_message(task, headers=self._context_headers)
            dt = time.perf_counter() - t0

            if session_id:
                sse_emitter.emit_agent_activity(
                    session_id=session_id,
                    agent_name=agent_name,
                    action="Response received",
                    status="completed",
                    details=(content[:400] + ("..." if len(content) > 400 else "")),
                    duration=dt,
                )
                sse_emitter.emit_agent_activity(
                    session_id=session_id,
                    agent_name="Multi-Agent System",
                    action=f"Delegation from {agent_name} complete",
                    status="completed",
                    details=None,
                    duration=dt,
                )
            return f"[{agent_name}] {content}"
        except Exception as e:
            session_id = self._session_id or self._context_headers.get("X-Session-ID")
            if session_id:
                sse_emitter.emit_agent_activity(
                    session_id=session_id,
                    agent_name=agent_name,
                    action="Error during delegation",
                    status="error",
                    details=str(e),
                )
                sse_emitter.emit_agent_activity(
                    session_id=session_id,
                    agent_name="Multi-Agent System",
                    action=f"Delegation to {agent_name} failed",
                    status="error",
                    details=str(e),
                )
            return f"Error delegating to {agent_name}: {str(e)}"

    def set_context(
        self,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        adx_token: Optional[str] = None,
        authorization: Optional[str] = None,
    ) -> None:
        headers: Dict[str, str] = {}
        if user_id:
            headers["X-User-ID"] = user_id
        if session_id:
            headers["X-Session-ID"] = session_id
            self._session_id = session_id
        if adx_token:
            headers["X-ADX-Token"] = adx_token
            # Provide standard bearer form only if Authorization not already provided
            headers.setdefault("Authorization", f"Bearer {adx_token}")
        if authorization:
            # Preserve upstream caller token; do not override it with ADX token
            headers["Authorization"] = authorization
        self._context_headers = headers

    async def discover_agents(self, addresses: List[str]) -> None:
        """Fetch agent cards using RFC 8615 well-known URI standard."""
        async with httpx.AsyncClient(timeout=15) as client:
            for addr in addresses:
                base = addr.rstrip("/")
                try:
                    r = await client.get(f"{base}/.well-known/agent-card.json")
                    r.raise_for_status()
                    card_raw = r.json()
                    
                    name = card_raw.get("name") or "UnnamedAgent"
                    # Find a JSON-RPC endpoint from card; default to /a2a/message
                    ep = (
                        card_raw.get("endpoints", {}).get("jsonrpc")
                        or f"{base}/a2a/message"
                    )
                    card = AgentCard(
                        name=name,
                        description=card_raw.get("description", ""),
                        endpoint=ep,
                        raw=card_raw,
                    )
                    self.remote_agents[name] = A2ARemoteAgent(base, card)
                    print(f"✅ Discovered agent via well-known URI: {base} -> {name}")
                except Exception as e:
                    print(f"Failed to read Agent Card at {addr}/.well-known/agent-card.json: {e}")

    async def initialize(self) -> None:
        """Create a single ChatCompletionAgent with delegation and collaboration functions."""

        @kernel_function(
            name="delegate_task",
            description="Delegate a task to a remote specialist via A2A",
        )
        async def delegate_task(agent_name: str, task: str) -> str:
            return await self._delegate(agent_name, task)

        @kernel_function(
            name="collaborate_agents",
            description="Coordinate multiple agents to work together on a complex task that requires information from different specialists",
        )
        async def collaborate_agents(task_description: str, agent_sequence: str) -> str:
            """
            Orchestrate multiple agents in sequence or parallel to solve complex problems.
            
            Args:
                task_description: The overall task to accomplish
                agent_sequence: Comma-separated list of agents to involve (e.g., "DocumentAgent,ADXAgent")
            """
            return await self._orchestrate_collaboration(task_description, agent_sequence)

        @kernel_function(
            name="research_task",
            description="Execute deep, multi-agent research with iterative collaboration. REQUIRED for company research - MUST include FictionalCompaniesAgent,ADXAgent,InvestigatorAgent for comprehensive results. Router orchestrates multiple rounds where findings from one agent guide the next query.",
        )
        async def research_task(research_objective: str, relevant_agents: str) -> str:
            """
            Magentic-style orchestration: Router maintains control and iteratively decides
            which agent to invoke next based on previous responses and emerging insights.
            
            Args:
                research_objective: The research goal or question to investigate
                relevant_agents: For COMPANY RESEARCH, use "FictionalCompaniesAgent,ADXAgent,InvestigatorAgent" (all three required for complete analysis: company data, IP/network scans, and leadership background)
            """
            return await self._iterative_research(research_objective, relevant_agents)

        self.kernel.add_function("A2ATools", delegate_task)
        self.kernel.add_function("A2ATools", collaborate_agents)
        self.kernel.add_function("A2ATools", research_task)

        self.router = ChatCompletionAgent(
            service=self.kernel.get_service(),
            kernel=self.kernel,
            name="RoutingAgent",
            instructions=self._router_instructions(),
            function_choice_behavior=FunctionChoiceBehavior.Auto(
                filters={"included_plugins": ["A2ATools"]}
            ),
        )

    async def process_user_message(
        self,
        message: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        adx_token: Optional[str] = None,
        authorization: Optional[str] = None,
    ) -> str:
        """Let the router choose to answer directly or delegate via A2A."""
        if not self.router:
            raise RuntimeError("Router not initialized.")
        # Capture forwarding headers for this turn
        if any([session_id, user_id, adx_token, authorization]):
            self.set_context(user_id=user_id, session_id=session_id, adx_token=adx_token, authorization=authorization)
        
        # Emit SSE: routing start
        if self._session_id:
            sse_emitter.emit_agent_activity(
                session_id=self._session_id,
                agent_name="RoutingAgent",
                action="Analyzing message",
                status="in-progress",
                details=(message[:200] + ("..." if len(message) > 200 else "")),
            )
        # Present known specialists in context
        specialists = [
            {"name": n, "description": a.card.description}
            for n, a in self.remote_agents.items()
        ]
        system_preamble = (
            "You are a routing/synthesis agent. "
            "You may answer directly, call delegate_task(agent_name, task) for single-agent tasks, "
            "or call collaborate_agents(task_description, agent_sequence) for multi-agent workflows.\n\n"
            "CRITICAL: If a user refers to 'that file', 'the document', 'names in that file', 'what does it say', "
            "or any implicit reference to uploaded content, that should delegate to DocumentAgent. "
            "Do NOT ask for clarification - assume they mean uploaded documents.\n\n"
            f"Available specialists:\n{json.dumps(specialists, indent=2)}"
        )

        chat_history = ChatHistory()
        chat_history.add_system_message(system_preamble)
        chat_history.add_user_message(message)

        settings = OpenAIChatPromptExecutionSettings(
            temperature=0.1,
            max_tokens=1200,
            function_choice_behavior=self.router.function_choice_behavior,
        )
        t0 = time.perf_counter()
        result = await self.kernel.get_service().get_chat_message_content(
            chat_history=chat_history,
            settings=settings,
            kernel=self.kernel,
        )
        final = (result.content or "").strip()
        # Emit SSE: routing complete
        if self._session_id:
            sse_emitter.emit_agent_activity(
                session_id=self._session_id,
                agent_name="RoutingAgent",
                action="Synthesis complete",
                status="completed",
                details=(final[:400] + ("..." if len(final) > 400 else "")),
                duration=(time.perf_counter() - t0),
            )
        return final

    async def _orchestrate_collaboration(self, task_description: str, agent_sequence: str) -> str:
        """
        Orchestrate multiple agents to work together on a complex task.
        Uses regular ChatCompletion to coordinate the workflow.
        """
        # Parse agent sequence - handle various formats
        import re
        
        # Clean up the sequence and extract agent names
        # Handle formats like: "DocumentAgent,ADXAgent", "DocumentAgent -> ADXAgent", "DocumentAgent then ADXAgent"
        agent_sequence_clean = re.sub(r'\s*->\s*|\s+then\s+|\s*,\s*', ',', agent_sequence)
        agent_names = [name.strip() for name in agent_sequence_clean.split(",") if name.strip()]
        
        # Validate all agents exist
        missing_agents = [name for name in agent_names if name not in self.remote_agents]
        if missing_agents:
            return f"Cannot collaborate: agents not found: {missing_agents}"

        session_id = self._session_id or self._context_headers.get("X-Session-ID")
        if session_id:
            sse_emitter.emit_agent_activity(
                session_id=session_id,
                agent_name="Multi-Agent System",
                action="Starting collaboration",
                status="starting", 
                details=f"Task: {task_description[:200]}... Agents: {agent_sequence}",
            )

        # Create an orchestration agent to manage the workflow
        orchestrator = ChatCompletionAgent(
            service=self.kernel.get_service(),
            kernel=self.kernel,
            name="OrchestrationAgent",
            instructions=self._orchestration_instructions(agent_names),
            function_choice_behavior=FunctionChoiceBehavior.Auto(
                filters={"included_plugins": ["A2ATools"]}
            ),
        )

        # Build context about available agents
        agent_info = []
        for name in agent_names:
            agent = self.remote_agents[name]
            agent_info.append({
                "name": name,
                "description": agent.card.description,
                "capabilities": agent.card.raw.get("capabilities", [])
            })

        # Create orchestration prompt
        orchestration_prompt = f"""
Task to accomplish: {task_description}

Available specialist agents for this task:
{json.dumps(agent_info, indent=2)}

Plan and execute a multi-step workflow using delegate_task() to coordinate these agents.
For questions that involve finding information from one source and then using it with another:
1. First, gather the necessary information from the appropriate agent
2. Then, use that information with the next agent
3. Synthesize the final results

Start by planning your approach, then execute the steps.
"""

        chat_history = ChatHistory()
        chat_history.add_user_message(orchestration_prompt)

        try:
            # Let the orchestrator plan and execute the workflow
            result = await orchestrator.get_response(messages=[orchestration_prompt], kernel=self.kernel)
            final_content = result.message.content or "No response from orchestration."
            
            if session_id:
                sse_emitter.emit_agent_activity(
                    session_id=session_id,
                    agent_name="Multi-Agent System",
                    action="Collaboration complete",
                    status="completed",
                    details=final_content[:400] + ("..." if len(final_content) > 400 else ""),
                )
            
            return final_content
            
        except Exception as e:
            error_msg = f"Error during multi-agent collaboration: {str(e)}"
            if session_id:
                sse_emitter.emit_agent_activity(
                    session_id=session_id,
                    agent_name="Multi-Agent System", 
                    action="Collaboration failed",
                    status="error",
                    details=error_msg,
                )
            return error_msg

    async def _iterative_research(self, research_objective: str, relevant_agents: str) -> str:
        """
        Magentic-style research orchestration where router acts as the manager,
        maintaining conversation state and iteratively deciding which agent to invoke
        next based on accumulated findings.
        
        This enables deep, multi-round research where:
        - Findings from one agent inform which agent to query next
        - The router dynamically adapts the research strategy
        - Multiple rounds of agent invocations build comprehensive answers
        """
        import re
        
        # Parse agent list
        agent_list = [name.strip() for name in relevant_agents.split(",") if name.strip()]
        
        # Filter out DocumentAgent if no documents are uploaded
        # DocumentAgent should only be used when user has uploaded files to analyze
        if "DocumentAgent" in agent_list:
            # Check if there are any uploaded documents (you can enhance this check)
            # For now, remove DocumentAgent from research unless explicitly needed
            session_id = self._session_id or self._context_headers.get("X-Session-ID")
            # Simple heuristic: If research objective doesn't mention documents/files, exclude DocumentAgent
            if not any(keyword in research_objective.lower() for keyword in ["document", "file", "upload", "pdf", "doc"]):
                agent_list.remove("DocumentAgent")
                if session_id:
                    logger.info(f"Filtered out DocumentAgent from research (no document-related keywords in objective)")
        else:
            session_id = self._session_id or self._context_headers.get("X-Session-ID")
        
        # Validate agents exist
        missing_agents = [name for name in agent_list if name not in self.remote_agents]
        if missing_agents:
            return f"Cannot start research: agents not found: {missing_agents}"
        
        if session_id:
            sse_emitter.emit_agent_activity(
                session_id=session_id,
                agent_name="Research Orchestrator",
                action="Starting iterative research",
                status="starting",
                details=f"Objective: {research_objective[:200]}... Agents: {relevant_agents}",
            )
        
        # Create research orchestrator agent with special instructions
        research_orchestrator = ChatCompletionAgent(
            service=self.kernel.get_service(),
            kernel=self.kernel,
            name="ResearchOrchestrator",
            instructions=self._research_orchestration_instructions(agent_list, research_objective),
            function_choice_behavior=FunctionChoiceBehavior.Auto(
                filters={"included_plugins": ["A2ATools"]}
            ),
        )
        
        # Initialize research conversation
        research_history = ChatHistory()
        research_history.add_user_message(f"""Begin research on this objective:

{research_objective}

You have access to these specialist agents: {', '.join(agent_list)}

Plan your approach and begin executing step-by-step. Use delegate_task() to gather information from agents as needed.
After each agent response, analyze what you learned and decide the next action.

When you have sufficient information, synthesize a comprehensive final answer.""")
        
        max_rounds = 12  # Allow more rounds for deep research
        round_num = 0
        
        try:
            while round_num < max_rounds:
                round_num += 1
                
                if session_id:
                    sse_emitter.emit_agent_activity(
                        session_id=session_id,
                        agent_name="Research Orchestrator",
                        action=f"Research round {round_num}/{max_rounds}",
                        status="in-progress",
                        details="Analyzing findings and planning next step...",
                    )
                
                # Get orchestrator's next decision
                # invoke() is an async generator that streams results and modifies chat_history in place
                messages = []
                async for msg in research_orchestrator.invoke(
                    kernel=self.kernel,
                    chat_history=research_history
                ):
                    messages.append(msg)
                
                # Extract response content from the last message
                if len(messages) == 0:
                    # No response, prompt for next action
                    research_history.add_user_message(
                        "What's your next step? Gather more information from an agent, or synthesize your findings into a final answer?"
                    )
                    continue
                
                # Get the last message (assistant's response)
                last_message = messages[-1]
                # Ensure response_content is always a string
                if hasattr(last_message, 'content'):
                    response_content = str(last_message.content) if last_message.content is not None else ""
                else:
                    response_content = str(last_message)
                
                # Check if research is complete
                if self._is_research_complete(response_content):
                    if session_id:
                        sse_emitter.emit_agent_activity(
                            session_id=session_id,
                            agent_name="Research Orchestrator",
                            action="Research complete",
                            status="completed",
                            details=response_content[:400] + ("..." if len(response_content) > 400 else ""),
                        )
                    return response_content
                
                # If orchestrator didn't call a function and hasn't concluded,
                # prompt it to either gather more info or conclude
                has_function_call = hasattr(last_message, 'items') and last_message.items and any(
                    hasattr(item, 'function_name') for item in last_message.items
                )
                
                if not has_function_call:
                    # Check if this looks like a synthesis/conclusion attempt
                    if len(response_content) > 200 and any(
                        indicator in response_content.lower() 
                        for indicator in ["based on", "in summary", "findings show", "analysis reveals"]
                    ):
                        # This appears to be a final synthesis
                        return response_content
                    
                    # Otherwise prompt for next action
                    # Note: invoke() already added assistant message to history
                    research_history.add_user_message(
                        "What's your next step? Gather more information from an agent, or synthesize your findings into a final answer?"
                    )
                # If function was called, invoke() already added response to history
                # Loop will continue with next round
            
            # Max rounds reached
            final_msg = "Research reached maximum iterations. Here are the accumulated findings:\n\n"
            
            # Extract all agent responses from history
            findings = []
            for msg in research_history.messages:
                # Safely convert content to string before checking length
                content_str = str(msg.content) if msg.content is not None else ""
                if msg.role.value == "assistant" and len(content_str) > 50:
                    findings.append(content_str)
            
            if findings:
                final_msg += "\n\n".join(findings[-3:])  # Last 3 substantial responses
            
            return final_msg
            
        except Exception as e:
            error_msg = f"Error during iterative research: {str(e)}"
            if session_id:
                sse_emitter.emit_agent_activity(
                    session_id=session_id,
                    agent_name="Research Orchestrator",
                    action="Research failed",
                    status="error",
                    details=error_msg,
                )
            return error_msg
    
    def _is_research_complete(self, content: str) -> bool:
        """Check if research has reached a conclusion."""
        if not content or len(content) < 100:
            return False
        
        completion_indicators = [
            "research complete",
            "comprehensive answer",
            "final synthesis",
            "conclusion:",
            "final answer:",
            "in summary of all findings",
            "complete analysis",
            "research summary:",
            "final research findings",
        ]
        
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in completion_indicators)
    
    def _research_orchestration_instructions(self, agent_names: List[str], objective: str) -> str:
        """Generate instructions for the research orchestrator."""
        agent_info = []
        for name in agent_names:
            if name in self.remote_agents:
                agent = self.remote_agents[name]
                agent_info.append({
                    "name": name,
                    "description": agent.card.description,
                    "capabilities": agent.card.raw.get("capabilities", [])
                })
        
        return f"""You are a Research Orchestrator managing an iterative, multi-agent research process using the Magentic-One pattern.

RESEARCH OBJECTIVE:
{objective}

AVAILABLE SPECIALIST AGENTS:
{json.dumps(agent_info, indent=2)}

🎯 YOUR ORCHESTRATION PRINCIPLES:

You maintain research state and decide which specialist to consult next based on:
- What you've learned so far
- What gaps remain in your understanding  
- What connections you're discovering between different information sources
- What new questions emerge from each agent's response

**Technical Requirement**: Use delegate_task(agent_name="AgentName", task="specific question") to interact with specialists.

🧭 DISCOVERY-DRIVEN RESEARCH APPROACH:

You are a creative investigator, not following a script. Let the research unfold naturally:

**Starting Point**: Begin with whatever agent can provide the initial context or anchor information.

**Iterative Discovery**: After each agent response, pause and reflect:
- What did I just learn that's significant?
- What new entities, identifiers, or connections were revealed? (IPs, names, locations, patterns)
- What would be valuable to investigate next?
- Which specialist agent could help explore that?

**Following Leads**: When you discover:
- **IP addresses** → ADXAgent can search for network/security intelligence on those IPs
- **Company names** → FictionalCompaniesAgent provides business/infrastructure details AND ADXAgent may have company data in database tables (scans, logs, people/employees, etc.)
- **People/executives** → InvestigatorAgent researches backgrounds/relationships AND ADXAgent may have employee/personnel data in database tables
- **Cross-references** → ADXAgent excels at finding connections across multiple database tables (people, companies, IPs, events, etc.)

🔍 **IMPORTANT - ADXAgent's Broader Capabilities:**
ADXAgent isn't just for IP addresses! It searches **database tables** that may contain:
- Company information (company names, relationships, organizational data)
- Employee/personnel data (people working at companies, contact info, roles)
- Security events (scans, alerts, threats linked to companies or people)
- Network logs (activity tied to companies, devices, or individuals)
- Cross-references between entities (which people work at which companies, which IPs belong to which orgs)

When researching a **company**, ask ADXAgent to search for:
- "Search all tables for data about [CompanyName]" 
- "Find any employees or people associated with [CompanyName]"
- "Look for company records, personnel data, or organizational information about [CompanyName]"

When researching **people**, ask ADXAgent to search for:
- "Search for any data about [PersonName] including employment, activity, or associations"
- "Find personnel or employee records for people at [CompanyName]"

**Adaptive Strategy**: 
- There's no required sequence - adapt based on what you're finding
- Some research paths dead-end - that's useful information too
- Some findings open multiple new avenues - explore the most promising
- Depth vs. breadth: Balance thorough investigation with comprehensive coverage

**Building Understanding**: As you gather information:
- Notice patterns and anomalies
- Connect dots between different specialists' findings
- Form hypotheses and test them with targeted queries
- Recognize when you have sufficient insight vs. when gaps remain

🎓 EXAMPLE DISCOVERY PATTERNS (not prescriptive - just possibilities):

*Scenario*: Researching company "TechCorp"
- Start → FictionalCompaniesAgent: "Tell me about TechCorp" → Discover they have devices at IPs 10.1.2.3, 10.1.2.4
- Follow-up #1 → ADXAgent: "Search all tables for any data about TechCorp, including company records, employee/personnel data, and organizational information" → Find company appears in database with employee records
- Follow-up #2 → ADXAgent: "Search for any activity from IP 10.1.2.3" → Find security scans showing vulnerabilities
- New angle → ADXAgent: "Find any employees or people associated with TechCorp" → Discover employee names, roles, contact info
- Integration → InvestigatorAgent: "Research backgrounds of [employees discovered]" → Get career histories and professional backgrounds
- Deep dive → ADXAgent: "Search for any security events, alerts, or network activity related to TechCorp or its employees" → Cross-reference findings
- Synthesis → Combine business profile + database records + employee data + network security posture + leadership context

*The key*: Each finding generates new questions. ADXAgent searches **databases** (not just IPs), so use it to find company data, people data, and cross-references. Follow what seems most valuable.

✅ COMPLETION RECOGNITION:

You'll know research is complete when:
- The core research objective is thoroughly addressed
- Major discoverable facts have been uncovered
- Available specialists have been consulted on their relevant areas
- Diminishing returns: New queries aren't adding significant value
- You can synthesize a coherent, comprehensive answer

📋 **CRITICAL: COMPREHENSIVE SYNTHESIS REQUIREMENTS**

When synthesizing your final response, you MUST include:

1. **All Database Discoveries:**
   - If ADXAgent found people/employees in database tables → **Include them in final response**
   - If ADXAgent found company records in database → **Include them in final response**
   - If ADXAgent found IPs, scans, logs, alerts → **Include them in final response**
   - Example: "Database records show Mark Reynolds (Zyphronix Dynamics employee, address: 200 Elm St, Tysons VA)"

2. **All Research Attempts (Even Unsuccessful Ones):**
   - If you researched someone but InvestigatorAgent found no background info → **Still mention the person was found in database**
   - Example: "Database identified Mark Reynolds as a Zyphronix employee, though no additional background information was available in public records"

3. **Cross-Reference Database + External Sources:**
   - Database findings (people, IPs, scans) are **primary intelligence**
   - InvestigatorAgent findings (C-suite executives, leadership) are **secondary intelligence**
   - **Mention both** in synthesis, clearly distinguishing sources

4. **Clear Attribution:**
   - "Database records show..." (from ADXAgent)
   - "Company profile indicates..." (from FictionalCompaniesAgent)
   - "Public research found..." (from InvestigatorAgent)

❌ **WRONG Synthesis:**
"Leadership team includes CEO Dr. Kythara Moonwhisper, CTO Vex Stellarforge..." [omits Mark Reynolds found in database]

✅ **CORRECT Synthesis:**
"Database records identified Mark Reynolds (address: 200 Elm St, Tysons VA) as associated with Zyphronix Dynamics. While public records contained limited information about Mark Reynolds, leadership team research found CEO Dr. Kythara Moonwhisper, CTO Vex Stellarforge..."

**KEY PRINCIPLE:** Database discoveries are often the MOST important findings because they show actual data in your systems. Never omit them from synthesis.

When complete:
- Signal with "FINAL RESEARCH FINDINGS:" or "RESEARCH COMPLETE:"
- Synthesize **ALL** discoveries into a coherent narrative (database + external sources)
- Highlight key facts, patterns, and connections
- Cite which specialists provided which insights
- Note any limitations or areas where information wasn't available

🌟 REMEMBER: 
- You're a creative investigator following leads, not executing a script
- Let curiosity and discovered information guide your path
- Each specialist brings different intelligence - use them strategically
- Deep research requires multiple rounds - keep going until you have the full picture
- There's no single "right" way to research - adapt to what you're finding
"""

    def _orchestration_instructions(self, agent_names: List[str]) -> str:
        """Generate instructions for the orchestration agent."""
        return f"""
You are an orchestration agent responsible for coordinating multiple specialist agents to solve complex tasks.

Your role:
- Plan multi-step workflows that leverage each agent's expertise
- Use delegate_task(agent_name, task) to interact with specialists: {', '.join(agent_names)}
- Gather information from one agent and use it as input for another when needed
- Synthesize final answers from multiple agent responses
- Ensure all parts of the user's question are addressed

Key patterns:
- Document + ADX queries: First get info from DocumentAgent, then search ADX with that info
- Research tasks: Gather data from multiple sources, then synthesize findings
- Multi-step analysis: Break complex questions into logical sequence of specialist tasks

Always provide a comprehensive final answer that addresses the original question completely.
"""

    def _router_instructions(self) -> str:
        return (
            "You are an intelligent routing and orchestration agent. Analyze user queries carefully and choose the optimal approach:\n\n"
            
            "🚨 PRIORITY RULE #1: COMPANY RESEARCH ALWAYS USES research_task 🚨\n"
            "If the user mentions ANY company name or asks to research/investigate/look up a company, you MUST use research_task.\n"
            "Examples that trigger research_task:\n"
            "  ✅ 'Research Zyphronix Dynamics' → research_task(research_objective='Research Zyphronix Dynamics', relevant_agents='FictionalCompaniesAgent,ADXAgent,InvestigatorAgent')\n"
            "  ✅ 'Tell me about TechCorp' → research_task(research_objective='Research TechCorp', relevant_agents='FictionalCompaniesAgent,ADXAgent,InvestigatorAgent')\n"
            "  ✅ 'Zyphronix Dynamics' → research_task(research_objective='Research Zyphronix Dynamics', relevant_agents='FictionalCompaniesAgent,ADXAgent,InvestigatorAgent')\n"
            "  ✅ 'Please Research the company: Zyphronix Dynamics' → research_task(research_objective='Research the company: Zyphronix Dynamics', relevant_agents='FictionalCompaniesAgent,ADXAgent,InvestigatorAgent')\n"
            "  ❌ NEVER use delegate_task for company research - it will miss critical insights!\n\n"
            
            "AGENT CAPABILITIES:\n"
            "• FictionalCompaniesAgent: Company intelligence - profiles, business details, network infrastructure, device inventories with IP addresses, organizational structure. Start here for company research.\n"
            "• ADXAgent: Database intelligence - security scans, network logs, vulnerability reports, IP analysis, device activity, threat data. Searches across multiple tables/databases for comprehensive findings. Use when investigating IPs, security events, or cross-referencing network data.\n" 
            "• InvestigatorAgent: Background research - people, executives, leadership teams, career histories, professional backgrounds, biographical data. Use for human-element investigation.\n"
            "• DocumentAgent: Document analysis - only use if user uploaded files. Analyzes document content, extracts text, searches within uploaded materials.\n\n"
            
            "ROUTING DECISIONS:\n\n"
            "1. SIMPLE SINGLE-AGENT TASKS (use delegate_task):\n"
            "   - Document operations (delegate to DocumentAgent):\n"
            "     * Explicit: 'summarize this document', 'what's in the file?', 'read the uploaded file'\n"
            "     * Implicit references: 'names in that file', 'what does it say?', 'list the items mentioned', 'extract data from it'\n"
            "     * ANY question referring to uploaded content, files, documents, or 'that file/document'\n"
            "     * Questions about content without specifying source (likely refers to uploaded documents)\n"
            "   - Pure database queries: 'search ADX for IP 1.2.3.4', 'run KQL query'\n"
            "   - A question posed to a specific agent by name: 'Ask the InvestigatorAgent what it knows about John Doe'\n"
            "   - Simple data lookups: 'who owns this IP address?' (ONLY if user wants just ownership, not full research)\n"
            "   ⚠️ NEVER use delegate_task for company research!\n\n"
            
            "2. COMPLEX MULTI-AGENT WORKFLOWS (use collaborate_agents):\n"
            "   - Cross-referencing data: 'find IP in document and search for it in ADX'\n"
            "   - Multi-step analysis: 'extract data from document then look up in database'\n"
            "   - Information synthesis: 'get company info and check their IPs in scan data'\n"
            "   - Sequential workflows: 'read document, identify entities, search for each'\n"
            "   - KNOWN SEQUENCE: You can predict the exact steps and agents needed upfront\n\n"
            
            "3. DEEP RESEARCH & INVESTIGATION (use research_task):\n"
            "   ⚠️ CRITICAL: Use research_task for ANY company research, even if just a company name is given!\n"
            "   - Company research (ALWAYS use research_task): 'research CompanyName', 'tell me about CompanyX', 'find info on CompanyY'\n"
            "   - Even simple-looking company queries: 'Zyphronix Dynamics', 'look up TechCorp', 'what do you know about AcmeCo'\n"
            "   \n"
            "   📋 AGENT SELECTION FOR COMPANY RESEARCH:\n"
            "   - **ALWAYS include FictionalCompaniesAgent** for company lookups (provides company details + IPs)\n"
            "   - **ALWAYS include ADXAgent** to investigate IP addresses and scan data\n"
            "   - **ALWAYS include InvestigatorAgent** for leadership/background research\n"
            "   - Only include DocumentAgent if documents are uploaded\n"
            "   - Example: relevant_agents=\"FictionalCompaniesAgent,ADXAgent,InvestigatorAgent\"\n"
            "   \n"
            "   - Open-ended investigation: 'investigate this entity', 'do a deep dive on X', 'find everything about X'\n"
            "   - Multi-round investigation: Research that requires following leads and discovering new information\n"
            "   - Iterative analysis: Each finding leads to new questions and deeper investigation\n"
            "   - Examples:\n"
            "     * 'Research TechCorp' → Find company → Get IPs → Check scans → Investigate CEO → Cross-reference docs → Synthesis\n"
            "     * 'Zyphronix Dynamics' → Company info → IP addresses → Security scans → Leadership research → Documents → Full report\n"
            "     * 'Investigate suspicious IP 1.2.3.4' → Check ownership → Query logs → Research owner → Find related IPs → Compile\n"
            "     * 'Deep dive on Project X' → Check docs → Identify stakeholders → Research each → Gather intel → Synthesis\n"
            "   - Use when: Solution path is unknown OR findings should guide next steps OR comprehensive research needed\n"
            "   - KEY: Company names alone = research (not simple lookup)\n\n"
            
            "4. COLLABORATION PATTERNS:\n"
            "   - Document → ADX: Extract info from docs, then query database\n"
            "   - Document → Company: Find IPs/companies in docs, then get business intel\n"
            "   - ADX → Company: Find IPs in scans, then identify owners\n"
            "   - Multiple sources: Gather data from 2+ agents for comprehensive analysis\n"
            "   - Iterative research: Company → IPs → Scans → Background → Documents → Synthesis\n\n"
            
            "IMPORTANT: When users refer to 'that file', 'the document', 'it', 'the names', 'the list', etc. without explicit context,\n"
            "assume they are referring to uploaded documents and route to DocumentAgent first.\n"
            
            "For collaborate_agents: specify clear task_description and agent_sequence (comma-separated)\n"
            "Always provide comprehensive final answers that address all aspects of the user's question."
        )
