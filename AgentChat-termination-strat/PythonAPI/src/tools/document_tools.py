"""Document management tools for the MCP server."""

import os
import json
import base64
import asyncio
from typing import List, Dict, Any, Optional

# Use relative imports since this is within the src package
try:
    from ..services.document_service import document_service
    from ..config.settings import settings
    from ..utils.logging import get_logger
except ImportError:
    # Fallback to absolute imports
    from src.services.document_service import document_service
    from src.config.settings import settings
    from src.utils.logging import get_logger

logger = get_logger(__name__)

def register_document_tools(mcp):
    """Register all document management tools with the MCP server."""
    
    @mcp.tool()
    async def list_documents(user_id: str, session_id: str = None, limit: int = 50) -> Dict[str, Any]:
        """List documents for a user/session.
        
        Args:
            user_id: User ID to list documents for
            session_id: Optional session ID to filter documents
            limit: Maximum number of documents to return
            
        Returns:
            Dictionary with list of documents and metadata
        """
        try:
            # Use the existing get_user_documents method
            documents = await document_service.get_user_documents(user_id, session_id)
            
            # Convert DocumentMetadata objects to dictionaries
            documents_list = [doc.to_dict() for doc in documents]
            
            # Limit results if requested
            if limit < len(documents_list):
                documents_list = documents_list[:limit]
                message = f"Showing first {limit} documents"
            else:
                message = f"Found {len(documents_list)} documents"
            
            return {
                "success": True,
                "documents": documents_list,
                "count": len(documents_list),
                "message": message
            }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "documents": [],
                "count": 0,
                "message": "Error listing documents"
            }
    
    @mcp.tool()
    async def get_document_metadata(document_id: str, user_id: str = None) -> Dict[str, Any]:
        """Get document metadata.
        
        Args:
            document_id: The ID of the document
            user_id: Optional user ID for access control
            
        Returns:
            Dictionary with document metadata
        """
        try:
            # Find document with context using existing method
            document_context = await document_service._find_document_with_context(document_id)
            if not document_context:
                return {
                    "success": False,
                    "error": "Document not found",
                    "message": "Document not found"
                }
            
            document_metadata, doc_user_id, session_id = document_context
            
            # Verify user access if provided
            if user_id and doc_user_id != user_id:
                return {
                    "success": False,
                    "error": "Access denied",
                    "message": "User does not have access to this document"
                }
            
            return {
                "success": True,
                "document": document_metadata,
                "message": "Document metadata retrieved successfully"
            }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Error getting document metadata"
            }
    
    @mcp.tool()
    async def download_document(document_id: str, user_id: str = None) -> Dict[str, Any]:
        """Download a document.
        
        Args:
            document_id: The ID of the document
            user_id: Optional user ID for access control
            
        Returns:
            Dictionary with download result including base64 encoded content
        """
        try:
            # Use existing download_document method
            content, file_name, content_type = await document_service.download_document(document_id, user_id)
            
            # Encode content as base64
            content_b64 = base64.b64encode(content).decode('utf-8')
            
            return {
                "success": True,
                "content": content_b64,
                "file_name": file_name,
                "content_type": content_type,
                "size": len(content),
                "message": "Document downloaded successfully"
            }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Error downloading document"
            }
    
    @mcp.tool()
    async def delete_document(document_id: str, user_id: str = None) -> Dict[str, Any]:
        """Delete a document.
        
        Args:
            document_id: The ID of the document
            user_id: Optional user ID for access control
            
        Returns:
            Dictionary with deletion result
        """
        try:
            # For now, return not implemented since the document_service doesn't have delete functionality
            return {
                "success": False,
                "error": "Delete functionality not implemented",
                "message": "Document deletion is not currently supported"
            }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Error deleting document"
            }
    
    @mcp.tool()
    async def search_documents(query: str, user_id: str, session_id: str = None, limit: int = 10) -> Dict[str, Any]:
        """Search documents using Azure AI Search.
        
        Args:
            query: Search query string (e.g., file name like "names.txt" or content description)
            user_id: User ID to search within
            session_id: Optional session ID to filter search
            limit: Maximum number of results to return
            
        Returns:
            Dictionary with search results containing:
              - success: Boolean indicating if search was successful
              - results: List of matching documents with documentId, fileName, and content preview
              - count: Number of results found
              - message: Human-readable message about the search results
              
        Each result in the results list contains:
          - documentId: The unique ID to use when retrieving document content
          - fileName: The name of the file
          - content: A snippet/preview of the matching content
          - score: Relevance score
        """
        try:
            logger.info(f"Searching for documents with query: '{query}', user_id: '{user_id}', session_id: '{session_id}'")
            
            # Use existing search_documents method
            chunks = await document_service.search_documents(query, user_id, session_id, limit)
            
            # Convert chunks to response format
            results = []
            for chunk in chunks:
                results.append({
                    'chunkId': chunk.chunk_id,
                    'documentId': chunk.document_id,
                    'content': chunk.content,
                    'score': chunk.score,
                    'chunkIndex': chunk.chunk_index,
                    'fileName': chunk.file_name
                })
            
            logger.info(f"Search completed. Found {len(results)} results for query '{query}'")
            if len(results) > 0:
                # Log more details about the results to help debug
                for i, result in enumerate(results[:3]):  # Log first 3 results
                    logger.info(f"Result {i+1}: documentId='{result.get('documentId')}', fileName='{result.get('fileName')}', score={result.get('score')}")
            else:
                logger.info(f"No results found for query '{query}'")
            
            return {
                "success": True,
                "query": query,
                "results": results,
                "count": len(results),
                "message": f"Found {len(results)} search results for '{query}'"
            }
                
        except Exception as e:
            logger.error(f"Error searching documents: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "query": query,
                "results": [],
                "count": 0,
                "message": f"Error searching documents: {str(e)}"
            }
    
    @mcp.tool()
    async def get_document_content_summary(document_id: str, user_id: str = None, max_length: int = 500) -> Dict[str, Any]:
        """Get a summary of document content for AI processing.
        
        Args:
            document_id: The ID of the document
            user_id: Optional user ID for access control
            max_length: Maximum length of content summary
            
        Returns:
            Dictionary with document content summary
        """
        try:
            # Use existing download_document method - it returns a dictionary
            download_result = await document_service.download_document(document_id, user_id)
            
            # Check if download was successful
            if not download_result.get("success", False):
                return {
                    "success": False,
                    "error": download_result.get("error", "Unknown error"),
                    "message": download_result.get("message", "Failed to download document")
                }
            
            # Extract values from the result dictionary
            file_name = download_result.get("file_name", "unknown")
            content_type = download_result.get("content_type", "application/octet-stream")
            content_b64 = download_result.get("content", "")
            
            # Decode base64 content
            import base64
            content = base64.b64decode(content_b64)
            
            # Try to decode as text for summary
            try:
                if content_type.startswith("text/"):
                    text_content = content.decode('utf-8')
                    summary = text_content[:max_length] + ("..." if len(text_content) > max_length else "")
                else:
                    summary = f"Binary file ({len(content)} bytes)"
                    
                return {
                    "success": True,
                    "document_id": document_id,
                    "file_name": file_name,
                    "content_type": content_type,
                    "size": len(content),
                    "summary": summary,
                    "is_text": content_type.startswith("text/"),
                    "message": "Document content summary retrieved"
                }
            except UnicodeDecodeError:
                return {
                    "success": True,
                    "document_id": document_id,
                    "file_name": file_name,
                    "content_type": content_type,
                    "size": len(content),
                    "summary": f"Binary file ({len(content)} bytes) - cannot decode as text",
                    "is_text": False,
                    "message": "Document content summary retrieved (binary file)"
                }
                    
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Error getting document content summary"
            }
    
    @mcp.tool()
    async def process_document(document_id: str, user_id: str = None) -> Dict[str, Any]:
        """Process a document for text extraction and search indexing.
        
        Args:
            document_id: The ID of the document to process
            user_id: Optional user ID for access control
            
        Returns:
            Dictionary with processing result
        """
        try:
            # Use existing process_document method
            result = await document_service.process_document(document_id)
            
            return {
                "success": result.success,
                "document_id": result.document_id,
                "chunk_count": result.chunk_count,
                "extracted_text_length": len(result.extracted_text) if result.extracted_text else 0,
                "error_message": result.error_message,
                "message": "Document processed successfully" if result.success else f"Processing failed: {result.error_message}"
            }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Error processing document"
            }

