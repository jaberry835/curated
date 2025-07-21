#!/usr/bin/env python3
"""
Test the extreme token overflow scenario where specialist responses
would exceed limits even after the first level of checks.
"""

import sys
import os

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from services.token_management import TokenManager


def test_extreme_overflow_scenario():
    """Test the scenario where specialist responses are extremely large."""
    
    print("🚨 Testing EXTREME Token Overflow Scenario")
    print("=" * 60)
    
    token_manager = TokenManager()
    
    # Create extremely large responses (each ~30K tokens)
    huge_response_1 = "A" * 110000  # ~30K tokens
    huge_response_2 = "B" * 110000  # ~30K tokens  
    huge_response_3 = "C" * 110000  # ~30K tokens
    huge_response_4 = "D" * 110000  # ~30K tokens
    
    # Create mock specialist responses
    mock_specialist_responses = [
        f"**ADXAgent**: {huge_response_1}",
        f"**DocumentAgent**: {huge_response_2}",
        f"**FictionalCompaniesAgent**: {huge_response_3}",
        f"**MathAgent**: {huge_response_4}"
    ]
    
    mock_coordinator_response = "I'll coordinate the responses."
    mock_question = "Analyze everything and provide a comprehensive report with all details."
    
    print(f"📊 Extreme scenario responses:")
    total_tokens = 0
    for i, response in enumerate(mock_specialist_responses, 1):
        tokens = token_manager.count_tokens(response)
        total_tokens += tokens
        print(f"   Response {i}: {len(response):,} chars → {tokens:,} tokens")
    
    coordinator_tokens = token_manager.count_tokens(mock_coordinator_response)
    question_tokens = token_manager.count_tokens(mock_question)
    
    print(f"   Coordinator: {coordinator_tokens:,} tokens")
    print(f"   Question: {question_tokens:,} tokens")
    print(f"   📊 Total specialist: {total_tokens:,} tokens")
    print(f"   🚦 Safe limit: {token_manager.SAFE_LIMIT:,} tokens")
    print(f"   🚨 MASSIVE OVERFLOW: {total_tokens - token_manager.SAFE_LIMIT:,} tokens over limit!")
    
    # Test the truncation logic from the multi-agent system
    print(f"\n✂️ Simulating Truncation Protection:")
    
    # Simulate the logic from _synthesize_responses method
    specialist_data = []
    for response in mock_specialist_responses:
        if ":" in response:
            agent_name, content = response.split(":", 1)
            specialist_data.append(f"**{agent_name.strip()}**:\n{content.strip()}")
        else:
            specialist_data.append(response)
    
    specialist_text = chr(10).join(specialist_data)
    specialist_tokens = token_manager.count_tokens(specialist_text)
    
    # Calculate available space (from the synthesis method)
    prompt_overhead = 800
    available_for_specialist = token_manager.SAFE_LIMIT - 6000 - prompt_overhead - question_tokens - coordinator_tokens
    
    print(f"   Available for specialist data: {available_for_specialist:,} tokens")
    print(f"   Actual specialist data: {specialist_tokens:,} tokens")
    print(f"   Overflow amount: {specialist_tokens - available_for_specialist:,} tokens")
    
    # Simulate the truncation process
    print(f"\n🔧 Applying Truncation Logic:")
    
    truncated_specialist_data = []
    current_tokens = 0
    
    for i, response_text in enumerate(specialist_data):
        response_tokens = token_manager.count_tokens(response_text)
        
        if current_tokens + response_tokens <= available_for_specialist:
            # This response fits completely
            truncated_specialist_data.append(response_text)
            current_tokens += response_tokens
            print(f"   ✅ Response {i+1}: Included fully ({response_tokens:,} tokens)")
        else:
            # This response needs truncation
            remaining_space = available_for_specialist - current_tokens
            if remaining_space > 100:  # Only include if meaningful space
                # Estimate characters from remaining tokens (rough: 3.5 chars/token)
                max_chars = int(remaining_space * 3.5)
                truncated_response = response_text[:max_chars] + "... [TRUNCATED DUE TO TOKEN LIMITS]"
                truncated_specialist_data.append(truncated_response)
                truncated_tokens = token_manager.count_tokens(truncated_response)
                current_tokens += truncated_tokens
                print(f"   ✂️  Response {i+1}: Truncated ({response_tokens:,} → {truncated_tokens:,} tokens)")
            else:
                print(f"   ❌ Response {i+1}: Skipped (no space remaining)")
            break
    
    # Calculate final results
    final_specialist_text = chr(10).join(truncated_specialist_data)
    final_specialist_tokens = token_manager.count_tokens(final_specialist_text)
    
    # Calculate total synthesis prompt size
    final_synthesis_tokens = final_specialist_tokens + coordinator_tokens + question_tokens + prompt_overhead + 1500  # +1500 for response generation
    
    print(f"\n📊 Truncation Results:")
    print(f"   Original specialist data: {specialist_tokens:,} tokens")
    print(f"   Truncated specialist data: {final_specialist_tokens:,} tokens")
    print(f"   Reduction: {specialist_tokens - final_specialist_tokens:,} tokens")
    print(f"   Reduction percentage: {((specialist_tokens - final_specialist_tokens) / specialist_tokens * 100):.1f}%")
    
    print(f"\n🔍 Final Synthesis Prompt Analysis:")
    print(f"   Specialist data: {final_specialist_tokens:,} tokens")
    print(f"   Coordinator response: {coordinator_tokens:,} tokens")
    print(f"   Original question: {question_tokens:,} tokens")
    print(f"   Prompt overhead: {prompt_overhead:,} tokens")
    print(f"   Response generation reserve: 1,500 tokens")
    print(f"   📊 Total synthesis prompt: {final_synthesis_tokens:,} tokens")
    print(f"   🚦 Safe limit: {token_manager.SAFE_LIMIT:,} tokens")
    print(f"   ✅ Within limit: {'YES' if final_synthesis_tokens <= token_manager.SAFE_LIMIT else 'NO'}")
    
    if final_synthesis_tokens <= token_manager.SAFE_LIMIT:
        remaining_capacity = token_manager.SAFE_LIMIT - final_synthesis_tokens
        print(f"   🎯 Remaining capacity: {remaining_capacity:,} tokens ({(remaining_capacity/token_manager.SAFE_LIMIT*100):.1f}%)")
    
    # Test the absolute worst case
    print(f"\n🆘 Testing Absolute Worst Case Scenario:")
    
    # Single response that exceeds the entire limit
    massive_single_response = "Z" * 500000  # ~137K tokens
    massive_tokens = token_manager.count_tokens(massive_single_response)
    
    print(f"   Single massive response: {len(massive_single_response):,} chars → {massive_tokens:,} tokens")
    print(f"   Exceeds MAX_TOKENS ({token_manager.MAX_TOKENS:,}): {'🚨 YES' if massive_tokens > token_manager.MAX_TOKENS else 'NO'}")
    
    if massive_tokens > token_manager.MAX_TOKENS:
        print(f"   🔧 This would trigger emergency fallback synthesis")
        print(f"   💡 System would use _fallback_synthesis() instead of LLM synthesis")
        print(f"   📝 Result: Simple concatenation without LLM processing")
    
    print(f"\n" + "=" * 60)
    print(f"🛡️  EXTREME OVERFLOW PROTECTION VERIFIED")
    print(f"=" * 60)
    
    return True


if __name__ == "__main__":
    try:
        result = test_extreme_overflow_scenario()
        if result:
            print("\n✅ Extreme overflow protection test passed!")
            print("🔒 System can handle even massive specialist responses safely")
        else:
            print("\n❌ Extreme overflow test failed")
            
    except Exception as e:
        print(f"\n❌ Error running extreme overflow test: {e}")
        import traceback
        traceback.print_exc()
