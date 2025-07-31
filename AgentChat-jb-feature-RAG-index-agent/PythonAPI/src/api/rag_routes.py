"""API endpoints for RAG Dataset management."""

import json
import asyncio
from flask import Blueprint, request, jsonify
from typing import Dict, Any, List

try:
    from ..config.rag_datasets_config import rag_datasets_config, RAGDatasetConfig
    from ..services.rag_agent_service import rag_agent_service
    from ..tools.rag_dataset_tools import rag_search_service
    from ..utils.logging import get_logger
    from ..utils.session_utils import get_current_user_id, get_current_session_id
except ImportError:
    from src.config.rag_datasets_config import rag_datasets_config, RAGDatasetConfig
    from src.services.rag_agent_service import rag_agent_service
    from src.tools.rag_dataset_tools import rag_search_service
    from src.utils.logging import get_logger
    from src.utils.session_utils import get_current_user_id, get_current_session_id

logger = get_logger(__name__)

# Create blueprint for RAG dataset routes
rag_bp = Blueprint('rag', __name__, url_prefix='/api/rag')

@rag_bp.route('/datasets', methods=['GET'])
def list_datasets():
    """List all available RAG datasets."""
    try:
        datasets = rag_datasets_config.get_enabled_datasets()
        
        dataset_list = []
        for name, config in datasets.items():
            dataset_info = {
                "name": config.name,
                "display_name": config.display_name,
                "description": config.description,
                "azure_search_index": config.azure_search_index,
                "enabled": config.enabled,
                "max_results": config.max_results
            }
            dataset_list.append(dataset_info)
        
        return jsonify({
            "success": True,
            "datasets": dataset_list,
            "count": len(dataset_list)
        })
        
    except Exception as e:
        logger.error(f"Error listing RAG datasets: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@rag_bp.route('/datasets/<dataset_name>', methods=['GET'])
def get_dataset(dataset_name: str):
    """Get details for a specific RAG dataset."""
    try:
        config = rag_datasets_config.get_dataset(dataset_name)
        
        if not config:
            return jsonify({
                "success": False,
                "error": f"Dataset '{dataset_name}' not found"
            }), 404
        
        return jsonify({
            "success": True,
            "dataset": {
                "name": config.name,
                "display_name": config.display_name,
                "description": config.description,
                "azure_search_index": config.azure_search_index,
                "system_prompt": config.system_prompt,
                "agent_instructions": config.agent_instructions,
                "enabled": config.enabled,
                "max_results": config.max_results,
                "temperature": config.temperature,
                "max_tokens": config.max_tokens
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting RAG dataset '{dataset_name}': {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@rag_bp.route('/datasets/<dataset_name>/search', methods=['POST'])
def search_dataset(dataset_name: str):
    """Search a specific RAG dataset."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400
        
        query = data.get('query')
        if not query:
            return jsonify({
                "success": False,
                "error": "Query is required"
            }), 400
        
        max_results = data.get('max_results', 5)
        user_id = get_current_user_id()
        session_id = get_current_session_id()
        
        # Run async search function
        async def run_search():
            return await rag_search_service.search_dataset(
                dataset_name=dataset_name,
                query=query,
                max_results=max_results,
                user_id=user_id,
                session_id=session_id
            )
        
        # Execute search
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_search())
        finally:
            loop.close()
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error searching RAG dataset '{dataset_name}': {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@rag_bp.route('/agents', methods=['GET'])
def list_agents():
    """List all available RAG agents."""
    try:
        agent_info = rag_agent_service.get_agent_info()
        
        return jsonify({
            "success": True,
            "agents": agent_info,
            "count": len(agent_info)
        })
        
    except Exception as e:
        logger.error(f"Error listing RAG agents: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@rag_bp.route('/agents/<dataset_name>/query', methods=['POST'])
def query_agent(dataset_name: str):
    """Query a specific RAG agent."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400
        
        query = data.get('query')
        if not query:
            return jsonify({
                "success": False,
                "error": "Query is required"
            }), 400
        
        user_id = get_current_user_id()
        session_id = get_current_session_id()
        
        # Run async agent query
        async def run_agent_query():
            return await rag_agent_service.query_agent(
                dataset_name=dataset_name,
                user_query=query,
                session_id=session_id,
                user_id=user_id
            )
        
        # Execute agent query
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_agent_query())
        finally:
            loop.close()
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error querying RAG agent '{dataset_name}': {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@rag_bp.route('/datasets', methods=['POST'])
def create_dataset():
    """Create a new RAG dataset configuration."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400
        
        # Validate required fields
        required_fields = ['name', 'display_name', 'description', 'azure_search_index', 
                          'system_prompt', 'agent_instructions']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    "success": False,
                    "error": f"Required field '{field}' is missing"
                }), 400
        
        # Create dataset config
        dataset_config = RAGDatasetConfig(
            name=data['name'],
            display_name=data['display_name'],
            description=data['description'],
            azure_search_index=data['azure_search_index'],
            system_prompt=data['system_prompt'],
            agent_instructions=data['agent_instructions'],
            max_results=data.get('max_results', 5),
            enabled=data.get('enabled', True),
            temperature=data.get('temperature', 0.3),
            max_tokens=data.get('max_tokens', 8000)
        )
        
        # Add to configuration
        rag_datasets_config.add_dataset(dataset_config)
        
        # Reload agents to include the new dataset
        rag_agent_service.reload_agents()
        
        return jsonify({
            "success": True,
            "message": f"Dataset '{data['name']}' created successfully"
        })
        
    except Exception as e:
        logger.error(f"Error creating RAG dataset: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@rag_bp.route('/datasets/<dataset_name>', methods=['PUT'])
def update_dataset(dataset_name: str):
    """Update an existing RAG dataset configuration."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400
        
        # Get existing dataset
        existing_config = rag_datasets_config.get_dataset(dataset_name)
        if not existing_config:
            return jsonify({
                "success": False,
                "error": f"Dataset '{dataset_name}' not found"
            }), 404
        
        # Update fields
        updated_config = RAGDatasetConfig(
            name=existing_config.name,  # Name cannot be changed
            display_name=data.get('display_name', existing_config.display_name),
            description=data.get('description', existing_config.description),
            azure_search_index=data.get('azure_search_index', existing_config.azure_search_index),
            system_prompt=data.get('system_prompt', existing_config.system_prompt),
            agent_instructions=data.get('agent_instructions', existing_config.agent_instructions),
            max_results=data.get('max_results', existing_config.max_results),
            enabled=data.get('enabled', existing_config.enabled),
            temperature=data.get('temperature', existing_config.temperature),
            max_tokens=data.get('max_tokens', existing_config.max_tokens)
        )
        
        # Update configuration
        rag_datasets_config.add_dataset(updated_config)
        
        # Reload agents to reflect changes
        rag_agent_service.reload_agents()
        
        return jsonify({
            "success": True,
            "message": f"Dataset '{dataset_name}' updated successfully"
        })
        
    except Exception as e:
        logger.error(f"Error updating RAG dataset '{dataset_name}': {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@rag_bp.route('/datasets/<dataset_name>', methods=['DELETE'])
def delete_dataset(dataset_name: str):
    """Delete a RAG dataset configuration."""
    try:
        success = rag_datasets_config.remove_dataset(dataset_name)
        
        if not success:
            return jsonify({
                "success": False,
                "error": f"Dataset '{dataset_name}' not found"
            }), 404
        
        # Reload agents to remove the deleted dataset
        rag_agent_service.reload_agents()
        
        return jsonify({
            "success": True,
            "message": f"Dataset '{dataset_name}' deleted successfully"
        })
        
    except Exception as e:
        logger.error(f"Error deleting RAG dataset '{dataset_name}': {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@rag_bp.route('/reload', methods=['POST'])
def reload_configuration():
    """Reload all RAG dataset configurations and agents."""
    try:
        rag_datasets_config.reload_config()
        rag_agent_service.reload_agents()
        
        return jsonify({
            "success": True,
            "message": "RAG configuration reloaded successfully"
        })
        
    except Exception as e:
        logger.error(f"Error reloading RAG configuration: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
