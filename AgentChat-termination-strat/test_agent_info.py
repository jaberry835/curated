#!/usr/bin/env python3
"""Test script to verify the agent information functionality."""

import asyncio
import os
import sys

# Add the PythonAPI src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'PythonAPI', 'src'))

from agents.multi_agent_system import MultiAgentSystem

async def test_agent_info():
    """Test that the coordinator can properly report available agents."""
    
    # Mock Azure OpenAI configuration
    system = MultiAgentSystem(
        azure_openai_api_key="test_key",
        azure_openai_endpoint="https://test.openai.azure.com/",
        azure_openai_deployment="test-deployment"
    )
    
    # Initialize the system (this will build the agent registry)
    try:
        await system.initialize()
        print("✅ System initialized successfully")
        
        # Test the get_available_agents_info method
        agent_info = system.get_available_agents_info()
        print("\n📋 Available Agents Info:")
        print(agent_info)
        
        # Test that the registry contains the expected agents
        expected_agents = [
            'CoordinatorAgent',
            'MathAgent', 
            'UtilityAgent',
            'ADXAgent',
            'DocumentAgent',
            'FictionalCompaniesAgent'
        ]
        
        actual_agents = list(system.agent_registry.keys())
        print(f"\n🔍 Expected agents: {expected_agents}")
        print(f"🔍 Actual agents: {actual_agents}")
        
        missing_agents = set(expected_agents) - set(actual_agents)
        extra_agents = set(actual_agents) - set(expected_agents)
        
        if missing_agents:
            print(f"❌ Missing agents: {missing_agents}")
        if extra_agents:
            print(f"➕ Extra agents: {extra_agents}")
        
        if not missing_agents and not extra_agents:
            print("✅ All expected agents are present!")
        
        # Test that each agent has the required metadata
        for agent_name, agent_info in system.agent_registry.items():
            required_keys = ['agent', 'description', 'keywords', 'examples']
            missing_keys = [key for key in required_keys if key not in agent_info]
            
            if missing_keys:
                print(f"❌ {agent_name} missing metadata: {missing_keys}")
            else:
                print(f"✅ {agent_name} has complete metadata")
        
        print("\n🎯 Test completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during initialization: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_agent_info())
