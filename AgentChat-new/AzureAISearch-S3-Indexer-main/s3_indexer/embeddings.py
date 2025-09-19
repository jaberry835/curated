from __future__ import annotations
from typing import List, Optional
import os
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

# Using official OpenAI Python SDK v1 with Azure OpenAI
from openai import AzureOpenAI


class EmbeddingClient:
    def __init__(self, endpoint: str, deployment: str, api_key: Optional[str] = None):
        if not endpoint:
            raise ValueError("Azure OpenAI endpoint is required")
        self.deployment = deployment
        # The SDK uses api_key or AAD via DefaultAzureCredential is not supported directly in SDK v1
        # For simplicity here we expect API key; AAD flows would use REST or azure-ai-inference libs.
        if not api_key:
            api_key = os.getenv("AZURE_OPENAI_API_KEY")
        if not api_key:
            raise ValueError("AZURE_OPENAI_API_KEY is required for embeddings in this sample")
        self.client = AzureOpenAI(
            api_key=api_key,
            api_version="2024-05-01-preview",
            azure_endpoint=endpoint,
        )

    @retry(wait=wait_exponential(multiplier=1, max=10), stop=stop_after_attempt(5))
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        resp = self.client.embeddings.create(
            input=texts,
            model=self.deployment,
        )
        # Results arrive in order
        return [d.embedding for d in resp.data]
