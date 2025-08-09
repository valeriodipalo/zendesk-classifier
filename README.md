# AI SuitUp Zendesk Classifier (Python)

This repository contains:
- A production classifier for Zendesk tickets (rule-based, LLM, or Vector+LLM with Qdrant)
- A serverless webhook for Vercel to auto-classify new tickets 24/7
- Analysis scripts to explore tickets and prepare datasets

## Repository structure

- `app/`
  - `zendesk.py` — Zendesk API client
  - `classifier.py` — Rule-based, LLM, and Vector LLM classifiers
  - `main.py` — CLI entrypoint for manual classification
  - `vector_store.py` — Qdrant retriever using OpenAI embeddings
- `api/`
  - `zendesk_webhook.py` — Vercel serverless endpoint to classify tickets on webhook
- `scripts/`
  - `data_analysis.py` — analysis; reads from `data/`; writes to `outputs/`
  - `create_refined_taxonomy.py` — builds refined taxonomy from real examples; outputs saved to `outputs/`
- `data/`
  - Raw inputs (e.g., `taxonomy.csv`, `zendesk_tickets_*.json`) and Generated analysis artifacts and CSVs
- `prompts/` (optional)
  - `simple_classifier_prompt.txt` — LLM production prompt
- `docs/` (optional)
  - Documentation and integrations

## Setup

1) Python 3.10+
2) Install dependencies:
```bash
python3 -m pip install -r requirements.txt
```
3) Environment variables (repo root `.env` preferred; `app/.env` also supported and loaded automatically):
```bash
# Zendesk
ZENDESK_SUBDOMAIN=...
ZENDESK_EMAIL=...
ZENDESK_API_TOKEN=...

# OpenAI
OPENAI_API_KEY=...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small   # optional

# Qdrant (for vector mode)
QDRANT_URL=https://<your-qdrant-endpoint>       # Cloud endpoint
QDRANT_API_KEY=...                               # if required
QDRANT_COLLECTION=ticket_taxonomy                # or your collection name

# Webhook (Vercel)
WEBHOOK_SHARED_SECRET=<random-string>
```

## Manual classification (CLI)

- Rule-based:
```bash
python3 -m app.main <TICKET_ID>
```
- LLM:
```bash
python3 -m app.main <TICKET_ID> --llm
```
- Vector + LLM (recommended):
```bash
python3 -m app.main <TICKET_ID> --vector
```

## Deploy auto-classification (Vercel)

- Import the repo in Vercel (or use `vercel` CLI)
- Set env vars in Vercel project settings (same as above)
- Endpoint will be available at:
```
https://<your-app>.vercel.app/api/zendesk_webhook
```
- Create Zendesk Webhook:
  - POST JSON to the endpoint
  - Header: `Authorization: Bearer <WEBHOOK_SHARED_SECRET>`
- Create Zendesk Trigger (Ticket is Created):
  - Action: Notify active webhook
  - JSON payload:
```json
{ "ticket_id": "{{ticket.id}}" }
```

## Analysis workflows

- Place raw files in `data/`:
  - `taxonomy.csv`
  - `zendesk_tickets_*.json`
- Run analyses:
```bash
python3 scripts/data_analysis.py
python3 scripts/create_refined_taxonomy.py
```
- Outputs appear in `outputs/`:
  - `zendesk_analysis_overview.png`
  - `single_tag_tickets_for_finetuning.csv`
  - `excluded_multi_tag_tickets.csv`
  - `refined_taxonomy_with_examples.csv`
  - `refined_taxonomy_compact.csv`

## Notes
- Do not commit real secrets. Use `.env` locally and Vercel envs in production.
- Vector mode requires both OpenAI and Qdrant configured, and a populated collection.
- The serverless webhook includes an idempotency guard to avoid duplicate notes. 