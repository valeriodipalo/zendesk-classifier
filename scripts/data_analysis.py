# %% [markdown]
# # Zendesk Tickets Analysis for Fine-Tuning
# 
# This notebook analyzes Zendesk tickets according to the provided taxonomy and prepares data for fine-tuning.

import pandas as pd
import json
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from collections import Counter
from datetime import datetime
import warnings
from pathlib import Path
warnings.filterwarnings('ignore')

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / 'data'
OUTPUTS = BASE / 'outputs'
OUTPUTS.mkdir(parents=True, exist_ok=True)

plt.style.use('default')
sns.set_palette("husl")

print("Loading data...")

# Load taxonomy
taxonomy_path = DATA / 'taxonomy.csv'
taxonomy_df = pd.read_csv(taxonomy_path)
print(f"Taxonomy loaded: {len(taxonomy_df)} categories")

# Load tickets
tickets_path = next(DATA.glob('zendesk_tickets_*.json'))
with open(tickets_path, 'r') as f:
    tickets_data = json.load(f)

tickets_df = pd.DataFrame(tickets_data)
print(f"Tickets loaded: {len(tickets_df)} tickets")

print("=== BASIC DATA INFO ===")
print(f"Ticket columns: {list(tickets_df.columns)}")
print(f"Taxonomy columns: {list(taxonomy_df.columns)}")
print(f"Date range: {tickets_df['created_at'].min()} to {tickets_df['created_at'].max()}")

print("=== TAXONOMY ANALYSIS ===")

def extract_tag_name(title):
    if pd.isna(title):
        return None
    if str(title).startswith('https://'):
        if 'tags%3A' in title:
            tag = title.split('tags%3A')[1].split('&')[0].split('%')[0]
            return tag
        return None
    return str(title).split(',')[0].strip()

taxonomy_df['tag_name'] = taxonomy_df['Title'].apply(extract_tag_name)
taxonomy_df_clean = taxonomy_df[taxonomy_df['tag_name'].notna()].copy()

print(f"Extracted {len(taxonomy_df_clean)} valid tags from taxonomy")
print("Sample tags:", taxonomy_df_clean['tag_name'].head(10).tolist())

taxonomy_lookup = dict(zip(taxonomy_df_clean['tag_name'], taxonomy_df_clean['Description']))

print("=== TICKET TAGS ANALYSIS ===")

tickets_df['num_tags'] = tickets_df['tags'].apply(lambda x: len(x) if isinstance(x, list) else 0)

tag_count_dist = tickets_df['num_tags'].value_counts().sort_index()
print("Distribution of tickets by number of tags:")
for num_tags, count in tag_count_dist.items():
    print(f"  {num_tags} tags: {count} tickets ({count/len(tickets_df)*100:.1f}%)")

all_tags = []
for tags in tickets_df['tags']:
    if isinstance(tags, list):
        all_tags.extend(tags)

tag_frequency = Counter(all_tags)
print(f"\nTotal unique tags found: {len(tag_frequency)}")
print(f"Total tag occurrences: {len(all_tags)}")

print("\nTop 20 most frequent tags:")
for tag, count in tag_frequency.most_common(20):
    description = taxonomy_lookup.get(tag, "Not in taxonomy")
    if pd.isna(description):
        description = "Not in taxonomy"
    else:
        description = str(description)
    print(f"  {tag}: {count} ({description[:60]}{'...' if len(description) > 60 else ''})")

print("=== TAXONOMY COVERAGE ===")

taxonomy_tags = set(taxonomy_df_clean['tag_name'])
ticket_tags = set(all_tags)

unused_taxonomy_tags = taxonomy_tags - ticket_tags
print(f"Tags in taxonomy but not found in tickets: {len(unused_taxonomy_tags)}")
if unused_taxonomy_tags:
    print("  ", list(unused_taxonomy_tags)[:10])

unknown_tags = ticket_tags - taxonomy_tags
print(f"Tags in tickets but not in taxonomy: {len(unknown_tags)}")
if unknown_tags:
    print("  ", list(unknown_tags)[:10])

covered_tags = taxonomy_tags & ticket_tags
print(f"Tags covered by taxonomy: {len(covered_tags)} out of {len(ticket_tags)} total tags")

print("=== FILTERING BY TAXONOMY ===")

def ticket_matches_taxonomy(tags):
    if not isinstance(tags, list):
        return False
    return any(tag in taxonomy_tags for tag in tags)

def get_taxonomy_tags(tags):
    if not isinstance(tags, list):
        return []
    return [tag for tag in tags if tag in taxonomy_tags]

# Filter tickets
tickets_df['matches_taxonomy'] = tickets_df['tags'].apply(ticket_matches_taxonomy)
tickets_df['taxonomy_tags'] = tickets_df['tags'].apply(get_taxonomy_tags)
tickets_df['num_taxonomy_tags'] = tickets_df['taxonomy_tags'].apply(len)

taxonomy_tickets = tickets_df[tickets_df['matches_taxonomy']].copy()

print(f"Tickets matching taxonomy: {len(taxonomy_tickets)} out of {len(tickets_df)} ({len(taxonomy_tickets)/len(tickets_df)*100:.1f}%)")

print("=== MULTI-TAG ANALYSIS ===")

single_tag_tickets = taxonomy_tickets[taxonomy_tickets['num_taxonomy_tags'] == 1].copy()
multi_tag_tickets = taxonomy_tickets[taxonomy_tickets['num_taxonomy_tags'] > 1].copy()

print(f"Single taxonomy tag tickets: {len(single_tag_tickets)} ({len(single_tag_tickets)/len(taxonomy_tickets)*100:.1f}%)")
print(f"Multi taxonomy tag tickets: {len(multi_tag_tickets)} ({len(multi_tag_tickets)/len(taxonomy_tickets)*100:.1f}%)")

