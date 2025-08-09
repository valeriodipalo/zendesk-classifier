#!/usr/bin/env python3
import argparse
import json
import os
from typing import List
from pathlib import Path

from dotenv import load_dotenv
from app.zendesk import ZendeskClient, ZendeskConfig
from app.classifier import RuleBasedClassifier, LlmClassifier, VectorLlmClassifier


def build_cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Classify Zendesk tickets and write classification as private note")
    p.add_argument("ticket_id", type=int, help="Zendesk ticket id to classify")
    p.add_argument("--llm", action="store_true", help="Use LLM classifier instead of rule-based")
    p.add_argument("--vector", action="store_true", help="Use LLM + Qdrant vector context")
    p.add_argument("--debug", action="store_true", help="Enable verbose debug logging")
    p.add_argument("--support-staff-ids", type=str, default="25419196369051", help="Comma-separated support staff user IDs")
    return p


def main() -> None:
    parser = build_cli()
    args = parser.parse_args()

    # Load env from project root and app/.env if present
    root_env = Path(__file__).resolve().parents[1] / ".env"
    app_env = Path(__file__).resolve().parent / ".env"
    for env_path in [root_env, app_env]:
        if env_path.exists():
            load_dotenv(env_path)

    if args.debug:
        os.environ["DEBUG_CLASSIFIER"] = "1"

    config = ZendeskConfig.from_env()
    client = ZendeskClient(config)

    support_staff_ids: List[int] = []
    if args.support_staff_ids:
        support_staff_ids = [int(x) for x in args.support_staff_ids.split(",") if x.strip()]

    data = client.build_conversation(args.ticket_id, support_staff_ids=support_staff_ids)
    subject = data.get("subject", "")
    conversation_items = data.get("conversation", [])
    conversation_text = "\n\n---\n\n".join([f"{item['role']}:\n{item['message']}" for item in conversation_items])

    if os.getenv("DEBUG_CLASSIFIER") == "1":
        print("\n=== MAIN DEBUG ===")
        print("Subject:", subject)
        print("Conversation items:", len(conversation_items))
        print("Conversation text length:", len(conversation_text))

    if args.vector:
        classifier = VectorLlmClassifier()
        result = classifier.classify(subject, conversation_text)
    elif args.llm:
        classifier = LlmClassifier()
        result = classifier.classify(subject, conversation_text)
    else:
        classifier = RuleBasedClassifier()
        result = classifier.classify(f"{subject}\n\n{conversation_text}")

    print(json.dumps({
        "ticket_id": args.ticket_id,
        "classification": result.classification,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
    }, indent=2))

    # Write back as private note
    payload = json.dumps({
        "classification": result.classification,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
    })
    client.add_private_comment(args.ticket_id, payload)
    print("Private note added to the ticket.")


if __name__ == "__main__":
    main() 