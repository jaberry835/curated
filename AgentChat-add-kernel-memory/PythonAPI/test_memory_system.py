#!/usr/bin/env python3
"""
Test script for demonstrating the memory functionality with Semantic Kernel ChatHistory.
This script shows how the memory system works with conversation context.
"""

import asyncio
import json
import os
import sys
from datetime import datetime

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from services.memory_service import MemoryService
from semantic_kernel.contents import ChatHistory

async def test_memory_system():
    """Test the memory system functionality."""
    print("🧠 Testing Memory System with Semantic Kernel ChatHistory")
    print("=" * 60)
    
    # Create a memory service instance
    memory_service = MemoryService()
    
    # Test session ID
    session_id = "test-session-123"
    user_id = "test-user"
    
    print(f"📝 Testing with session: {session_id}")
    print()
    
    # 1. Create a new chat history
    print("1️⃣ Creating new chat history...")
    chat_history = memory_service.create_chat_history(session_id)
    print(f"   ✅ Created ChatHistory with {len(chat_history.messages)} initial messages")
    print()
    
    # 2. Add some conversation messages
    print("2️⃣ Adding conversation messages...")
    memory_service.add_user_message(session_id, "Hello! What can you help me with?", user_id)
    memory_service.add_assistant_message(session_id, "Hello! I'm an AI assistant that can help you with various tasks. I have access to specialized agents for different types of questions like math, data analysis, document management, and more. What would you like to know about?", "CoordinatorAgent")
    
    memory_service.add_user_message(session_id, "Can you calculate the factorial of 5?", user_id)
    memory_service.add_assistant_message(session_id, "I'll calculate the factorial of 5 for you. The factorial of 5 (5!) = 5 × 4 × 3 × 2 × 1 = 120", "MathAgent")
    
    memory_service.add_user_message(session_id, "What about some company information for IP 192.168.1.100?", user_id)
    memory_service.add_assistant_message(session_id, "Based on the IP address 192.168.1.100, this appears to be from TechCorp Limited. Here's the company information:\n\nCompany: TechCorp Limited\nIndustry: Technology Services\nLocation: Seattle, WA\nEmployees: 500-1000\nDevices: 45 network devices including servers, switches, and workstations.", "FictionalCompaniesAgent")
    
    updated_history = memory_service.get_chat_history(session_id)
    print(f"   ✅ Added conversation messages. Total messages: {len(updated_history.messages)}")
    print()
    
    # 3. Test serialization
    print("3️⃣ Testing serialization...")
    serialized_data = memory_service.serialize_chat_history(updated_history)
    print(f"   ✅ Serialized ChatHistory: {len(serialized_data)} characters")
    print(f"   📄 Sample serialized data (first 200 chars): {serialized_data[:200]}...")
    print()
    
    # 4. Test deserialization
    print("4️⃣ Testing deserialization...")
    new_session_id = "test-session-456"
    restored_history = memory_service.deserialize_chat_history(serialized_data, new_session_id)
    print(f"   ✅ Deserialized ChatHistory: {len(restored_history.messages)} messages")
    print()
    
    # 5. Test context summary
    print("5️⃣ Testing context summary...")
    context_summary = memory_service.get_context_summary(session_id, 500)
    print(f"   ✅ Generated context summary:")
    print(f"   📋 {context_summary}")
    print()
    
    # 6. Test memory reduction
    print("6️⃣ Testing memory reduction...")
    print(f"   📊 Messages before reduction: {len(updated_history.messages)}")
    
    # Add more messages to test reduction
    for i in range(10):
        memory_service.add_user_message(session_id, f"Test message {i+1}", user_id)
        memory_service.add_assistant_message(session_id, f"Response to test message {i+1}", "TestAgent")
    
    final_history = memory_service.get_chat_history(session_id)
    print(f"   📊 Messages after adding test messages: {len(final_history.messages)}")
    
    was_reduced = await memory_service.reduce_chat_history(session_id, target_count=15)
    reduced_history = memory_service.get_chat_history(session_id)
    print(f"   📊 Messages after reduction: {len(reduced_history.messages)}")
    print(f"   🔄 Reduction performed: {was_reduced}")
    print()
    
    # 7. Test tool message integration
    print("7️⃣ Testing tool message integration...")
    memory_service.simulate_function_call(session_id, "calculate_factorial", "call_001", {"number": 5})
    memory_service.add_tool_message(session_id, "calculate_factorial", "call_001", "120")
    
    tool_history = memory_service.get_chat_history(session_id)
    print(f"   ✅ Added tool messages. Total messages: {len(tool_history.messages)}")
    print()
    
    # 8. Display final conversation structure
    print("8️⃣ Final conversation structure:")
    for i, message in enumerate(tool_history.messages[-10:], 1):  # Show last 10 messages
        role = message.role.value if hasattr(message.role, 'value') else str(message.role)
        content = str(message.content)[:100] + "..." if len(str(message.content)) > 100 else str(message.content)
        name = getattr(message, 'name', 'N/A')
        print(f"   {i:2d}. [{role.upper()}] {name}: {content}")
    
    print()
    print("✅ Memory system test completed successfully!")
    print("=" * 60)


