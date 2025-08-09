#!/usr/bin/env python3
"""
Zendesk API Client
- Fetch ticket metadata
- Fetch ticket comments (public only)
- Update ticket with private/internal comment (classification JSON)
"""

from __future__ import annotations

import os
import time
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

DEFAULT_TIMEOUT = 30

@dataclass
class ZendeskConfig:
    subdomain: str
    email: str
    api_token: str

    @classmethod
    def from_env(cls) -> "ZendeskConfig":
        subdomain = os.getenv("ZENDESK_SUBDOMAIN", "").strip()
        email = os.getenv("ZENDESK_EMAIL", "").strip()
        api_token = os.getenv("ZENDESK_API_TOKEN", "").strip()
        if not subdomain or not email or not api_token:
            raise RuntimeError("Missing ZENDESK_SUBDOMAIN, ZENDESK_EMAIL or ZENDESK_API_TOKEN env vars")
        return cls(subdomain=subdomain, email=email, api_token=api_token)

class ZendeskClient:
    def __init__(self, config: ZendeskConfig, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.config = config
        self.base_url = f"https://{config.subdomain}.zendesk.com/api/v2"
        self.session = requests.Session()
        self.session.auth = (f"{config.email}/token", config.api_token)
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ai-suitup-zendesk-client/1.0",
        })
        self.timeout = timeout

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _put(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        resp = self.session.put(url, data=json.dumps(body), timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_ticket(self, ticket_id: int) -> Dict[str, Any]:
        return self._get(f"/tickets/{ticket_id}.json")

    def get_ticket_comments(self, ticket_id: int, public_only: bool = True) -> List[Dict[str, Any]]:
        data = self._get(f"/tickets/{ticket_id}/comments.json")
        comments = data.get("comments", [])
        if public_only:
            comments = [c for c in comments if bool(c.get("public", False))]
        return comments

    def build_conversation(self, ticket_id: int, support_staff_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        ticket = self.get_ticket(ticket_id).get("ticket", {})
        comments = self.get_ticket_comments(ticket_id, public_only=True)

        description = ticket.get("description", "")
        conversation: List[Dict[str, str]] = []

        # Skip first public comment if it exactly equals description
        first_public = comments[0] if comments else None
        is_dup = False
        if first_public and isinstance(first_public.get("plain_body"), str):
            is_dup = first_public.get("plain_body").strip() == description.strip()

        for idx, c in enumerate(comments):
            if idx == 0 and is_dup:
                continue
            author_id = c.get("author_id")
            role = "Support Staff" if (support_staff_ids and author_id in support_staff_ids) else "Customer"
            text = (c.get("plain_body") or c.get("html_body") or c.get("body") or "").strip()
            if not text:
                continue
            conversation.append({"role": role, "message": text})

        subject = ticket.get("subject", "")
        return {"subject": subject, "conversation": conversation, "ticket": ticket}

    def add_private_comment(self, ticket_id: int, body_text: str) -> Dict[str, Any]:
        payload = {
            "ticket": {
                "comment": {
                    "body": body_text,
                    "public": False,
                }
            }
        }
        return self._put(f"/tickets/{ticket_id}.json", payload) 