import json
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

        self.kernel.add_function("A2ATools", delegate_task)
        self.kernel.add_function("A2ATools", collaborate_agents)

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
            
            "AGENT CAPABILITIES:\n"
            "• DocumentAgent: Document analysis, file reading, text extraction, summarization, finding information in uploaded files\n"
            "• ADXAgent: Azure Data Explorer queries, KQL, database searches, scan data, security logs, telemetry analysis\n" 
            "• InvestigatorAgent: This agent has access to specific datasets that it has indexed.  It can act as as tool to check for information regarding a certain topic or entity.\n"
            "• FictionalCompaniesAgent: Company information, IP address ownership, business intelligence, fictional company data\n\n"
            
            "ROUTING DECISIONS:\n\n"
            "1. SIMPLE SINGLE-AGENT TASKS (use delegate_task):\n"
            "   - Document operations (delegate to DocumentAgent):\n"
            "     * Explicit: 'summarize this document', 'what's in the file?', 'read the uploaded file'\n"
            "     * Implicit references: 'names in that file', 'what does it say?', 'list the items mentioned', 'extract data from it'\n"
            "     * ANY question referring to uploaded content, files, documents, or 'that file/document'\n"
            "     * Questions about content without specifying source (likely refers to uploaded documents)\n"
            "   - Pure database queries: 'search ADX for IP 1.2.3.4', 'run KQL query'\n"
            "   - A question posed to a specific agent by name: 'Ask the InvestigatorAgent what it knows about John Doe'\n"
            "   - Pure company lookups: 'who owns this IP address?'\n\n"
            
            "2. COMPLEX MULTI-AGENT WORKFLOWS (use collaborate_agents):\n"
            "   - Cross-referencing data: 'find IP in document and search for it in ADX'\n"
            "   - Multi-step analysis: 'extract data from document then look up in database'\n"
            "   - Information synthesis: 'get company info and check their IPs in scan data'\n"
            "   - Sequential workflows: 'read document, identify entities, search for each'\n\n"
            
            "3. COLLABORATION PATTERNS:\n"
            "   - Document → ADX: Extract info from docs, then query database\n"
            "   - Document → Company: Find IPs/companies in docs, then get business intel\n"
            "   - ADX → Company: Find IPs in scans, then identify owners\n"
            "   - Multiple sources: Gather data from 2+ agents for comprehensive analysis\n\n"
            
            "IMPORTANT: When users refer to 'that file', 'the document', 'it', 'the names', 'the list', etc. without explicit context,\n"
            "assume they are referring to uploaded documents and route to DocumentAgent first.\n"
            
            "For collaborate_agents: specify clear task_description and agent_sequence (comma-separated)\n"
            "Always provide comprehensive final answers that address all aspects of the user's question."
        )
