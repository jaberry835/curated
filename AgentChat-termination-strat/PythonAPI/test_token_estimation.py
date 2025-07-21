#!/usr/bin/env python3
"""
Test script to verify pure Python token estimation accuracy and performance.
This script tests the token management service without external dependencies.
"""

import sys
import os
import time
from typing import Dict, List, Tuple

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from services.token_management import TokenManager


def test_token_estimation():
    """Test the pure Python token estimation with various text samples."""
    
    print("🧪 Testing Pure Python Token Estimation")
    print("=" * 60)
    
    # Initialize the token management service
    token_service = TokenManager()
    
    # Test cases with expected approximate token counts
    test_cases = [
        ("Hello world", 2, "Simple greeting"),
        ("The quick brown fox jumps over the lazy dog", 9, "Classic pangram"),
        ("This is a longer sentence with multiple words and some punctuation!", 14, "Complex sentence"),
        ("123 456 789", 6, "Numbers"),
        ("user@example.com", 3, "Email address"),
        ("https://www.example.com/path?param=value", 8, "URL"),
        ("import json\ndata = {'key': 'value'}\nprint(json.dumps(data))", 18, "Code snippet"),
        ("AI models like GPT-4 can process natural language efficiently.", 12, "Technical text"),
        ("🚀 🌟 ✨ Emojis and special characters! @#$%^&*()", 14, "Special characters and emojis"),
        ("A" * 100, 25, "Repeated characters"),
        ("", 0, "Empty string"),
        ("   ", 1, "Whitespace only"),
        ("""
        This is a multi-line text that contains
        several sentences across different lines.
        It should be counted properly by our
        token estimation algorithm.
        """, 25, "Multi-line text"),
    ]
    
    results = []
    total_start = time.time()
    
    for i, (text, expected_approx, description) in enumerate(test_cases, 1):
        print(f"\n📝 Test {i}: {description}")
        print(f"   Text: {repr(text[:50] + '...' if len(text) > 50 else text)}")
        
        # Time the token counting
        start_time = time.time()
        token_count = token_service.count_tokens(text)
        end_time = time.time()
        
        duration_ms = (end_time - start_time) * 1000
        
        # Calculate accuracy (within reasonable range)
        accuracy = abs(token_count - expected_approx) / max(expected_approx, 1)
        is_reasonable = accuracy <= 0.5  # Within 50% is reasonable for estimation
        
        print(f"   🔢 Estimated tokens: {token_count}")
        print(f"   📊 Expected ~{expected_approx} tokens")
        print(f"   ⚡ Duration: {duration_ms:.2f}ms")
        print(f"   ✅ Reasonable: {'Yes' if is_reasonable else 'No'}")
        
        results.append({
            'description': description,
            'text_length': len(text),
            'estimated_tokens': token_count,
            'expected_tokens': expected_approx,
            'duration_ms': duration_ms,
            'accuracy': accuracy,
            'reasonable': is_reasonable
        })
    
    total_duration = time.time() - total_start
    
    # Summary statistics
    print("\n" + "=" * 60)
    print("📊 SUMMARY STATISTICS")
    print("=" * 60)
    
    reasonable_count = sum(1 for r in results if r['reasonable'])
    avg_duration = sum(r['duration_ms'] for r in results) / len(results)
    avg_accuracy = sum(r['accuracy'] for r in results) / len(results)
    
    print(f"✅ Tests passed: {reasonable_count}/{len(results)} ({reasonable_count/len(results)*100:.1f}%)")
    print(f"⚡ Average duration: {avg_duration:.2f}ms")
    print(f"📊 Average accuracy: {avg_accuracy:.1%}")
    print(f"🕐 Total test time: {total_duration:.2f}s")
    
    # Performance test with larger text
    print("\n" + "=" * 60)
    print("🚀 PERFORMANCE TEST")
    print("=" * 60)
    
    # Create a large text sample
    large_text = """
    Azure OpenAI Service provides REST API access to OpenAI's powerful language models including GPT-4, GPT-3.5-Turbo, and Embeddings model series. These models can be easily adapted to your specific task including but not limited to content generation, summarization, semantic search, and natural language to code translation. Users can access the service through REST APIs, Python SDK, or our web-based interface in the Azure OpenAI Studio.
    
    The Multi-Agent System is a sophisticated architecture that coordinates multiple specialized AI agents to handle complex queries. Each agent has specific capabilities:
    - Document Agent: Handles document storage, retrieval, and search operations
    - ADX Agent: Manages Azure Data Explorer queries and database operations  
    - Fictional Companies Agent: Provides fictional company data and IP address lookups
    - Math Agent: Performs mathematical calculations and statistical analysis
    - Utility Agent: Handles utility functions like hash generation and formatting
    - Coordinator Agent: Orchestrates the overall conversation and synthesizes responses
    
    The system uses advanced token management to ensure conversations stay within the 128K token limit of GPT-4, automatically optimizing and truncating context when necessary. This production-safe implementation uses pure Python for token estimation, eliminating external dependencies while maintaining accuracy.
    """ * 10  # Repeat to make it larger
    
    print(f"📄 Large text sample: {len(large_text):,} characters")
    
    # Test performance with large text
    start_time = time.time()
    large_token_count = token_service.count_tokens(large_text)
    end_time = time.time()
    
    duration_ms = (end_time - start_time) * 1000
    chars_per_ms = len(large_text) / duration_ms
    
    print(f"🔢 Estimated tokens: {large_token_count:,}")
    print(f"⚡ Duration: {duration_ms:.2f}ms")
    print(f"🚄 Processing speed: {chars_per_ms:.0f} chars/ms")
    print(f"📊 Chars per token: {len(large_text) / large_token_count:.1f}")
    
    # Test token limit checking
    print("\n" + "=" * 60)
    print("🔒 TOKEN LIMIT TESTING")
    print("=" * 60)
    
    # Test messages that would exceed limits
    test_messages = [
        "Short message",
        "A" * 1000,  # 1K chars
        "B" * 10000,  # 10K chars  
        "C" * 100000,  # 100K chars
        "D" * 500000,  # 500K chars (should trigger optimization)
    ]
    
    for i, message in enumerate(test_messages, 1):
        tokens = token_service.count_tokens(message)
        within_limit = tokens <= token_service.MAX_TOKENS
        
        print(f"📝 Message {i}: {len(message):,} chars → {tokens:,} tokens")
        print(f"   🚦 Within limit: {'✅ Yes' if within_limit else '❌ No'}")
        
        if not within_limit:
            print(f"   ⚠️  Exceeds limit by {tokens - token_service.MAX_TOKENS:,} tokens")
    
    print("\n" + "=" * 60)
    print("🎉 TOKEN ESTIMATION TEST COMPLETED")
    print("=" * 60)
    
    return results


if __name__ == "__main__":
    try:
        results = test_token_estimation()
        
        # Check if most tests passed
        reasonable_count = sum(1 for r in results if r['reasonable'])
        if reasonable_count >= len(results) * 0.8:  # 80% success rate
            print("\n✅ Token estimation is working well!")
            sys.exit(0)
        else:
            print(f"\n⚠️  Token estimation needs improvement ({reasonable_count}/{len(results)} tests passed)")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Error running token estimation test: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
