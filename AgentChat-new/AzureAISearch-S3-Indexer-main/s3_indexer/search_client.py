from __future__ import annotations
from typing import Iterable, List, Optional
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
import time


def make_search_client(service_endpoint: str, index_name: str, api_key: Optional[str]) -> SearchClient:
    if not service_endpoint or not index_name:
        raise ValueError("Search service endpoint and index name are required")
    if not api_key:
        # For brevity in this sample, require API key; AAD requires DefaultAzureCredential + RBAC
        raise ValueError("AZURE_SEARCH_API_KEY is required in this sample")
    return SearchClient(endpoint=service_endpoint, index_name=index_name, credential=AzureKeyCredential(api_key))


def upload_docs(client: SearchClient, docs: Iterable[dict]) -> List[dict]:
    actions = []
    for d in docs:
        d = dict(d)
        d["@search.action"] = d.get("@search.action", "mergeOrUpload")
        actions.append(d)
    if not actions:
        return []
    result = client.upload_documents(documents=actions)
    return [r.as_dict() for r in result]


def purge_all_docs(client: SearchClient, key_field: str = "chunk_id", batch_size: int = 1000, max_passes: int = 10) -> int:
    """Delete all documents from the index by enumerating keys and deleting in batches.

    Iterates all pages; then polls until the index is empty or max_passes reached.
    Returns the number of deleted documents (best-effort).
    """
    deleted_total = 0
    for _ in range(max_passes):
        # If nothing remains, stop
        try:
            remaining = client.get_document_count()
        except Exception:
            remaining = None
        if remaining == 0:
            break

        deleted_this_pass = 0
        batch = []
        # Iterate all results; SDK auto-paginates under the hood
        for doc in client.search(search_text="*", select=[key_field]):
            key = doc.get(key_field)
            if key is None:
                continue
            batch.append({key_field: key})
            if len(batch) >= batch_size:
                client.delete_documents(batch)
                deleted_this_pass += len(batch)
                batch = []
        if batch:
            client.delete_documents(batch)
            deleted_this_pass += len(batch)
        deleted_total += deleted_this_pass

        # Small delay to allow deletions to settle
        time.sleep(1.0)

        try:
            new_remaining = client.get_document_count()
        except Exception:
            new_remaining = None
        if new_remaining is not None and new_remaining > 0:
            # Continue another pass if documents still remain
            continue
        else:
            break

    return deleted_total