# Direct function implementation for MCP client
async def list_documents_impl(user_id: str, session_id: str = None, limit: int = 50, prefix: str = None):
    """Direct implementation of list_documents for MCP client."""
    from src.services.document_service import document_service
    from src.utils.logging import get_logger
    logger = get_logger(__name__)
    
    try:
        # Use the existing get_user_documents method
        documents = await document_service.get_user_documents(user_id, session_id)
        
        # Convert DocumentMetadata objects to dictionaries
        documents_list = [doc.to_dict() for doc in documents]
        
        # Filter by prefix if provided
        if prefix:
            documents_list = [doc for doc in documents_list if doc.get('fileName', '').startswith(prefix)]
        
        # Limit results if requested
        if limit < len(documents_list):
            documents_list = documents_list[:limit]
            message = f"Showing first {limit} documents"
        else:
            message = f"Found {len(documents_list)} documents"
        
        return {
            "success": True,
            "documents": documents_list,
            "count": len(documents_list),
            "message": message
        }
            
    except Exception as e:
        logger.error(f"Error listing documents: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "documents": [],
            "count": 0,
            "message": "Error listing documents"
        }

async def get_document_metadata_impl(document_id: str, user_id: str = None, session_id: str = None):
    """Direct implementation of get_document_metadata for MCP client."""
    from src.services.document_service import document_service
    from src.utils.logging import get_logger
    logger = get_logger(__name__)
    
    try:
        # Find document with context using existing method
        document_context = await document_service._find_document_with_context(document_id)
        if not document_context:
            return {
                "success": False,
                "error": "Document not found",
                "message": "Document not found"
            }
        
        document_metadata, doc_user_id, session_id = document_context
        
        # Verify user access if provided
        if user_id and doc_user_id != user_id:
            return {
                "success": False,
                "error": "Access denied",
                "message": "User does not have access to this document"
            }
        
        return {
            "success": True,
            "document": document_metadata,
            "message": "Document metadata retrieved successfully"
        }
            
    except Exception as e:
        logger.error(f"Error getting document metadata: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "message": "Error getting document metadata"
        }

