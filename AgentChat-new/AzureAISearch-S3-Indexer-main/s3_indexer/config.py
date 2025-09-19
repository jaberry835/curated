from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Load variables from a .env file if present
load_dotenv()


def _get(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    return v if v is not None else default


def _get_bool(name: str, default: str = "false") -> bool:
    v = (os.getenv(name) or default).strip().lower()
    return v in ("1", "true", "yes", "y", "on")


@dataclass
class Settings:
    # S3
    s3_bucket: str = _get("S3_BUCKET", "")
    s3_prefix: str = _get("S3_PREFIX", "")

    # Azure Search
    search_service: str = _get("AZURE_SEARCH_SERVICE", "")  # full https URL
    search_index: str = _get("AZURE_SEARCH_INDEX", "")
    search_api_key: Optional[str] = _get("AZURE_SEARCH_API_KEY")

    # Azure OpenAI
    aoai_endpoint: str = _get("AZURE_OPENAI_ENDPOINT", "")
    aoai_api_key: Optional[str] = _get("AZURE_OPENAI_API_KEY")
    aoai_embed_deployment: str = _get("AZURE_OPENAI_EMBED_DEPLOYMENT", "text-embedding-3-small")

    # Security enrichment
    security_enrich_url: Optional[str] = _get("SECURITY_ENRICH_URL")
    security_enrich_timeout: float = float(_get("SECURITY_ENRICH_TIMEOUT", "5"))
    security_s3_meta_key: str = _get("SECURITY_S3_META_KEY", "x-allowedprincipal-hint")

    # Behavior
    chunk_len: int = int(_get("CHUNK_LEN", "2000"))
    chunk_overlap: int = int(_get("CHUNK_OVERLAP", "500"))
    concurrency: int = int(_get("CONCURRENCY", "4"))
    # Optional: explicit vector dimension for index creation
    vector_dim: Optional[int] = int(_get("AZURE_SEARCH_VECTOR_DIM", "0")) or None
    # How to write allowedprincipals to the index: 'collection' (recommended) or 'string'
    allowedprincipals_mode: str = (_get("ALLOWEDPRINCIPALS_MODE", "collection") or "collection").lower()
    # Optional: default principals if none provided by metadata/tags/enricher
    default_allowedprincipals: str = _get("DEFAULT_ALLOWEDPRINCIPALS", "") or ""
    # Optionally read from S3 object tags
    use_s3_tag_for_allowedprincipals: bool = _get_bool("USE_S3_TAG_FOR_ALLOWEDPRINCIPALS", "false")
    allowedprincipals_tag_name: str = _get("ALLOWEDPRINCIPALS_TAG_NAME", "allowedprincipals") or "allowedprincipals"


def load_settings() -> Settings:
    return Settings()
