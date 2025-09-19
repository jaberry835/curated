from __future__ import annotations
from typing import Optional
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchField,
    SearchFieldDataType,
    SearchSuggester,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchAlgorithmMetric,
    VectorSearchProfile,
)


def ensure_index(
    service_endpoint: str,
    api_key: str,
    index_name: str,
    vector_dim: Optional[int],
) -> None:
    """Create the index if it doesn't exist, with required fields.

    Fields created:
      - chunk_id (key)
      - parent_id
      - chunk
      - title
      - text_vector (Collection(Edm.Single)) with vector config
      - allowedprincipals (Collection(Edm.String), filterable, retrievable=false)
    """
    client = SearchIndexClient(endpoint=service_endpoint, credential=AzureKeyCredential(api_key))

    # Fast existence check
    try:
        existing = client.get_index(index_name)
        return  # already exists
    except Exception:
        pass

    if not vector_dim or vector_dim <= 0:
        # Reasonable default for popular models (text-embedding-ada-002, text-embedding-3-small)
        vector_dim = 1536

    fields = [
        SimpleField(name="chunk_id", type=SearchFieldDataType.String, key=True, filterable=False, sortable=True),
        SimpleField(name="parent_id", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="chunk", type=SearchFieldDataType.String, searchable=True),
        SearchField(name="title", type=SearchFieldDataType.String, searchable=True),
        SearchField(
            name="text_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=vector_dim,
            vector_search_profile_name="default-profile",
        ),
        SearchField(
            name="allowedprincipals",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            filterable=True,
            retrievable=False,
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(name="hnsw", parameters={"m": 4, "efConstruction": 400}, metric=VectorSearchAlgorithmMetric.COSINE)
        ],
        profiles=[VectorSearchProfile(name="default-profile", algorithm_configuration_name="hnsw")],
    )

    index = SearchIndex(name=index_name, fields=fields, vector_search=vector_search)
    client.create_index(index)
