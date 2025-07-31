#!/usr/bin/env python3
"""
Test script to verify that the coordinator agent can properly call kernel functions.
"""

import asyncio
import os

# Import from the current directory structure
from src.agents.multi_agent_system import MultiAgentSystem

async def test_coordinator_functions():
    """Test that the coordinator agent can properly call kernel functions."""
    print("🧪 Testing Coordinator Agent kernel functions...")
    
    # Get Azure OpenAI credentials from environment
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
    
    if not azure_endpoint or not azure_api_key:
        print("❌ Azure OpenAI environment variables not set")
        return
    
    # Initialize the multi-agent system
    system = MultiAgentSystem(
        azure_openai_api_key=azure_api_key,
        azure_openai_endpoint=azure_endpoint,
        azure_openai_deployment=azure_deployment
    )
    
    # Initialize the system
    await system.initialize()
    
    # Test the coordinator agent directly
    print("\n📋 Testing direct coordinator agent function calls...")
    
    # Test the get_available_agents function
    coordinator = system.coordinator_agent
    print(f"✅ Coordinator agent loaded: {coordinator.name}")
    
    # Check if the kernel has the expected functions
    try:
        # Try to get the plugin from the kernel
        kernel_plugins = coordinator.kernel.plugins
        print(f"🔧 Coordinator kernel plugins: {list(kernel_plugins.keys())}")
        
        # Check if SystemTools plugin exists
        if "SystemTools" in kernel_plugins:
            system_tools = kernel_plugins["SystemTools"]
            print(f"🔧 SystemTools functions: {list(system_tools.functions.keys())}")
        else:
            print("❌ SystemTools plugin not found in kernel")
            
    except Exception as e:
        print(f"❌ Error accessing kernel functions: {e}")
    
    # Test via process_question to trigger the fast path
    print("\n🚀 Testing via process_question (should use fast path)...")
    try:
        response = await system.process_question("What agents are available?")
        print(f"✅ Response received: {response[:200]}...")
        
        # Check if the response contains dynamic agent information
        if "MathAgent" in response and "ADXAgent" in response:
            print("✅ SUCCESS: Response contains dynamic agent information!")
        else:
            print("❌ FAILURE: Response does not contain expected agent information")
            print(f"Full response: {response}")
            
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_coordinator_functions())
