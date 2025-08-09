#!/usr/bin/env python3
"""
Extract Conversation Content from Zendesk Tickets
This script fetches the actual comments/messages from tickets to prepare fine-tuning data
"""

import requests
import json
import pandas as pd
from datetime import datetime
import time
import os
from pathlib import Path
from dotenv import load_dotenv

class ZendeskConversationExtractor:
    def __init__(self, subdomain: str, email: str, api_token: str):
        self.subdomain = subdomain
        self.base_url = f"https://{subdomain}.zendesk.com/api/v2"
        self.session = requests.Session()
        self.session.auth = (f"{email}/token", api_token)
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def get_ticket_comments(self, ticket_id: int):
        """Get all comments for a specific ticket"""
        url = f"{self.base_url}/tickets/{ticket_id}/comments.json"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()
            return data.get('comments', [])
        except requests.exceptions.RequestException as e:
            print(f"Error fetching comments for ticket {ticket_id}: {e}")
            return []
    
    def extract_conversation_pair(self, comments):
        """Extract first customer message and first agent response"""
        if not comments or len(comments) < 2:
            return None, None
        
        # Sort comments by created_at
        comments = sorted(comments, key=lambda x: x['created_at'])
        
        customer_message = None
        agent_response = None
        
        for comment in comments:
            # Skip empty or system messages
            if not comment.get('body') or comment.get('body', '').strip() == '':
                continue
                
            # First non-empty message is usually from customer
            if customer_message is None:
                customer_message = comment['body']
                continue
            
            # First response from different author is agent response
            if agent_response is None and comment.get('author_id') != comments[0].get('author_id'):
                agent_response = comment['body']
                break
        
        return customer_message, agent_response
    
    def clean_message_content(self, content):
        """Clean message content for fine-tuning"""
        if not content:
            return ""
        
        # Remove HTML tags
        import re
        content = re.sub('<[^<]+?>', '', content)
        
        # Remove email signatures and footers
        lines = content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            # Skip common email artifacts
            if any(skip_phrase in line.lower() for skip_phrase in [
                'sent from', 'reply above', 'on behalf of', 'forwarded message',
                'original message', 'from:', 'to:', 'subject:', 'date:'
            ]):
                break
            if line:
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines).strip()

def main():
    # Load the clean ticket dataset
    df = pd.read_csv('single_tag_tickets_for_finetuning.csv')
    print(f"Loaded {len(df)} tickets for conversation extraction")
    
    # Load env from repo root (and scripts/.env as fallback)
    BASE = Path(__file__).resolve().parents[1]
    load_dotenv(BASE / ".env")
    load_dotenv(Path(__file__).resolve().parent / ".env")

    # Zendesk credentials from env
    SUBDOMAIN = os.getenv("ZENDESK_SUBDOMAIN", "").strip()
    EMAIL = os.getenv("ZENDESK_EMAIL", "").strip()
    API_TOKEN = os.getenv("ZENDESK_API_TOKEN", "").strip()

    if not SUBDOMAIN or not EMAIL or not API_TOKEN:
        raise SystemExit("Missing ZENDESK_SUBDOMAIN, ZENDESK_EMAIL or ZENDESK_API_TOKEN in environment")

    extractor = ZendeskConversationExtractor(SUBDOMAIN, EMAIL, API_TOKEN)
    
    # Extract conversations
    conversations = []
    
    for idx, row in df.iterrows():
        ticket_id = row['ticket_id']
        tag = row['tag']
        tag_description = row['tag_description']
        
        print(f"Processing ticket {ticket_id} ({idx+1}/{len(df)})...")
        
        # Get comments
        comments = extractor.get_ticket_comments(ticket_id)
        
        if not comments:
            print(f"  No comments found for ticket {ticket_id}")
            continue
        
        # Extract conversation pair
        customer_msg, agent_msg = extractor.extract_conversation_pair(comments)
        
        if not customer_msg or not agent_msg:
            print(f"  No valid conversation pair found for ticket {ticket_id}")
            continue
        
        # Clean messages
        customer_msg = extractor.clean_message_content(customer_msg)
        agent_msg = extractor.clean_message_content(agent_msg)
        
        if len(customer_msg) < 10 or len(agent_msg) < 10:
            print(f"  Messages too short for ticket {ticket_id}")
            continue
        
        conversations.append({
            'ticket_id': ticket_id,
            'category': tag,
            'category_description': tag_description,
            'customer_message': customer_msg,
            'agent_response': agent_msg,
            'message_length': len(customer_msg),
            'response_length': len(agent_msg)
        })
        
        print(f"  ✓ Extracted conversation pair")
        
        # Be polite to the API
        time.sleep(0.1)
    
    # Save conversations
    conversations_df = pd.DataFrame(conversations)
    conversations_df.to_csv('ticket_conversations_for_finetuning.csv', index=False)
    
    print(f"\n=== EXTRACTION COMPLETE ===")
    print(f"Successfully extracted {len(conversations)} conversation pairs")
    print(f"Average customer message length: {conversations_df['message_length'].mean():.0f} chars")
    print(f"Average agent response length: {conversations_df['response_length'].mean():.0f} chars")
    
    # Show distribution by category
    print(f"\nConversations by category:")
    category_dist = conversations_df['category'].value_counts()
    for category, count in category_dist.items():
        print(f"  {category}: {count} conversations")
    
    print(f"\nSaved to: ticket_conversations_for_finetuning.csv")

if __name__ == "__main__":
    main() 