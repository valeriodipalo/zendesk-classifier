#!/usr/bin/env python3
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

try:
    from qdrant_client import QdrantClient
except Exception:
    QdrantClient = None  # type: ignore

try:
    import openai  # type: ignore
except Exception:
    openai = None  # type: ignore

DEFAULT_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

@dataclass
class QdrantConfig:
    url: str
    api_key: Optional[str]
    collection: str

    @classmethod
    def from_env(cls) -> "QdrantConfig":
        url = os.getenv("QDRANT_URL", "").strip()
        api_key = os.getenv("QDRANT_API_KEY", "").strip() or None
        collection = os.getenv("QDRANT_COLLECTION", "ticket_taxonomy").strip()
        if not url:
            raise RuntimeError("QDRANT_URL env var is required for QdrantRetriever")
        return cls(url=url, api_key=api_key, collection=collection)

class QdrantRetriever:
    def __init__(self, config: QdrantConfig, embedding_model: str = DEFAULT_EMBEDDING_MODEL) -> None:
        if QdrantClient is None:
            raise RuntimeError("qdrant-client not installed. Add it to requirements.txt and pip install.")
        if openai is None:
            raise RuntimeError("openai package not available for embeddings. Install and set OPENAI_API_KEY.")
        self.client = QdrantClient(url=config.url, api_key=config.api_key)
        self.collection = config.collection
        self.embedding_model = embedding_model

    def embed(self, text: str) -> List[float]:
        resp = openai.embeddings.create(model=self.embedding_model, input=text)
        return resp.data[0].embedding  # type: ignore

    def search(self, text: str, top_k: int = 2) -> List[Dict[str, Any]]:
        vector = self.embed(text)
        results = self.client.search(
            collection_name=self.collection,
            query_vector=vector,
            limit=top_k,
            with_payload=True,
        )
        docs: List[Dict[str, Any]] = []
        for r in results:
            payload = r.payload or {}
            content = payload.get("content") or payload.get("text") or ""
            tag = payload.get("tag") or payload.get("category")
            docs.append({
                "content": content,
                "tag": tag,
                "score": r.score,
            })
        return docs

    @staticmethod
    def format_context(docs: List[Dict[str, Any]]) -> str:
        lines: List[str] = []
        for i, d in enumerate(docs, 1):
            prefix = f"[{i}]"
            tag = f" (tag: {d['tag']})" if d.get("tag") else ""
            lines.append(f"{prefix}{tag} {d['content']}")
        return "\n".join(lines) 