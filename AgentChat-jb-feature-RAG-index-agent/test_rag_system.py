"""Test script for the Dynamic RAG Agent System."""

import asyncio
import json
import sys
from pathlib import Path

# Add src to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from src.config.rag_datasets_config import rag_datasets_config
from src.services.rag_agent_service import rag_agent_service
from src.tools.rag_dataset_tools import rag_search_service, search_rag_dataset_impl

async def test_rag_system():
    """Test the RAG system components."""
    
    print("🧪 Testing Dynamic RAG Agent System")
    print("=" * 50)
    
    # Test 1: Configuration Loading
    print("1. Testing Configuration Loading...")
    try:
        datasets = rag_datasets_config.get_enabled_datasets()
        print(f"✅ Loaded {len(datasets)} datasets:")
        for name, config in datasets.items():
            print(f"   - {config.display_name} ({name}) -> {config.azure_search_index}")
    except Exception as e:
        print(f"❌ Configuration loading failed: {e}")
        return
    
    # Test 2: RAG Search Service
    print("\n2. Testing RAG Search Service...")
    try:
        # Test with a simple query (will likely fail without proper Azure config)
        result = await rag_search_service.search_dataset(
            dataset_name="hulk",
            query="test query",
            max_results=3
        )
        if result.get("success"):
            print(f"✅ Search service working: {result.get('count', 0)} results")
        else:
            print(f"⚠️ Search service returned error (expected without Azure config): {result.get('error')}")
    except Exception as e:
        print(f"⚠️ Search service error (expected without Azure config): {e}")
    
    # Test 3: RAG Agent Service
    print("\n3. Testing RAG Agent Service...")
    try:
        agents = rag_agent_service.get_all_agents()
        print(f"✅ Initialized {len(agents)} agents:")
        for name, agent in agents.items():
            print(f"   - {agent.agent_name} (dataset: {name})")
        
        # Get agent info
        agent_info = rag_agent_service.get_agent_info()
        print(f"✅ Agent info available for {len(agent_info)} agents")
        
    except Exception as e:
        print(f"❌ Agent service error: {e}")
        return
    
    # Test 4: Tool Function
    print("\n4. Testing RAG Dataset Tool Functions...")
    try:
        from src.tools.rag_dataset_tools import search_hulk_dataset_impl
        
        # Test the tool function (will likely fail without Azure config)
        result = await search_hulk_dataset_impl(
            query="test query",
            max_results=3
        )
        result_data = json.loads(result) if isinstance(result, str) else result
        
        if result_data.get("success"):
            print(f"✅ Tool function working: {result_data.get('count', 0)} results")
        else:
            print(f"⚠️ Tool function error (expected without Azure config): {result_data.get('error')}")
            
    except Exception as e:
        print(f"⚠️ Tool function error (expected without Azure config): {e}")
    
    # Test 5: Dynamic Tool Generation
    print("\n5. Testing Dynamic Tool Generation...")
    try:
        from src.tools.rag_dataset_tools import get_rag_dataset_tools, get_rag_dataset_tool_descriptions
        
        tools = get_rag_dataset_tools()
        descriptions = get_rag_dataset_tool_descriptions()
        
        print(f"✅ Generated {len(tools)} dynamic tools")
        print(f"✅ Generated {len(descriptions)} tool descriptions:")
        for desc in descriptions:
            print(f"   - {desc['name']}: {desc['description'][:60]}...")
            
    except Exception as e:
        print(f"❌ Dynamic tool generation error: {e}")
    
    # Test 6: Configuration Management
    print("\n6. Testing Configuration Management...")
    try:
        # Test adding a new dataset
        from src.config.rag_datasets_config import RAGDatasetConfig
        
        test_config = RAGDatasetConfig(
            name="test_dataset",
            display_name="Test Dataset",
            description="A test dataset for validation",
            azure_search_index="test-idx",
            system_prompt="You are a test assistant",
            agent_instructions="Test instructions",
            max_results=3,
            enabled=False  # Keep disabled for testing
        )
        
        # Save current state
        original_datasets = len(rag_datasets_config.datasets)
        
        # Add test dataset
        rag_datasets_config.add_dataset(test_config)
        print(f"✅ Added test dataset: {len(rag_datasets_config.datasets)} total datasets")
        
        # Remove test dataset
        rag_datasets_config.remove_dataset("test_dataset")
        print(f"✅ Removed test dataset: {len(rag_datasets_config.datasets)} total datasets")
        
        # Verify back to original state
        if len(rag_datasets_config.datasets) == original_datasets:
            print("✅ Configuration management working correctly")
        else:
            print("⚠️ Configuration management may have issues")
            
    except Exception as e:
        print(f"❌ Configuration management error: {e}")
    
    print("\n" + "=" * 50)
    print("🎉 RAG System Test Complete!")
    print("\nNEXT STEPS:")
    print("1. Configure Azure AI Search endpoint and key in environment variables")
    print("2. Configure Azure OpenAI endpoint and key for embeddings and chat")
    print("3. Create your Azure AI Search indexes with the required schema")
    print("4. Add your datasets to the rag_datasets.json configuration file")
    print("5. Test with real queries once Azure services are configured")
    
    # Show sample configuration
    print("\nSAMPLE ENVIRONMENT VARIABLES:")
    print("AZURE_SEARCH_ENDPOINT=https://your-search-service.search.windows.net")
    print("AZURE_SEARCH_KEY=your-search-admin-key")
    print("AZURE_OPENAI_ENDPOINT=https://your-openai-service.openai.azure.com")
    print("AZURE_OPENAI_API_KEY=your-openai-api-key")
    print("AZURE_OPENAI_DEPLOYMENT=your-chat-deployment-name")
    print("AZURE_OPENAI_EMBEDDING_DEPLOYMENT=your-embedding-deployment-name")

if __name__ == "__main__":
    asyncio.run(test_rag_system())
