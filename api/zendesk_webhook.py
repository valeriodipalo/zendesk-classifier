#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler
import json
import os
import traceback
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Ensure local imports work in serverless env
ROOT = Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.zendesk import ZendeskClient, ZendeskConfig
from app.classifier import RuleBasedClassifier, LlmClassifier, VectorLlmClassifier

WEBHOOK_SHARED_SECRET = os.getenv("WEBHOOK_SHARED_SECRET", "")
DEBUG = os.getenv("DEBUG_CLASSIFIER") == "1"


def choose_classifier() -> object:
    if os.getenv("QDRANT_URL") and os.getenv("OPENAI_API_KEY"):
        try:
            return VectorLlmClassifier()
        except Exception:
            pass
    if os.getenv("OPENAI_API_KEY"):
        try:
            return LlmClassifier()
        except Exception:
            pass
    return RuleBasedClassifier()


def has_internal_comments(client: ZendeskClient, ticket_id: int) -> bool:
    """Return True if the ticket already contains ANY private (internal) comment."""
    try:
        comments = client.get_ticket_comments(ticket_id, public_only=False)
    except Exception:
        return False
    for c in comments:
        if c.get("public") is False:
            return True
    return False


def load_response_mapping() -> dict:
    """Load category -> response_text mapping from JSON only.
    Priority (first existing wins):
      1) RESPONSE_MAP_JSON (absolute path)
      2) data/response_templates.json
      3) DATA/response_templates.json
    JSON formats accepted:
      - Object { "refund": "text...", "regeneration": "text..." }
      - Array of objects [ {"category":"refund","response_text":"text..."}, ... ]
    Keys normalized to lowercase.
    """
    candidates = []
    env_json = os.getenv("RESPONSE_MAP_JSON")
    if env_json:
        candidates.append(Path(env_json))
    candidates += [
        ROOT / "data" / "response_templates.json",
        ROOT / "DATA" / "response_templates.json",
        ROOT / "DATA" / "Ticket_map_key_value.json",
    ]

    for p in candidates:
        try:
            if not p.exists():
                continue
            with p.open("r", encoding="utf-8-sig") as f:
                data = json.load(f)
            mapping = {}
            if isinstance(data, dict):
                for k, v in data.items():
                    k2 = (k or "").strip().lower()
                    v2 = (v or "").strip()
                    if k2 and v2:
                        mapping[k2] = v2
            elif isinstance(data, list):
                for row in data:
                    if not isinstance(row, dict):
                        continue
                    k2 = (row.get("category") or "").strip().lower()
                    v2 = (row.get("response_text") or row.get("response") or "").strip()
                    if k2 and v2:
                        mapping[k2] = v2
            if DEBUG:
                print(f"Loaded JSON response map from: {p} (entries={len(mapping)})")
            if mapping:
                return mapping
        except Exception as e:
            if DEBUG:
                print(f"Failed loading JSON mapping from {p}: {e}")
    if DEBUG:
        print("No JSON response mapping found; will skip answer comment")
    return {}


class handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode("utf-8"))

    def do_POST(self):
        # Basic bearer verification
        auth = self.headers.get("Authorization", "")
        if WEBHOOK_SHARED_SECRET:
            if not auth.startswith("Bearer ") or auth.split(" ", 1)[1].strip() != WEBHOOK_SHARED_SECRET:
                return self._send(401, {"ok": False, "error": "unauthorized"})

        # Read body
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except Exception:
            length = 0
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = {}

        ticket_id = payload.get("ticket_id") or payload.get("ticket", {}).get("id")
        if not ticket_id:
            return self._send(400, {"ok": False, "error": "missing ticket_id"})

        try:
            config = ZendeskConfig.from_env()
            client = ZendeskClient(config)

            # Only act if there are NO internal comments on the ticket
            if has_internal_comments(client, int(ticket_id)):
                return self._send(200, {"ok": True, "skipped": True, "reason": "has internal comments"})

            # Build conversation and classify
            convo = client.build_conversation(int(ticket_id))
            subject = convo.get("subject", "")
            conversation_items = convo.get("conversation", [])
            conversation_text = "\n\n---\n\n".join([f"{it['role']}:\n{it['message']}" for it in conversation_items])

            classifier = choose_classifier()
            if hasattr(classifier, "classify") and classifier.__class__.__name__ != "RuleBasedClassifier":
                result = classifier.classify(subject, conversation_text)
            else:
                result = classifier.classify(f"{subject}\n\n{conversation_text}")

            # Post classification as private note
            class_body = json.dumps({
                "classification": result.classification,
                "confidence": result.confidence,
                "reasoning": result.reasoning,
            })
            client.add_private_comment(int(ticket_id), class_body)

            # Post mapped internal answer as a second private note (if available)
            mapping = load_response_mapping()
            answer = mapping.get((result.classification or "").lower())
            if not answer and (result.classification or "").lower() != "miscellaneous":
                # Edge-case fallback
                answer = mapping.get("miscellaneous", "human intervention required")
            if answer:
                # Add prefix to make it clear this is the response template
                template_note = f"Response Template:\n\n{answer}"
                client.add_private_comment(int(ticket_id), template_note)

            return self._send(200, {
                "ok": True,
                "ticket_id": ticket_id,
                "classification": result.classification,
                "answer_posted": bool(answer),
            })
        except Exception as e:
            traceback.print_exc()
            return self._send(200, {"ok": False, "error": str(e)}) 