if len(multi_tag_tickets) > 0:
    print(f"\nMulti-tag distribution:")
    multi_dist = multi_tag_tickets['num_taxonomy_tags'].value_counts().sort_index()
    for num_tags, count in multi_dist.items():
        print(f"  {num_tags} tags: {count} tickets")
    
    print(f"\nSample multi-tag combinations:")
    for i, row in multi_tag_tickets.head(5).iterrows():
        print(f"  Ticket {row['id']}: {row['taxonomy_tags']}")

print("=== CREATING VISUALIZATIONS ===")

fig, axes = plt.subplots(2, 2, figsize=(15, 12))

top_tags = dict(tag_frequency.most_common(15))
taxonomy_status = ['In Taxonomy' if tag in taxonomy_tags else 'Not in Taxonomy' for tag in top_tags.keys()]

ax1 = axes[0, 0]
bars = ax1.bar(range(len(top_tags)), list(top_tags.values()))
ax1.set_xticks(range(len(top_tags)))
ax1.set_xticklabels(list(top_tags.keys()), rotation=45, ha='right')
ax1.set_ylabel('Frequency')
ax1.set_title('Top 15 Tags by Frequency')

for i, (bar, status) in enumerate(zip(bars, taxonomy_status)):
    bar.set_color('green' if status == 'In Taxonomy' else 'red')

ax2 = axes[0, 1]
tag_count_dist.plot(kind='bar', ax=ax2, color='skyblue')
ax2.set_xlabel('Number of Tags')
ax2.set_ylabel('Number of Tickets')
ax2.set_title('Distribution of Tags per Ticket')
ax2.tick_params(axis='x', rotation=0)

ax3 = axes[1, 0]
coverage_data = [len(covered_tags), len(unknown_tags), len(unused_taxonomy_tags)]
coverage_labels = ['Covered Tags', 'Unknown Tags', 'Unused Taxonomy']
ax3.pie(coverage_data, labels=coverage_labels, autopct='%1.1f%%', startangle=90)
ax3.set_title('Tag Coverage Analysis')

ax4 = axes[1, 1]
single_multi_data = [len(single_tag_tickets), len(multi_tag_tickets)]
single_multi_labels = ['Single Tag', 'Multi Tag']
ax4.pie(single_multi_data, labels=single_multi_labels, autopct='%1.1f%%', startangle=90)
ax4.set_title('Single vs Multi-Tag Tickets\n(Taxonomy Tags Only)')

plt.tight_layout()
plt.savefig(OUTPUTS / 'zendesk_analysis_overview.png', dpi=300, bbox_inches='tight')

print("=== CREATING SINGLE-TAG DATASET ===")

clean_dataset = single_tag_tickets.copy()
clean_dataset['primary_tag'] = clean_dataset['taxonomy_tags'].apply(lambda x: x[0] if x else None)
clean_dataset['tag_description'] = clean_dataset['primary_tag'].map(taxonomy_lookup)

single_tag_dist = clean_dataset['primary_tag'].value_counts()
print(f"Single-tag dataset: {len(clean_dataset)} tickets")
print(f"Categories represented: {len(single_tag_dist)}")

fine_tuning_data = []
for _, row in clean_dataset.iterrows():
    fine_tuning_data.append({
        'ticket_id': row['id'],
        'subject': row.get('subject', ''),
        'tag': row['primary_tag'],
        'tag_description': row['tag_description'],
        'created_at': row['created_at'],
        'all_tags': row['tags']
    })

fine_tuning_df = pd.DataFrame(fine_tuning_data)
fine_tuning_df.to_csv(OUTPUTS / 'single_tag_tickets_for_finetuning.csv', index=False)
print(f"Saved single-tag dataset: {len(fine_tuning_df)} tickets")

print("=== MULTI-TAG EXCLUSION ANALYSIS ===")

excluded_tickets = multi_tag_tickets.copy()
print(f"Tickets to exclude (multi-tag): {len(excluded_tickets)}")
print(f"Percentage of taxonomy tickets excluded: {len(excluded_tickets)/len(taxonomy_tickets)*100:.1f}%")

excluded_tag_combinations = excluded_tickets['taxonomy_tags'].apply(tuple).value_counts()
print("\nTop 10 multi-tag combinations being excluded:")
for combo, count in excluded_tag_combinations.head(10).items():
    print(f"  {list(combo)}: {count} tickets")

excluded_tickets.to_csv(OUTPUTS / 'excluded_multi_tag_tickets.csv', index=False)
print("\nSaved excluded multi-tag tickets for review")

print("=== FINAL SUMMARY ===")
print(f"Total tickets analyzed: {len(tickets_df)}")
print(f"Tickets matching taxonomy: {len(taxonomy_tickets)} ({len(taxonomy_tickets)/len(tickets_df)*100:.1f}%)")
print(f"Single-tag tickets for fine-tuning: {len(single_tag_tickets)} ({len(single_tag_tickets)/len(tickets_df)*100:.1f}%)")
print(f"Multi-tag tickets excluded: {len(multi_tag_tickets)} ({len(multi_tag_tickets)/len(taxonomy_tickets)*100:.1f}%)")

print(f"\nCategories in final dataset: {len(single_tag_dist)}")
print(f"Average tickets per category: {len(single_tag_tickets)/len(single_tag_dist):.1f}")

print("\n=== ANALYSIS COMPLETE ===")
print("Files created in outputs/:")
print("- zendesk_analysis_overview.png")
print("- single_tag_tickets_for_finetuning.csv")
print("- excluded_multi_tag_tickets.csv") 