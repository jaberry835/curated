from __future__ import annotations
from typing import List, Optional, Dict
import requests


def compute_allowed_principals_stub(s3_metadata: Dict[str, str], enrich_url: Optional[str], timeout: float = 5.0, hint_key: str = "x-allowedprincipal-hint") -> List[str]:
    """Stub: read custom S3 metadata and call an HTTP endpoint to resolve principals.

    - s3_metadata: dict from S3 Object Metadata (lowercased keys in boto3 HeadObject)
    - enrich_url: optional HTTP endpoint to call. If None, returns metadata hint if present.
    - timeout: seconds for HTTP call
    - hint_key: metadata key to read (e.g., 'x-allowedprincipal-hint')

    Expected endpoint contract (suggested):
    POST {enrich_url}
    { "hint": "<string>", "objectMetadata": { ... } }
    -> { "allowedPrincipals": ["group_id1", "group_id2"] }
    """
    principals: List[str] = []
    hint = s3_metadata.get(hint_key) if s3_metadata else None

    if enrich_url:
        try:
            resp = requests.post(enrich_url, json={"hint": hint, "objectMetadata": s3_metadata or {}}, timeout=timeout)
            resp.raise_for_status()
            data = resp.json() or {}
            ap = data.get("allowedPrincipals") or []
            if isinstance(ap, list):
                principals = [str(x) for x in ap if isinstance(x, (str, int))]
        except Exception:
            # In production, log the error; here we fallback to hint-only
            pass

    if not principals and hint:
        # support comma or semicolon separated hints
        principals = [p.strip() for p in hint.replace(";", ",").split(",") if p.strip()]

    return principals
