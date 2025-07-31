"""Test script to verify vector dimension fix."""

import asyncio
import logging
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.tools.rag_dataset_tools import rag_search_service
from src.config.rag_datasets_config import rag_datasets_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_vector_dimensions():
    """Test vector dimension compatibility."""
    try:
        # Reload config to pick up changes
        rag_datasets_config.reload_config()
        
        # Test each dataset
        for dataset_name in ["policy_documents", "hulk"]:
            logger.info(f"\n🧪 Testing vector dimensions for dataset: {dataset_name}")
            
            dataset_config = rag_datasets_config.get_dataset(dataset_name)
            if dataset_config:
                logger.info(f"📋 Dataset config:")
                logger.info(f"   - Embedding model: {dataset_config.embedding_model}")
                logger.info(f"   - Vector dimensions: {dataset_config.vector_dimensions}")
                logger.info(f"   - Vector search enabled: {dataset_config.enable_vector_search}")
                logger.info(f"   - Vector field: {dataset_config.vector_field}")
                
                # Test embedding generation
                embedding = await rag_search_service._generate_embedding("test query", dataset_config.embedding_model)
                if embedding:
                    logger.info(f"   - Generated embedding dimensions: {len(embedding)}")
                    if len(embedding) == dataset_config.vector_dimensions:
                        logger.info(f"   ✅ Vector dimensions match!")
                    else:
                        logger.warning(f"   ⚠️ Vector dimension mismatch: expected {dataset_config.vector_dimensions}, got {len(embedding)}")
                else:
                    logger.error(f"   ❌ Failed to generate embedding")
                
                # Test actual search
                logger.info(f"🔍 Testing search for dataset: {dataset_name}")
                result = await rag_search_service.search_dataset(
                    dataset_name=dataset_name,
                    query="budget information",
                    max_results=2
                )
                
                if result.get("success"):
                    logger.info(f"   ✅ Search successful! Found {result.get('count', 0)} results")
                    for i, doc in enumerate(result.get("results", []), 1):
                        logger.info(f"      📄 Result {i}: {doc.get('title', 'No title')[:50]}...")
                else:
                    logger.error(f"   ❌ Search failed: {result.get('error')}")
            else:
                logger.error(f"❌ Dataset config not found: {dataset_name}")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_vector_dimensions())
