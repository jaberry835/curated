"""Test RAG search with corrected field names."""

import asyncio
import logging
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.tools.rag_dataset_tools import rag_search_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_rag_search():
    """Test RAG search with corrected field names."""
    try:
        # Test searching the policy_documents dataset
        logger.info("🧪 Testing RAG search for policy_documents dataset...")
        
        result = await rag_search_service.search_dataset(
            dataset_name="policy_documents",
            query="test",  # Simple test query
            max_results=3
        )
        
        logger.info(f"✅ Search result: {result}")
        
        if result.get("success"):
            logger.info(f"🎉 Search successful! Found {result.get('count', 0)} results")
            for i, doc in enumerate(result.get("results", []), 1):
                logger.info(f"   📄 Result {i}: {doc.get('title', 'No title')}")
                logger.info(f"      Content preview: {doc.get('content', '')[:100]}...")
        else:
            logger.error(f"❌ Search failed: {result.get('error')}")
        
        # Test searching the hulk dataset
        logger.info("\n🧪 Testing RAG search for hulk dataset...")
        
        result2 = await rag_search_service.search_dataset(
            dataset_name="hulk",
            query="hulk",  # Simple test query
            max_results=3
        )
        
        logger.info(f"✅ Search result: {result2}")
        
        if result2.get("success"):
            logger.info(f"🎉 Search successful! Found {result2.get('count', 0)} results")
            for i, doc in enumerate(result2.get("results", []), 1):
                logger.info(f"   📄 Result {i}: {doc.get('title', 'No title')}")
                logger.info(f"      Content preview: {doc.get('content', '')[:100]}...")
        else:
            logger.error(f"❌ Search failed: {result2.get('error')}")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_rag_search())
