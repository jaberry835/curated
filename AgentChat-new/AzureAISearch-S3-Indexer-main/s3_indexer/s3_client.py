from __future__ import annotations
import boto3
from typing import Iterator, Optional, Dict, List


def iter_s3_objects(bucket: str, prefix: str = "", s3_client: Optional[boto3.client] = None) -> Iterator[dict]:
    """Yield S3 object metadata dicts using pagination."""
    s3 = s3_client or boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []) or []:
            key = item["Key"]
            head = s3.head_object(Bucket=bucket, Key=key)
            # Attempt to read tags (ignore errors if not allowed)
            tags: Dict[str, str] = {}
            try:
                tag_resp = s3.get_object_tagging(Bucket=bucket, Key=key)
                for t in tag_resp.get("TagSet", []) or []:
                    k = str(t.get("Key", ""))
                    v = str(t.get("Value", ""))
                    tags[k] = v
            except Exception:
                pass
            yield {
                "bucket": bucket,
                "key": key,
                "size": item.get("Size"),
                "e_tag": item.get("ETag"),
                "last_modified": item.get("LastModified"),
                "content_type": head.get("ContentType"),
                "metadata": head.get("Metadata", {}),
                "tags": tags,
            }


def get_s3_object_bytes(bucket: str, key: str, s3_client: Optional[boto3.client] = None) -> bytes:
    s3 = s3_client or boto3.client("s3")
    obj = s3.get_object(Bucket=bucket, Key=key)
    return obj["Body"].read()
