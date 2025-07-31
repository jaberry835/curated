"""Test script to verify RAG agent integration with multi-agent system."""

import asyncio
import logging
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.services.rag_agent_service import rag_agent_service
from src.agents.multi_agent_system import MultiAgentSystem

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_rag_integration():
    """Test RAG agent integration."""
    try:
        # Test RAG agent service
        logger.info("🧪 Testing RAG Agent Service...")
        
        # Get available agents
        rag_agents = rag_agent_service.get_all_agents()
        logger.info(f"✅ Found {len(rag_agents)} RAG agents")
        
        for name, agent in rag_agents.items():
            logger.info(f"   📚 {name}: {agent.dataset_config.display_name}")
        
        # Get available datasets
        datasets = rag_agent_service.get_available_datasets()
        logger.info(f"✅ Available datasets: {datasets}")
        
        # Test agent info
        agent_info = rag_agent_service.get_agent_info()
        logger.info(f"✅ Agent info for {len(agent_info)} agents:")
        for info in agent_info:
            logger.info(f"   📋 {info['agent_name']}: {info['description']}")
        
        logger.info("🎉 RAG Agent Service test completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ RAG integration test failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(test_rag_integration())
