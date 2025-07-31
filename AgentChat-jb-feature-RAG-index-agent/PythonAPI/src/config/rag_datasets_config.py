"""RAG Datasets Configuration for Dynamic Agent Creation."""

import json
import os
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class RAGDatasetConfig:
    """Configuration for a single RAG dataset."""
    name: str
    display_name: str
    description: str
    azure_search_index: str
    system_prompt: str
    agent_instructions: str
    max_results: int = 5
    enabled: bool = True
    temperature: float = 0.3
    max_tokens: int = 8000
    
    # Field mappings for Azure Search index fields
    content_field: str = "chunk"  # Default content field name
    vector_field: str = "text_vector"  # Default vector field name
    title_field: str = "title"  # Default title field name
    id_field: str = "id"  # Default ID field name
    
    # Embedding configuration
    embedding_model: str = "text-embedding-ada-002"  # Default embedding model
    vector_dimensions: int = 1536  # Default for text-embedding-ada-002
    enable_vector_search: bool = True  # Whether to use vector search
    
    # Optional fields - can be None if not needed
    filename_field: Optional[str] = None
    filepath_field: Optional[str] = None
    uploaded_at_field: Optional[str] = None
    metadata_field: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RAGDatasetConfig':
        """Create from dictionary."""
        return cls(**data)

class RAGDatasetsConfigManager:
    """Manager for RAG datasets configuration."""
    
    def __init__(self, config_file_path: str = None):
        """Initialize with config file path."""
        if config_file_path is None:
            # Default to config file in the same directory as this module
            config_dir = Path(__file__).parent
            config_file_path = config_dir / "rag_datasets.json"
        
        self.config_file_path = Path(config_file_path)
        self.datasets: Dict[str, RAGDatasetConfig] = {}
        self.load_config()
    
    def load_config(self) -> None:
        """Load datasets configuration from JSON file."""
        try:
            if not self.config_file_path.exists():
                logger.warning(f"RAG datasets config file not found: {self.config_file_path}")
                self.create_default_config()
                return
            
            with open(self.config_file_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            self.datasets.clear()
            for dataset_name, dataset_config in config_data.get('datasets', {}).items():
                try:
                    self.datasets[dataset_name] = RAGDatasetConfig.from_dict(dataset_config)
                    logger.info(f"✅ Loaded RAG dataset config: {dataset_name}")
                except Exception as e:
                    logger.error(f"❌ Failed to load dataset config '{dataset_name}': {e}")
            
            logger.info(f"🔧 Loaded {len(self.datasets)} RAG dataset configurations")
            
        except Exception as e:
            logger.error(f"Failed to load RAG datasets config: {e}")
            self.create_default_config()
    
    def create_default_config(self) -> None:
        """Create a default configuration file with example datasets."""
        default_config = {
            "datasets": {
                "hulk": {
                    "name": "hulk",
                    "display_name": "Hulk Dataset",
                    "description": "Dataset containing information about the Hulk character, stories, and related content",
                    "azure_search_index": "hulk-idx",
                    "system_prompt": "You are a knowledgeable assistant specializing in information about the Hulk character from Marvel Comics. You have access to comprehensive data about Hulk's stories, characters, powers, and related content.",
                    "agent_instructions": """You are the Hulk Dataset Agent, specializing in information about the Hulk character from Marvel Comics.

CAPABILITIES:
- Search for Hulk-related information in the dataset
- Provide detailed answers about Hulk stories, characters, and lore
- Retrieve specific content from Hulk comics and media
- Answer questions about Hulk's powers, abilities, and history

INSTRUCTIONS:
- Use the search capabilities to find relevant information in the Hulk dataset
- Provide comprehensive, accurate answers based on the dataset content
- If asked about information not in your dataset, clearly state the limitations
- Focus specifically on Hulk-related content and characters
- Present information in a clear, engaging manner

RESPONSE PATTERN:
After providing your answer, always end with: "My answer is complete - CoordinatorAgent, please approve"
""",
                    "max_results": 5,
                    "enabled": True,
                    "temperature": 0.3,
                    "max_tokens": 8000
                },
                "policy_documents": {
                    "name": "policy_documents", 
                    "display_name": "Policy Documents",
                    "description": "Corporate policy documents and procedures dataset",
                    "azure_search_index": "policy-docs-idx",
                    "system_prompt": "You are a corporate policy assistant with access to company policies, procedures, and guidelines. Help users find and understand policy information.",
                    "agent_instructions": """You are the Policy Documents Agent, specializing in corporate policies and procedures.

CAPABILITIES:
- Search for policy information in the corporate documents dataset
- Provide clear explanations of policies and procedures
- Help users understand compliance requirements
- Retrieve specific policy sections and guidelines

INSTRUCTIONS:
- Search the policy documents dataset for relevant information
- Provide accurate, up-to-date policy information
- Explain complex policies in clear, understandable terms
- Reference specific policy documents when possible
- Help users understand how policies apply to their situations

RESPONSE PATTERN:
After providing your answer, always end with: "My answer is complete - CoordinatorAgent, please approve"
""",
                    "max_results": 3,
                    "enabled": True,
                    "temperature": 0.2,
                    "max_tokens": 6000
                }
            }
        }
        
        try:
            # Ensure directory exists
            self.config_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_file_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✅ Created default RAG datasets config: {self.config_file_path}")
            self.load_config()  # Reload the default config
            
        except Exception as e:
            logger.error(f"Failed to create default RAG datasets config: {e}")
    
    def get_enabled_datasets(self) -> Dict[str, RAGDatasetConfig]:
        """Get all enabled datasets."""
        return {name: config for name, config in self.datasets.items() if config.enabled}
    
    def get_dataset(self, name: str) -> Optional[RAGDatasetConfig]:
        """Get a specific dataset configuration."""
        return self.datasets.get(name)
    
    def add_dataset(self, dataset_config: RAGDatasetConfig) -> None:
        """Add a new dataset configuration."""
        self.datasets[dataset_config.name] = dataset_config
        self.save_config()
    
    def remove_dataset(self, name: str) -> bool:
        """Remove a dataset configuration."""
        if name in self.datasets:
            del self.datasets[name]
            self.save_config()
            return True
        return False
    
    def save_config(self) -> None:
        """Save current configuration to file."""
        try:
            config_data = {
                "datasets": {
                    name: config.to_dict() 
                    for name, config in self.datasets.items()
                }
            }
            
            with open(self.config_file_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✅ Saved RAG datasets config: {self.config_file_path}")
            
        except Exception as e:
            logger.error(f"Failed to save RAG datasets config: {e}")
    
    def reload_config(self) -> None:
        """Reload configuration from file."""
        self.load_config()

# Global instance
rag_datasets_config = RAGDatasetsConfigManager()
