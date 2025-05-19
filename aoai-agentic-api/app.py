# app.py
from quart import Quart, render_template, request, jsonify
import asyncio, uuid

from semantic_kernel import Kernel
from agent_wrapper import SemanticAgent  # Our custom agent wrapper
from quart_schema import QuartSchema, validate_request, validate_response
from swagger_ui import quart_api_doc

from data_explorer_agent import DataExplorerAgent  # New ADX agent

app = Quart(__name__)
agents_registry = {}
jobs = {}
QuartSchema(app)  # Enables OpenAPI docs
    
# Serve Swagger UI at /docs
quart_api_doc(app, config_url="/openapi.json", url_prefix="/docs", title="API Documentation")

def initialize_agents():
    # Create a shared kernel (or create separate Kernel instances per agent if needed)
    kernel1 = Kernel()
    kernel2 = Kernel()
    
    # Create custom agents with their own configurations
    # agents_registry['agent1'] = SemanticAgent("agent1", kernel1)
    # agents_registry['agent2'] = SemanticAgent("agent2", kernel2)
    # Add further agents as desired
        # Register the new Data Explorer agent
    agents_registry['adx_agent'] = DataExplorerAgent("adx_agent", kernel3)
initialize_agents()

@app.route("/agents", methods=["GET"])
async def list_agents():
    return jsonify({"agents": list(agents_registry.keys())})

@app.route("/agents/<agent_id>/run", methods=["POST"])
async def run_agent(agent_id):
    if agent_id not in agents_registry:
        return jsonify({"error": "Agent not found"}), 404
    
    data = await request.get_json()
    agent_input = data.get("input", "")
    if not agent_input:
        return jsonify({"error": "Missing agent input"}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "running", "result": None}

    async def run_job():
        try:
            result = await agents_registry[agent_id].run_task(agent_input)
            jobs[job_id]["result"] = result
            jobs[job_id]["status"] = "completed"
        except Exception as e:
            jobs[job_id]["result"] = str(e)
            jobs[job_id]["status"] = "failed"

    asyncio.create_task(run_job())
    return jsonify({"job_id": job_id})

@app.route("/jobs/<job_id>", methods=["GET"])
async def check_job(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(jobs[job_id])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
