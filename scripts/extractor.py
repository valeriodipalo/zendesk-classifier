#!/usr/bin/env python3
"""
Zendesk Ticket Extractor - Last 24 Hours
Simple script to extract tickets created in the last 24 hours
"""

import requests
import json
from datetime import datetime, timedelta, timezone

# === CONFIGURATION ===
subdomain = "aisuitupsupport"  # Replace with your Zendesk subdomain
email = "valerio@aisuitup.com"  # Replace with your email
api_token = "LIevAV0gMgqZXU8IVvXnDNGebE0TMpjESMITlqqs"  # Replace with your API token

# === AUTHENTICATION ===
auth = (f"{email}/token", api_token)

# === DATE CALCULATION ===
# Get tickets from the last 24 hours - using UTC to match Zendesk
now_utc = datetime.now(timezone.utc)
twenty_four_hours_ago = now_utc - timedelta(hours=24)
created_after = twenty_four_hours_ago.strftime('%Y-%m-%dT%H:%M:%SZ')

print(f"Current UTC time: {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")
print(f"Fetching tickets created after: {created_after}")
print(f"Local time equivalent: {twenty_four_hours_ago.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}")

# === ZENDESK API ENDPOINT ===
base_url = f"https://{subdomain}.zendesk.com/api/v2/tickets.json"
params = {
    'created_after': created_after,
    'sort_by': 'created_at',
    'sort_order': 'desc',
    'per_page': 100
}

# === DATA COLLECTION ===
all_tickets = []
url = base_url

while url:
    print(f"Fetching: {url}")
    
    # Make API request
    response = requests.get(url, auth=auth, params=params if url == base_url else None)
    
    if response.status_code != 200:
        print(f"Error: {response.status_code} - {response.text}")
        break
    
    data = response.json()
    tickets = data.get("tickets", [])
    all_tickets.extend(tickets)
    
    print(f"Retrieved {len(tickets)} tickets. Total so far: {len(all_tickets)}")
    
    # Check for next page
    url = data.get("next_page")
    params = None  # Clear params for subsequent requests

# === RESULTS ===
print(f"\n=== SUMMARY ===")
print(f"Total tickets found: {len(all_tickets)}")

if all_tickets:
    # === ANALYZE TIMEFRAME OF ACTUAL TICKETS ===
    if len(all_tickets) > 0:
        # Check the actual creation times of first and last tickets
        first_ticket_time = all_tickets[0].get('created_at', '')
        last_ticket_time = all_tickets[-1].get('created_at', '')
        
        print(f"\n=== ACTUAL TIMEFRAME ===")
        print(f"Newest ticket: {first_ticket_time}")
        print(f"Oldest ticket: {last_ticket_time}")
        
        if first_ticket_time and last_ticket_time:
            try:
                first_dt = datetime.fromisoformat(first_ticket_time.replace('Z', '+00:00'))
                last_dt = datetime.fromisoformat(last_ticket_time.replace('Z', '+00:00'))
                timespan = first_dt - last_dt
                print(f"Actual timespan covered: {timespan.total_seconds() / 3600:.1f} hours")
            except:
                print("Could not parse ticket timestamps")
    
    # === SAVE TO JSON ===
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f"zendesk_tickets_24h_{timestamp}.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_tickets, f, indent=2, ensure_ascii=False)
    
    print(f"Tickets saved to: {output_file}")
    
    # === DISPLAY SAMPLE TICKETS ===
    print(f"\n=== RECENT TICKETS ===")
    for i, ticket in enumerate(all_tickets[:5], 1):  # Show first 5 tickets
        created_at = ticket.get('created_at', '')
        print(f"{i}. ID: {ticket.get('id')} | Status: {ticket.get('status')}")
        print(f"   Subject: {ticket.get('subject', 'No subject')[:80]}")
        print(f"   Created: {created_at}")
        print(f"   Priority: {ticket.get('priority', 'None')}")
        print()
    
    # === STATS ===
    status_counts = {}
    for ticket in all_tickets:
        status = ticket.get('status', 'unknown')
        status_counts[status] = status_counts.get(status, 0) + 1
    
    print(f"=== TICKET STATUS BREAKDOWN ===")
    for status, count in status_counts.items():
        print(f"{status}: {count}")

else:
    print("No tickets found in the last 24 hours.")

print("\nExtraction completed!")
