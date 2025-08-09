#!/usr/bin/env python3
import pandas as pd
import json
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / 'data'
OUTPUTS = BASE / 'outputs'
OUTPUTS.mkdir(parents=True, exist_ok=True)

from typing import List, Dict


def load_current_taxonomy() -> Dict[str, str]:
    taxonomy_df = pd.read_csv(DATA / 'taxonomy.csv')
    taxonomy_lookup = {}
    for _, row in taxonomy_df.iterrows():
        title = row['Title']
        if pd.isna(title):
            continue
        if str(title).startswith('https://'):
            if 'tags%3A' in title:
                tag = title.split('tags%3A')[1].split('&')[0].split('%')[0]
            else:
                continue
        else:
            tag = str(title).split(',')[0].strip()
        description = row['Description'] if pd.notna(row['Description']) else ""
        taxonomy_lookup[tag] = description
    return taxonomy_lookup


def load_ticket_data():
    clean_path = OUTPUTS / 'single_tag_tickets_for_finetuning.csv'
    if clean_path.exists():
        clean_tickets = pd.read_csv(clean_path)
    else:
        # Fallback to legacy filename in root
        legacy = BASE / 'single_tag_tickets_for_finetuning.csv'
        clean_tickets = pd.read_csv(legacy)

    original_path = next(DATA.glob('zendesk_tickets_*.json'))
    with open(original_path, 'r') as f:
        original_tickets = json.load(f)
    original_lookup = {t['id']: t for t in original_tickets}
    return clean_tickets, original_lookup


def clean_message_content(content: str) -> str:
    if not content:
        return ""
    content = str(content)
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    cleaned_lines = []
    total_chars = 0
    for line in lines:
        if total_chars + len(line) > 200 and cleaned_lines:
            break
        cleaned_lines.append(line)
        total_chars += len(line)
        if len(cleaned_lines) >= 3:
            break
    result = ' | '.join(cleaned_lines)
    return result[:197] + '...' if len(result) > 200 else result


def get_category_examples(clean_tickets: pd.DataFrame, original_lookup: Dict[int, dict], category: str, max_examples: int = 10) -> List[Dict[str, str]]:
    category_tickets = clean_tickets[clean_tickets['tag'] == category].copy()
    category_tickets['created_at'] = pd.to_datetime(category_tickets['created_at'])
    category_tickets = category_tickets.sort_values('created_at', ascending=False)
    examples: List[Dict[str, str]] = []
    for _, ticket in category_tickets.head(max_examples).iterrows():
        ticket_id = int(ticket['ticket_id']) if 'ticket_id' in ticket else int(ticket['id'])
        original_ticket = original_lookup.get(ticket_id, {})
        subject = ticket.get('subject', 'No subject')
        description = original_ticket.get('description', '')
        cleaned_message = clean_message_content(description)
        if subject and subject != 'No subject':
            example_text = f"Subject: {subject}"
            if cleaned_message:
                example_text += f" | Message: {cleaned_message}"
        else:
            example_text = cleaned_message if cleaned_message else "No message content"
        examples.append({
            'ticket_id': ticket_id,
            'created_at': ticket['created_at'].strftime('%Y-%m-%d'),
            'example_text': example_text
        })
    return examples


def create_refined_taxonomy():
    taxonomy_lookup = load_current_taxonomy()
    clean_tickets, original_lookup = load_ticket_data()
    top_categories = [
        'refund', 'regeneration', 'sppam', 'pictures-not-received-spam', 'invoice', 'reupload', 
        'influencers', 'team-info', 'feedback', 'ghost-email', 'linkedin'
    ]
    refined = []
    for category in top_categories:
        description = taxonomy_lookup.get(category, f"Category: {category} (description needed)")
        examples = get_category_examples(clean_tickets, original_lookup, category)
        ticket_count = len(clean_tickets[clean_tickets['tag'] == category])
        entry = {
            'category': category,
            'description': description,
            'ticket_count': ticket_count,
            'examples_included': len(examples)
        }
        for i, ex in enumerate(examples, 1):
            entry[f'example_{i}_date'] = ex['created_at']
            entry[f'example_{i}_ticket_id'] = ex['ticket_id']
            entry[f'example_{i}_text'] = ex['example_text']
        refined.append(entry)
    return refined


def save_outputs(refined):
    df = pd.DataFrame(refined)
    # Detailed
    detailed = OUTPUTS / 'refined_taxonomy_with_examples.csv'
    # Compact
    compact = OUTPUTS / 'refined_taxonomy_compact.csv'

    # Detailed columns ordering
    base_cols = ['category', 'description', 'ticket_count', 'examples_included']
    example_cols = []
    for i in range(1, 11):
        example_cols += [f'example_{i}_date', f'example_{i}_ticket_id', f'example_{i}_text']
    use_cols = [c for c in base_cols + example_cols if c in df.columns]
    df[use_cols].to_csv(detailed, index=False)

    # Compact
    compact_rows = []
    for _, row in df.iterrows():
        examples = []
        for i in range(1, 11):
            txt = row.get(f'example_{i}_text', '')
            if isinstance(txt, str) and txt:
                examples.append(f"{i}. {txt}")
        compact_rows.append({
            'category': row['category'],
            'description': row['description'],
            'ticket_count': row['ticket_count'],
            'examples_count': row['examples_included'],
            'all_examples': ' || '.join(examples)
        })
    pd.DataFrame(compact_rows).to_csv(compact, index=False)
    print(f"Saved: {detailed}")
    print(f"Saved: {compact}")


def main():
    refined = create_refined_taxonomy()
    save_outputs(refined)

if __name__ == '__main__':
    main() 