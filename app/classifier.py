#!/usr/bin/env python3
"""
Ticket Classifier
- Uses LLM with a strong system prompt
- Optional: vector store semantic search tool (hook provided)
- Fallback: rule-based classifier
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

# Optional: you can integrate OpenAI or other providers here
try:
    import openai  # type: ignore
except Exception:
    openai = None  # will use fallback

try:
    from app.vector_store import QdrantRetriever, QdrantConfig
except Exception:
    QdrantRetriever = None  # type: ignore
    QdrantConfig = None  # type: ignore

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "simple_classifier_prompt.txt")

CATEGORIES = {
    "refund",
    "regeneration",
    "sppam",
    "pictures-not-received-spam",
    "invoice",
    "reupload",
    "influencers",
    "team-info",
    "feedback",
    "ghost-email",
    "linkedin",
    "miscellaneous",
}

@dataclass
class ClassificationResult:
    classification: str
    confidence: int
    reasoning: str

    def to_ticket_private_comment(self) -> Dict[str, Any]:
        payload = {
            "classification": self.classification,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }
        return {
            "ticket": {
                "comment": {
                    "body": json.dumps(payload),
                    "public": False,
                }
            }
        }

class RuleBasedClassifier:
    def classify(self, text: str) -> ClassificationResult:
        t = text.lower()
        # Refund
        if any(k in t for k in ["refund", "money back", "chargeback"]):
            return ClassificationResult("refund", 90, "Refund keywords detected")
        # Pictures not received
        if any(k in t for k in ["never received", "didn't get", "didnt get", "where are my headshots", "not received photos"]):
            return ClassificationResult("pictures-not-received-spam", 85, "Delivery issue keywords detected")
        # Regeneration
        if any(k in t for k in ["make my hair", "change hair", "longer hair", "shorter hair", "modify"]):
            return ClassificationResult("regeneration", 80, "Modification request detected")
        # Invoice
        if any(k in t for k in ["invoice", "receipt", "billing"]):
            return ClassificationResult("invoice", 90, "Invoice request keywords detected")
        # Reupload
        if any(k in t for k in ["reupload", "upload again", "new photos", "different pictures"]):
            return ClassificationResult("reupload", 80, "Reupload intent detected")
        # Influencers
        if any(k in t for k in ["followers", "collaboration", "promote on", "influencer"]):
            return ClassificationResult("influencers", 80, "Influencer outreach detected")
        # Team info
        if any(k in t for k in ["team", "enterprise", "bulk"]):
            return ClassificationResult("team-info", 75, "Team/enterprise inquiry detected")
        # Feedback
        if any(k in t for k in ["feedback", "suggestion", "how did we do"]):
            return ClassificationResult("feedback", 70, "Feedback keywords detected")
        # LinkedIn
        if any(k in t for k in ["linkedin", "shared on linkedin"]):
            return ClassificationResult("linkedin", 85, "LinkedIn share detected")
        # Spam (generic)
        if any(k in t for k in ["seo", "guest post", "backlink", "website ranking"]):
            return ClassificationResult("sppam", 95, "Spam keywords detected")
        return ClassificationResult("miscellaneous", 40, "No clear category match")

class LlmClassifier:
    def __init__(self, model: str = "gpt-4o-mini") -> None:
        if openai is None:
            raise RuntimeError("openai package not available; use RuleBasedClassifier or install openai")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY env var is required for LlmClassifier")
        openai.api_key = api_key
        self.model = model
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        try:
            with open(PROMPT_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return "You are an AI SuitUp ticket classifier. Return JSON with classification, confidence, reasoning."

    def classify(self, subject: str, conversation: str) -> ClassificationResult:
        text = f"Subject: {subject}\n\n{conversation}"
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": text},
        ]
        resp = openai.chat.completions.create(model=self.model, messages=messages, temperature=0)
        content = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(content)
            classification = data.get("classification", "miscellaneous")
            confidence = int(data.get("confidence", 60))
            reasoning = data.get("reasoning", "")
        except Exception:
            # Fallback parse strategy
            classification = "miscellaneous"
            confidence = 60
            reasoning = "LLM output parsing fallback"
        if classification not in CATEGORIES:
            classification = "miscellaneous"
        return ClassificationResult(classification, confidence, reasoning)

class VectorLlmClassifier:
    def __init__(self, model: str = "gpt-4o-mini", top_k: int = 2) -> None:
        if openai is None:
            raise RuntimeError("openai package not available; install and set OPENAI_API_KEY")
        if QdrantRetriever is None or QdrantConfig is None:
            raise RuntimeError("Qdrant components not available. Ensure app.vector_store and qdrant-client are installed.")
        self.model = model
        self.system_prompt = self._load_system_prompt()
        self.retriever = QdrantRetriever(QdrantConfig.from_env())
        self.top_k = top_k

    def _load_system_prompt(self) -> str:
        try:
            with open(PROMPT_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return "You are an AI SuitUp ticket classifier. Return JSON with classification, confidence, reasoning."

    def classify(self, subject: str, conversation: str) -> ClassificationResult:
        query_text = f"Subject: {subject}\n\n{conversation}"
        docs = self.retriever.search(query_text, top_k=self.top_k)
        context = QdrantRetriever.format_context(docs)

        user_content = (
            "You have access to the following relevant knowledge snippets (semantic matches):\n\n"
            f"{context}\n\n"
            "Now classify the incoming ticket based on these snippets and the message below."
            " Prioritize refund over other intents; if uncertain, reply miscellaneous.\n\n"
            f"TICKET:\n{query_text}"
        )

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ]
        resp = openai.chat.completions.create(model=self.model, messages=messages, temperature=0)
        content = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(content)
            classification = data.get("classification", "miscellaneous")
            confidence = int(data.get("confidence", 60))
            reasoning = data.get("reasoning", "")
        except Exception:
            classification = "miscellaneous"
            confidence = 60
            reasoning = "LLM output parsing fallback"
        if classification not in CATEGORIES:
            classification = "miscellaneous"
        return ClassificationResult(classification, confidence, reasoning) 