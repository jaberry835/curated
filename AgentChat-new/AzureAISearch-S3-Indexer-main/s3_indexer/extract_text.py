from __future__ import annotations
from typing import Optional
import io


def sniff_type_from_key(key: str) -> str:
    lower = key.lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".txt"):
        return "text/plain"
    return "application/octet-stream"


def extract_text(content: bytes, content_type: Optional[str], key: str) -> str:
    ct = (content_type or sniff_type_from_key(key)).lower()
    if ct.startswith("application/pdf"):
        return _extract_pdf(content)
    if ct.startswith("text/"):
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode("latin-1", errors="ignore")
    # Fallback: treat as bytes
    return ""


def _extract_pdf(content: bytes) -> str:
    try:
        # Lazy import to avoid IDE errors before dependencies are installed
        from pypdf import PdfReader  # type: ignore
    except Exception:
        # Dependency not installed or other issue; return empty
        return ""
    with io.BytesIO(content) as f:
        reader = PdfReader(f)
        texts = []
        for page in reader.pages:
            t = page.extract_text() or ""
            texts.append(t)
        return "\n\n".join(texts)