async def test_integration_scenario():
    """Test a more realistic integration scenario."""
    print("\n🔄 Testing Integration Scenario")
    print("=" * 60)
    
    memory_service = MemoryService()
    session_id = "integration-test-session"
    user_id = "integration-user"
    
    print("📚 Simulating a multi-turn conversation with context...")
    
    # Initialize session
    chat_history = memory_service.create_chat_history(session_id, max_messages=20)
    
    # Conversation flow
    conversations = [
        ("user", "Hi, I need help with some data analysis.", user_id),
        ("assistant", "Hello! I'd be happy to help you with data analysis. I have access to Azure Data Explorer and can run KQL queries. What kind of data are you working with?", "CoordinatorAgent"),
        ("user", "I have some sales data and want to find the top customers by revenue.", user_id),
        ("assistant", "I'll help you analyze your sales data to find the top customers by revenue. Let me query the sales database for you.", "ADXAgent"),
        ("user", "Actually, before that, can you calculate what 15% of $50,000 would be?", user_id),
        ("assistant", "I'll calculate 15% of $50,000 for you. 15% of $50,000 = 0.15 × $50,000 = $7,500", "MathAgent"),
        ("user", "Great! Now back to the sales analysis - can you show me the top 5 customers?", user_id),
        ("assistant", "Based on your sales data, here are the top 5 customers by revenue:\n1. ABC Corp - $150,000\n2. XYZ Industries - $125,000\n3. TechStart Inc - $98,000\n4. Global Solutions - $87,000\n5. Innovation Labs - $76,000", "ADXAgent"),
    ]
    
    # Add conversations to memory
    for role, content, name in conversations:
        if role == "user":
            memory_service.add_user_message(session_id, content, name)
        else:
            memory_service.add_assistant_message(session_id, content, name)
    
    # Test context awareness
    print("\n🧠 Testing context awareness...")
    context = memory_service.get_context_summary(session_id, 800)
    print(f"Context Summary:\n{context}")
    
    # Test serialization for persistence
    print("\n💾 Testing persistence simulation...")
    serialized = memory_service.serialize_chat_history(chat_history)
    print(f"Serialized conversation: {len(serialized)} characters")
    
    # Simulate loading from storage
    restored_session = "restored-session"
    restored_history = memory_service.deserialize_chat_history(serialized, restored_session)
    restored_context = memory_service.get_context_summary(restored_session, 400)
    
    print(f"\n🔄 Restored conversation context:\n{restored_context}")
    print(f"Original messages: {len(chat_history.messages)}")
    print(f"Restored messages: {len(restored_history.messages)}")
    
    print("\n✅ Integration scenario test completed!")


if __name__ == "__main__":
    print("🚀 AgentChat Memory System Demo")
    print("Using Semantic Kernel ChatHistory with CosmosDB persistence")
    print("=" * 80)
    
    async def run_tests():
        await test_memory_system()
        await test_integration_scenario()
        
        print("\n🎉 All tests completed successfully!")
        print("The memory system is ready for integration with your chat application.")
    
    # Run the tests
    asyncio.run(run_tests())
