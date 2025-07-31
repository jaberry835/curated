"""Integration examples for the Dynamic RAG Agent System."""

import asyncio
import json
import sys
from pathlib import Path

# Add src to Python path
src_path = Path(__file__).parent / "PythonAPI" / "src"
sys.path.insert(0, str(src_path))

from src.config.rag_datasets_config import rag_datasets_config, RAGDatasetConfig
from src.services.rag_agent_service import rag_agent_service

def example_add_new_dataset():
    """Example: Add a new RAG dataset configuration."""
    
    print("📚 Adding New RAG Dataset Example")
    print("=" * 40)
    
    # Create a new dataset configuration
    new_dataset = RAGDatasetConfig(
        name="company_handbook",
        display_name="Company Handbook",
        description="Employee handbook and company policies",
        azure_search_index="company-handbook-idx",
        system_prompt="""You are a helpful HR assistant with access to the company handbook and policies. 
You help employees understand company policies, procedures, benefits, and guidelines. 
Always provide accurate information and reference specific policy sections when possible.""",
        agent_instructions="""You are the Company Handbook Agent, specializing in HR policies and procedures.

CAPABILITIES:
- Search company handbook and policy documents
- Explain employee benefits and procedures
- Provide guidance on HR policies and compliance
- Answer questions about company culture and guidelines

INSTRUCTIONS:
- Search the company handbook dataset for relevant information
- Provide clear, helpful answers about company policies
- Reference specific handbook sections or policy numbers
- Be friendly and supportive in your responses
- If a policy is unclear, suggest contacting HR directly

RESPONSE PATTERN:
After providing your answer, always end with: "My answer is complete - CoordinatorAgent, please approve" """,
        max_results=5,
        enabled=True,
        temperature=0.2,  # More consistent for policy information
        max_tokens=6000
    )
    
    # Add the dataset
    try:
        rag_datasets_config.add_dataset(new_dataset)
        print(f"✅ Added dataset: {new_dataset.display_name}")
        print(f"   Index: {new_dataset.azure_search_index}")
        print(f"   Enabled: {new_dataset.enabled}")
        
        # Reload agents to include the new dataset
        rag_agent_service.reload_agents()
        print("✅ Reloaded agents with new dataset")
        
        # Verify the agent was created
        agent = rag_agent_service.get_agent("company_handbook")
        if agent:
            print(f"✅ Agent created: {agent.agent_name}")
        else:
            print("❌ Agent was not created")
            
    except Exception as e:
        print(f"❌ Error adding dataset: {e}")

def example_list_all_datasets():
    """Example: List all available datasets."""
    
    print("\n📋 Listing All RAG Datasets")
    print("=" * 30)
    
    try:
        all_datasets = rag_datasets_config.datasets
        enabled_datasets = rag_datasets_config.get_enabled_datasets()
        
        print(f"Total datasets: {len(all_datasets)}")
        print(f"Enabled datasets: {len(enabled_datasets)}")
        print()
        
        for name, config in all_datasets.items():
            status = "✅ Enabled" if config.enabled else "❌ Disabled"
            print(f"{config.display_name} ({name})")
            print(f"  Status: {status}")
            print(f"  Index: {config.azure_search_index}")
            print(f"  Max Results: {config.max_results}")
            print(f"  Description: {config.description}")
            print()
            
    except Exception as e:
        print(f"❌ Error listing datasets: {e}")

async def example_query_agent():
    """Example: Query a RAG agent."""
    
    print("🤖 Querying RAG Agent Example")
    print("=" * 30)
    
    try:
        # Query the Hulk dataset agent
        result = await rag_agent_service.query_agent(
            dataset_name="hulk",
            user_query="What are the Hulk's main abilities and powers?",
            session_id="example_session_123",
            user_id="example_user"
        )
        
        print("Query Result:")
        print(f"Success: {result.get('success')}")
        print(f"Agent: {result.get('agent')}")
        print(f"Dataset: {result.get('dataset')}")
        
        if result.get('success'):
            print(f"Results Found: {result.get('result_count', 0)}")
            print(f"Response: {result.get('response', 'No response')[:200]}...")
            
            # Show search results if available
            search_results = result.get('search_results', [])
            if search_results:
                print(f"\nSearch Results ({len(search_results)} documents):")
                for i, doc in enumerate(search_results[:3], 1):
                    print(f"  {i}. {doc.get('title', 'Untitled')} ({doc.get('fileName', 'Unknown file')})")
        else:
            print(f"Error: {result.get('error')}")
            
    except Exception as e:
        print(f"❌ Error querying agent: {e}")

