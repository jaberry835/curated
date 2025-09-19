from __future__ import annotations
import argparse
import hashlib
import os
from typing import List
from tqdm import tqdm

from .config import load_settings
from .s3_client import iter_s3_objects, get_s3_object_bytes
from .extract_text import extract_text
from .chunking import chunk_text
from .embeddings import EmbeddingClient
from .search_client import make_search_client, upload_docs, purge_all_docs
from .security_enricher import compute_allowed_principals_stub
from .index_management import ensure_index


def make_chunk_id(parent_id: str, idx: int) -> str:
    return f"{parent_id}__chunk_{idx:05d}"


def hash_parent_id(bucket: str, key: str) -> str:
    return hashlib.sha256(f"s3://{bucket}/{key}".encode("utf-8")).hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Index S3 docs into Azure AI Search with embeddings and security field")
    parser.add_argument("--bucket", default=os.getenv("S3_BUCKET"), help="S3 bucket name")
    parser.add_argument("--prefix", default=os.getenv("S3_PREFIX", ""), help="S3 key prefix")
    parser.add_argument("--max-files", type=int, default=0, help="Max number of files to process (0 = all)")
    parser.add_argument("--concurrency", type=int, default=int(os.getenv("CONCURRENCY", "4")))
    parser.add_argument("--skip-embed", action="store_true", help="Skip embeddings for debugging")
    parser.add_argument("--dry-run", action="store_true", help="Do not upload to search, just print counts")
    parser.add_argument("--ensure-index", action="store_true", help="Create the search index if it does not exist")
    parser.add_argument("--purge-index", action="store_true", help="Delete all documents from the index before indexing")
    parser.add_argument("--no-index", action="store_true", help="Do not index any S3 objects (useful with --purge-index)")

    args = parser.parse_args()
    settings = load_settings()

    if not args.bucket:
        raise SystemExit("--bucket or S3_BUCKET is required")

    # Init clients
    embed_client = None
    if not args.skip_embed:
        embed_client = EmbeddingClient(settings.aoai_endpoint, settings.aoai_embed_deployment, settings.aoai_api_key)
    if args.ensure_index:
        if not settings.search_api_key:
            raise SystemExit("--ensure-index requires AZURE_SEARCH_API_KEY")
        ensure_index(settings.search_service, settings.search_api_key, settings.search_index, settings.vector_dim)
    search_client = make_search_client(settings.search_service, settings.search_index, settings.search_api_key)
    if args.purge_index:
        try:
            deleted = purge_all_docs(search_client, key_field="chunk_id")
            print(f"Purged {deleted} document(s) from index '{settings.search_index}'.")
        except Exception as ex:
            raise SystemExit(f"Failed to purge index: {ex}")
        if args.no_index:
            # Stop right after purge
            try:
                remaining = search_client.get_document_count()
                print(f"Index '{settings.search_index}' now has {remaining} document(s).")
            except Exception:
                pass
            return

    processed = 0
    for obj in tqdm(iter_s3_objects(args.bucket, args.prefix), desc="S3 objects"):
        if args.max_files and processed >= args.max_files:
            break
        key = obj["key"]
        # download and extract text
        content = get_s3_object_bytes(obj["bucket"], key)
        text = extract_text(content, obj.get("content_type"), key)
        if not text:
            continue
        chunks = chunk_text(text, max_len=settings.chunk_len, overlap=settings.chunk_overlap)
        if not chunks:
            continue

        # embeddings
        vectors: List[List[float]] = [[] for _ in chunks]
        if embed_client:
            vectors = embed_client.embed_texts(chunks)

        # security enrichment
        # 1) From metadata via stub/endpoint (preferred)
        allowed_principals = compute_allowed_principals_stub(
            obj.get("metadata", {}),
            settings.security_enrich_url,
            timeout=settings.security_enrich_timeout,
            hint_key=settings.security_s3_meta_key,
        )
        # 2) From S3 tags if enabled and still empty
        if not allowed_principals and settings.use_s3_tag_for_allowedprincipals:
            tags = obj.get("tags", {}) or {}
            tag_val = tags.get(settings.allowedprincipals_tag_name)
            if tag_val:
                allowed_principals = [p.strip() for p in tag_val.replace(";", ",").split(",") if p.strip()]
        # 3) Default if still empty
        if not allowed_principals and settings.default_allowedprincipals:
            allowed_principals = [p.strip() for p in settings.default_allowedprincipals.replace(";", ",").split(",") if p.strip()]

        parent_id = hash_parent_id(obj["bucket"], key)
        title = key.split("/")[-1]

        # Shape allowedprincipals according to index schema
        if settings.allowedprincipals_mode == "string":
            ap_value = ",".join(allowed_principals) if allowed_principals else ""
        else:
            ap_value = allowed_principals

        docs = []
        for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
            doc = {
                "@search.action": "mergeOrUpload",
                "chunk_id": make_chunk_id(parent_id, i),  # key
                "parent_id": parent_id,
                "chunk": chunk,
                "title": title,
                "text_vector": vec,
                # Security trimming field per requirement
                "allowedprincipals": ap_value,
                # Extra metadata field requested by user: original file name
                "metaName": title,
            }
            docs.append(doc)

        if args.dry_run:
            print(f"Would upload {len(docs)} chunks for {key}")
        else:
            upload_docs(search_client, docs)

        processed += 1

    print(f"Done. Processed {processed} S3 object(s).")


if __name__ == "__main__":
    main()
