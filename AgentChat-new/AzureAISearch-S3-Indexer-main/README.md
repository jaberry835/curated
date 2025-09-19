# Azure AI Search S3 Indexer (Python)

A small tool that walks an Amazon S3 bucket, extracts text from files, chunks and embeddings with Azure OpenAI, and uploads chunks into an existing Azure AI Search index. Includes a stub to read custom S3 object metadata and call an HTTP endpoint to resolve a security trimming attribute, stored as `allowedprincipals`.

## Features
- Reads files from S3 (paged, prefix filter).
- Extracts text from PDFs and plain text; easily extend for others.
- Deterministic chunking (pages/length/overlap similar to portal defaults).
- Embeds chunks with Azure OpenAI embeddings.
- Pushes documents to an existing Azure AI Search index.
- Adds `allowedprincipals` (Collection(Edm.String), filterable, retrievable=false recommended).
  - If your index defines `allowedprincipals` as `Edm.String`, set `ALLOWEDPRINCIPALS_MODE=string` in `.env`.
  - Populate from (priority): S3 metadata via stub/HTTP -> S3 object tags -> DEFAULT_ALLOWEDPRINCIPALS.
  - Configure with `SECURITY_S3_META_KEY`, `USE_S3_TAG_FOR_ALLOWEDPRINCIPALS`, `ALLOWEDPRINCIPALS_TAG_NAME`, `DEFAULT_ALLOWEDPRINCIPALS`.
  - The sample adds `metaName` with the original filename (object key basename).
- Stub to enrich security attributes via custom S3 metadata + external HTTP endpoint.

## Prereqs
- Python 3.9+
- Azure AI Search service and an existing index (created in the portal wizard) with:
  - `chunk_id` (key)
  - `parent_id`
  - `chunk`
  - `title`
  - `text_vector` (Collection(Edm.Single))
  - `allowedprincipals` (Collection(Edm.String), filterable, retrievable=false)
- Azure OpenAI embedding deployment (e.g., `text-embedding-3-small`).
- IAM/keys to access S3 objects.

## Install
```pwsh
# In repo root
py -3 -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -U pip
pip install -e .
```

## Configure
Set environment variables (use `.env` if convenient):

```env
# S3
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1
S3_BUCKET=my-bucket
S3_PREFIX=optional/prefix/

# Azure AI Search
AZURE_SEARCH_SERVICE=https://<your-search>.search.windows.net
AZURE_SEARCH_INDEX=<your-index>
# Choose either Key or Entra ID (DefaultAzureCredential)
AZURE_SEARCH_API_KEY=<admin-or-query-key>
# If using Entra ID instead of key, omit AZURE_SEARCH_API_KEY and ensure your identity has roles.

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://<your-aoai>.openai.azure.com
AZURE_OPENAI_API_KEY=<key-if-not-using-credential>
AZURE_OPENAI_EMBED_DEPLOYMENT=text-embedding-3-small
# Optional: use DefaultAzureCredential by leaving API key empty and granting access.

# Optional: Security enricher endpoint
SECURITY_ENRICH_URL=https://example.com/resolve-principals
SECURITY_ENRICH_TIMEOUT=5
SECURITY_S3_META_KEY=x-allowedprincipal-hint
USE_S3_TAG_FOR_ALLOWEDPRINCIPALS=false
ALLOWEDPRINCIPALS_TAG_NAME=allowedprincipals
DEFAULT_ALLOWEDPRINCIPALS=

# If your index uses a single string field instead of a collection for security:
ALLOWEDPRINCIPALS_MODE=collection  # or "string" to emit comma-separated string
```

## Run
```pwsh
s3-indexer --bucket $env:S3_BUCKET --prefix $env:S3_PREFIX --max-files 100
```

Key options:
- `--bucket`, `--prefix`: S3 enumeration
- `--max-files`: limit for testing
- `--concurrency`: parallelism for embedding/indexing
- `--skip-embed`: push text only (debug)
- `--dry-run`: show what would be sent
- `--ensure-index`: create index if missing (minimal schema)
- `--purge-index`: delete all documents before indexing (keeps schema)
 - `--no-index`: skip indexing entirely (useful to purge and leave the index empty)

## Notes
- Text extraction: PDFs via `pypdf`, `.txt` as-is. Extend `extract_text.py` to add docx, html, etc.
- Chunking matches portal defaults approximately: 2000 chars, 500 overlap, pages if PDF.
- Index schema must include `allowedprincipals` as `Collection(Edm.String)` and filterable.
- Use `search.in(allowedprincipals, 'id1,id2')` in queries for trimming.

## License
MIT