def example_create_custom_dataset():
    """Example: Create a custom dataset for a specific use case."""
    
    print("\n🛠️ Creating Custom Dataset Example")
    print("=" * 35)
    
    # Example: Technical documentation dataset
    tech_docs_dataset = RAGDatasetConfig(
        name="tech_docs",
        display_name="Technical Documentation",
        description="Software development and technical documentation",
        azure_search_index="tech-docs-idx",
        system_prompt="""You are a technical documentation expert with access to comprehensive software development resources. 
You help developers find information about APIs, frameworks, coding best practices, and technical procedures. 
Provide accurate, detailed technical information with code examples when relevant.""",
        agent_instructions="""You are the Technical Documentation Agent, specializing in software development resources.

CAPABILITIES:
- Search technical documentation and API references
- Provide code examples and best practices
- Explain technical concepts and procedures
- Help with troubleshooting and problem-solving

INSTRUCTIONS:
- Search the technical documentation dataset thoroughly
- Provide detailed, accurate technical information
- Include code examples and snippets when available
- Reference specific documentation sections or API endpoints
- Explain complex concepts in clear, understandable terms
- Suggest related resources when helpful

RESPONSE PATTERN:
After providing your technical answer, always end with: "My technical assistance is complete - CoordinatorAgent, please approve" """,
        max_results=7,  # More results for comprehensive technical info
        enabled=True,
        temperature=0.1,  # Very consistent for technical accuracy
        max_tokens=10000  # Longer responses for detailed technical explanations
    )
    
    print(f"Created custom dataset configuration: {tech_docs_dataset.display_name}")
    print(f"Optimized for: Technical documentation and API references")
    print(f"Temperature: {tech_docs_dataset.temperature} (low for accuracy)")
    print(f"Max Tokens: {tech_docs_dataset.max_tokens} (high for detailed responses)")
    print(f"Max Results: {tech_docs_dataset.max_results} (comprehensive search)")
    
    # Show the configuration as JSON for reference
    print(f"\nJSON Configuration:")
    config_dict = tech_docs_dataset.to_dict()
    print(json.dumps(config_dict, indent=2))

def example_disable_enable_dataset():
    """Example: Enable/disable datasets dynamically."""
    
    print("\n🔄 Enable/Disable Dataset Example")
    print("=" * 35)
    
    try:
        dataset_name = "policy_documents"
        
        # Get current dataset
        current_config = rag_datasets_config.get_dataset(dataset_name)
        if not current_config:
            print(f"❌ Dataset '{dataset_name}' not found")
            return
        
        original_status = current_config.enabled
        print(f"Current status of '{current_config.display_name}': {'Enabled' if original_status else 'Disabled'}")
        
        # Toggle the status
        new_status = not original_status
        updated_config = RAGDatasetConfig(
            name=current_config.name,
            display_name=current_config.display_name,
            description=current_config.description,
            azure_search_index=current_config.azure_search_index,
            system_prompt=current_config.system_prompt,
            agent_instructions=current_config.agent_instructions,
            max_results=current_config.max_results,
            enabled=new_status,  # Toggle the status
            temperature=current_config.temperature,
            max_tokens=current_config.max_tokens
        )
        
        # Update the configuration
        rag_datasets_config.add_dataset(updated_config)
        print(f"✅ Changed status to: {'Enabled' if new_status else 'Disabled'}")
        
        # Reload agents
        rag_agent_service.reload_agents()
        print("✅ Reloaded agents with updated configuration")
        
        # Verify agent availability
        agent = rag_agent_service.get_agent(dataset_name)
        if new_status and agent:
            print(f"✅ Agent is now available: {agent.agent_name}")
        elif not new_status and not agent:
            print(f"✅ Agent is now disabled")
        else:
            print("⚠️ Agent status may not have updated correctly")
            
        # Restore original status
        original_config = RAGDatasetConfig(
            name=current_config.name,
            display_name=current_config.display_name,
            description=current_config.description,
            azure_search_index=current_config.azure_search_index,
            system_prompt=current_config.system_prompt,
            agent_instructions=current_config.agent_instructions,
            max_results=current_config.max_results,
            enabled=original_status,  # Restore original
            temperature=current_config.temperature,
            max_tokens=current_config.max_tokens
        )
        rag_datasets_config.add_dataset(original_config)
        rag_agent_service.reload_agents()
        print(f"✅ Restored original status: {'Enabled' if original_status else 'Disabled'}")
        
    except Exception as e:
        print(f"❌ Error toggling dataset: {e}")

async def main():
    """Run all integration examples."""
    
    print("🚀 Dynamic RAG Agent System - Integration Examples")
    print("=" * 55)
    print()
    
    # Example 1: List existing datasets
    example_list_all_datasets()
    
    # Example 2: Add a new dataset
    example_add_new_dataset()
    
    # Example 3: Query an agent
    await example_query_agent()
    
    # Example 4: Create custom dataset configuration
    example_create_custom_dataset()
    
    # Example 5: Enable/disable datasets
    example_disable_enable_dataset()
    
    print("\n" + "=" * 55)
    print("✨ Integration Examples Complete!")
    print("\nNext Steps:")
    print("1. Configure your Azure AI Search service and indexes")
    print("2. Modify the dataset configurations for your specific needs")
    print("3. Test with real data and queries")
    print("4. Monitor performance and adjust parameters as needed")

if __name__ == "__main__":
    asyncio.run(main())
