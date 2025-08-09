#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler
import json
import os
import traceback
from pathlib import Path
from datetime import datetime, timezone, timedelta
import csv

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
    """Load category->response text mapping from CSV.
    Order of precedence (first that exists wins):
      1) RESPONSE_MAP_PATH env
      2) DATA/Ticket_map.csv   (user-provided mapping)
      3) data/Ticket_map.csv
      4) ricket_map.csv (legacy name) under data/ or root
      5) data/response_templates.csv (fallback conventional name)
    CSV may be headered (category,response_text) or headerless.
    Delimiter is auto-detected among [; , \t |].
    """
    candidates = []
    env_path = os.getenv("RESPONSE_MAP_PATH")
    if env_path:
        candidates.append(Path(env_path))
    base = ROOT
    candidates += [
        base / "DATA" / "Ticket_map.csv",
        base / "data" / "Ticket_map.csv",
        base / "data" / "ricket_map.csv",
        base / "ricket_map.csv",
        base / "data" / "response_templates.csv",
    ]

    def detect_delimiter(sample: str) -> str:
        for d in [";", ",", "\t", "|"]:
            if d in sample:
                return d
        return ","

    for p in candidates:
        try:
            if not p.exists():
                continue
            mapping = {}
            with p.open("r", encoding="utf-8-sig", newline="") as f:
                head = f.read(2048)
                f.seek(0)
                delim = detect_delimiter(head)
                # Try with DictReader first
                reader = csv.DictReader(f, delimiter=delim)
                fieldnames = [fn.strip().lower() for fn in (reader.fieldnames or [])]
                if "category" in fieldnames and ("response_text" in fieldnames or "response" in fieldnames):
                    resp_key = "response_text" if "response_text" in fieldnames else "response"
                    for row in reader:
                        cat = (row.get("category") or "").strip().lower()
                        txt = (row.get(resp_key) or "").strip()
                        if cat and txt:
                            mapping[cat] = txt
                else:
                    # Headerless: use csv.reader and take first two columns
                    f.seek(0)
                    r2 = csv.reader(f, delimiter=delim)
                    for row in r2:
                        if not row or len(row) < 2:
                            continue
                        cat = (row[0] or "").strip().lower()
                        txt = (row[1] or "").strip()
                        if cat and txt and cat != "category":
                            mapping[cat] = txt
            if DEBUG:
                print(f"Loaded response map from: {p} (entries={len(mapping)}) delimiter='{delim}'")
            return mapping
        except Exception as e:
            if DEBUG:
                print(f"Failed loading mapping from {p}: {e}")
    if DEBUG:
        print("No response mapping found; will skip answer comment")
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

            # Load mapping and post the mapped internal answer (private) if available
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