async def download_document_impl(document_id: str, user_id: str = None):
    """Direct implementation of download_document for MCP client."""
    import base64
    from src.services.document_service import document_service
    from src.utils.logging import get_logger
    logger = get_logger(__name__)
    
    try:
        # Use existing download_document method
        content, file_name, content_type = await document_service.download_document(document_id, user_id)
        
        # Encode content as base64
        content_b64 = base64.b64encode(content).decode('utf-8')
        
        return {
            "success": True,
            "content": content_b64,
            "file_name": file_name,
            "content_type": content_type,
            "size": len(content),
            "message": "Document downloaded successfully"
        }
            
    except Exception as e:
        logger.error(f"Error downloading document: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "message": "Error downloading document"
        }

async def search_documents_impl(query: str, user_id: str = None, session_id: str = None, limit: int = 10):
    """Direct implementation of search_documents for MCP client."""
    from src.services.document_service import document_service
    from src.utils.logging import get_logger
    logger = get_logger(__name__)
    
    try:
        logger.info(f"🔍 DIRECT IMPL: Searching for documents with query: '{query}', user_id: '{user_id}', session_id: '{session_id}'")
        
        if not user_id:
            # This was causing the bug - we should never use a default user_id
            # The user_id must be passed all the way through from the frontend
            error_msg = "❌ ERROR: search_documents_impl called without user_id parameter!"
            logger.error(error_msg)
            return {
                "error": "Missing required user_id parameter for document search",
                "success": False,
                "results": [],
                "count": 0,
                "message": "Document search failed: No user ID provided. Please ensure user_id is passed from the frontend to API and through to document tools."
            }
        
        # Use existing search_documents method
        result = await document_service.search_documents(query, user_id, session_id, limit)
        
        if not result.get("success", False):
            logger.error(f"Search error: {result.get('error', 'Unknown error')}")
            return result
            
        # Log search results
        results = result.get("results", [])
        logger.info(f"🔍 DIRECT IMPL: Found {len(results)} results for query '{query}'")
        
        # Log details about each result
        for i, r in enumerate(results[:3]):  # Log first 3 results
            logger.info(f"  Result {i+1}: documentId='{r.get('documentId')}', fileName='{r.get('fileName')}'")
        
        return result
            
    except Exception as e:
        logger.error(f"Error searching documents: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "query": query,
            "results": [],
            "count": 0,
            "message": f"Error searching documents: {str(e)}"
        }

async def get_document_content_summary_impl(document_id: str, user_id: str = None, session_id: str = None, max_length: int = 500):
    """Direct implementation of get_document_content_summary for MCP client."""
    from src.services.document_service import document_service
    from src.utils.logging import get_logger
    logger = get_logger(__name__)
    
    try:
        # Use existing download_document method - it returns a dictionary
        download_result = await document_service.download_document(document_id, user_id)
        
        # Check if download was successful
        if not download_result.get("success", False):
            return {
                "success": False,
                "error": download_result.get("error", "Unknown error"),
                "message": download_result.get("message", "Failed to download document")
            }
        
        # Extract values from the result dictionary
        file_name = download_result.get("file_name", "unknown")
        content_type = download_result.get("content_type", "application/octet-stream")
        content_b64 = download_result.get("content", "")
        
        # Decode base64 content
        import base64
        content = base64.b64decode(content_b64)
        
        # Try to decode as text for summary
        try:
            if content_type.startswith("text/"):
                text_content = content.decode('utf-8')
                summary = text_content[:max_length] + ("..." if len(text_content) > max_length else "")
            else:
                summary = f"Binary file ({len(content)} bytes)"
                
            return {
                "success": True,
                "document_id": document_id,
                "file_name": file_name,
                "content_type": content_type,
                "size": len(content),
                "summary": summary,
                "is_text": content_type.startswith("text/"),
                "message": "Document content summary retrieved"
            }
        except UnicodeDecodeError:
            return {
                "success": True,
                "document_id": document_id,
                "file_name": file_name,
                "content_type": content_type,
                "size": len(content),
                "summary": f"Binary file ({len(content)} bytes) - cannot decode as text",
                "is_text": False,
                "message": "Document content summary retrieved (binary file)"
            }
                
    except Exception as e:
        logger.error(f"Error getting document content summary: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "message": "Error getting document content summary"
        }
