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
    # Prefer vector LLM if Qdrant configured; else plain LLM; else rule-based
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


def recent_classification_exists(client: ZendeskClient, ticket_id: int, window_minutes: int = 10) -> bool:
    try:
        data = client.get_ticket_comments(ticket_id, public_only=False)
    except Exception:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    for c in reversed(data):
        if c.get("public") is True:
            continue
        body = (c.get("body") or c.get("plain_body") or "").strip()
        if not body:
            continue
        if '"classification"' in body:
            # Idempotency: if very recent, skip
            created_at = c.get("created_at")
            try:
                if created_at:
                    created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    if created_dt >= cutoff:
                        return True
            except Exception:
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

        # Run classification
        try:
            config = ZendeskConfig.from_env()
            client = ZendeskClient(config)

            # Idempotency for classification note
            if recent_classification_exists(client, int(ticket_id)):
                return self._send(200, {"ok": True, "skipped": True, "reason": "recent classification exists"})

            # Build conversation
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

            # Load JSON mapping and post the mapped internal answer (private) if available
            mapping = load_response_mapping()
            answer = mapping.get((result.classification or "").lower())
            if answer:
                client.add_private_comment(int(ticket_id), answer)
                if DEBUG:
                    print(f"Posted mapped internal answer for category '{result.classification}'")

            return self._send(200, {
                "ok": True,
                "ticket_id": ticket_id,
                "classification": result.classification,
                "answer_posted": bool(answer),
            })
        except Exception as e:
            traceback.print_exc()
            # Return 200 to avoid repeated Zendesk retries; include error in body
            return self._send(200, {"ok": False, "error": str(e)}) 