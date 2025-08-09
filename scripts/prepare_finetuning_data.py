#!/usr/bin/env python3
"""
Prepare Fine-Tuning Data from Zendesk Conversations
This script formats conversation data for different fine-tuning platforms
"""

import pandas as pd
import json
from typing import List, Dict, Any

def create_openai_format(conversations_df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Create OpenAI fine-tuning format (messages format)
    """
    fine_tuning_data = []
    
    for _, row in conversations_df.iterrows():
        entry = {
            "messages": [
                {
                    "role": "system",
                    "content": f"You are a helpful AI SuitUp customer support agent. You specialize in {row['category_description'] if pd.notna(row['category_description']) else row['category']} inquiries."
                },
                {
                    "role": "user", 
                    "content": row['customer_message']
                },
                {
                    "role": "assistant",
                    "content": row['agent_response']
                }
            ],
            "category": row['category']
        }
        fine_tuning_data.append(entry)
    
    return fine_tuning_data

def create_huggingface_format(conversations_df: pd.DataFrame) -> List[Dict[str, str]]:
    """
    Create Hugging Face format (instruction-response pairs)
    """
    fine_tuning_data = []
    
    for _, row in conversations_df.iterrows():
        entry = {
            "instruction": f"As an AI SuitUp customer support agent, respond to this {row['category']} inquiry:",
            "input": row['customer_message'],
            "output": row['agent_response'],
            "category": row['category']
        }
        fine_tuning_data.append(entry)
    
    return fine_tuning_data

def create_classification_format(conversations_df: pd.DataFrame) -> List[Dict[str, str]]:
    """
    Create format for classification fine-tuning (message -> category)
    """
    fine_tuning_data = []
    
    for _, row in conversations_df.iterrows():
        entry = {
            "text": row['customer_message'],
            "label": row['category'],
            "label_description": row['category_description'] if pd.notna(row['category_description']) else ""
        }
        fine_tuning_data.append(entry)
    
    return fine_tuning_data

def analyze_data_balance(conversations_df: pd.DataFrame):
    """
    Analyze data distribution and suggest balancing strategies
    """
    print("=== DATA BALANCE ANALYSIS ===")
    
    category_counts = conversations_df['category'].value_counts()
    total_samples = len(conversations_df)
    
    print(f"Total samples: {total_samples}")
    print(f"Number of categories: {len(category_counts)}")
    print(f"Average samples per category: {total_samples / len(category_counts):.1f}")
    
    print("\nCategory distribution:")
    for category, count in category_counts.items():
        percentage = (count / total_samples) * 100
        print(f"  {category}: {count} samples ({percentage:.1f}%)")
    
    # Identify imbalanced categories
    median_count = category_counts.median()
    low_representation = category_counts[category_counts < median_count * 0.5]
    high_representation = category_counts[category_counts > median_count * 2]
    
    if len(low_representation) > 0:
        print(f"\n⚠️  Low representation categories (< {median_count * 0.5:.0f} samples):")
        for category, count in low_representation.items():
            print(f"  {category}: {count} samples")
    
    if len(high_representation) > 0:
        print(f"\n📊 High representation categories (> {median_count * 2:.0f} samples):")
        for category, count in high_representation.items():
            print(f"  {category}: {count} samples")
    
    return category_counts

def suggest_data_augmentation(conversations_df: pd.DataFrame, min_samples: int = 20):
    """
    Suggest data augmentation strategies for low-representation categories
    """
    category_counts = conversations_df['category'].value_counts()
    low_categories = category_counts[category_counts < min_samples]
    
    if len(low_categories) == 0:
        print(f"✅ All categories have >= {min_samples} samples")
        return
    
    print(f"\n=== DATA AUGMENTATION SUGGESTIONS ===")
    print(f"Categories needing augmentation (< {min_samples} samples):")
    
    augmentation_strategies = []
    
    for category, count in low_categories.items():
        needed = min_samples - count
        print(f"\n{category}: {count} samples (need {needed} more)")
        
        # Get sample messages for this category
        category_data = conversations_df[conversations_df['category'] == category]
        
        strategies = []
        if count >= 3:
            strategies.append("Paraphrasing existing messages")
            strategies.append("Varying customer tone/formality")
        if count >= 2:
            strategies.append("Creating similar scenarios")
        strategies.append("Manual creation based on category description")
        
        print(f"  Suggested strategies: {', '.join(strategies)}")
        
        # Show example for context
        if len(category_data) > 0:
            example = category_data.iloc[0]
            print(f"  Example message: {example['customer_message'][:100]}...")

def split_train_validation(data: List[Dict], train_ratio: float = 0.8, by_category: bool = True):
    """
    Split data into training and validation sets
    """
    if not by_category:
        # Simple random split
        split_idx = int(len(data) * train_ratio)
        return data[:split_idx], data[split_idx:]
    
    # Stratified split by category
    df = pd.DataFrame(data)
    train_data = []
    val_data = []
    
    for category in df['category'].unique():
        category_data = df[df['category'] == category].to_dict('records')
        split_idx = max(1, int(len(category_data) * train_ratio))  # Ensure at least 1 in each set
        
        train_data.extend(category_data[:split_idx])
        val_data.extend(category_data[split_idx:])
    
    return train_data, val_data

def main():
    # Load conversation data
    try:
        conversations_df = pd.read_csv('ticket_conversations_for_finetuning.csv')
    except FileNotFoundError:
        print("❌ Error: ticket_conversations_for_finetuning.csv not found")
        print("Please run extract_conversations.py first to generate conversation data")
        return
    
    print(f"Loaded {len(conversations_df)} conversation pairs")
    
    # Analyze data balance
    category_counts = analyze_data_balance(conversations_df)
    
    # Suggest augmentation
    suggest_data_augmentation(conversations_df)
    
    # Create different formats
    print(f"\n=== CREATING FINE-TUNING FORMATS ===")
    
    # 1. OpenAI format
    openai_data = create_openai_format(conversations_df)
    train_openai, val_openai = split_train_validation(openai_data)
    
    with open('openai_train.jsonl', 'w') as f:
        for entry in train_openai:
            f.write(json.dumps(entry) + '\n')
    
    with open('openai_validation.jsonl', 'w') as f:
        for entry in val_openai:
            f.write(json.dumps(entry) + '\n')
    
    print(f"✅ OpenAI format: {len(train_openai)} train, {len(val_openai)} validation")
    
    # 2. Hugging Face format
    hf_data = create_huggingface_format(conversations_df)
    train_hf, val_hf = split_train_validation(hf_data)
    
    with open('huggingface_train.json', 'w') as f:
        json.dump(train_hf, f, indent=2)
    
    with open('huggingface_validation.json', 'w') as f:
        json.dump(val_hf, f, indent=2)
    
    print(f"✅ Hugging Face format: {len(train_hf)} train, {len(val_hf)} validation")
    
    # 3. Classification format
    classification_data = create_classification_format(conversations_df)
    train_clf, val_clf = split_train_validation(classification_data)
    
    with open('classification_train.json', 'w') as f:
        json.dump(train_clf, f, indent=2)
    
    with open('classification_validation.json', 'w') as f:
        json.dump(val_clf, f, indent=2)
    
    print(f"✅ Classification format: {len(train_clf)} train, {len(val_clf)} validation")
    
    print(f"\n=== FILES CREATED ===")
    print("OpenAI format (GPT fine-tuning):")
    print("  - openai_train.jsonl")
    print("  - openai_validation.jsonl")
    print("\nHugging Face format (instruction-following):")
    print("  - huggingface_train.json")
    print("  - huggingface_validation.json")
    print("\nClassification format (category prediction):")
    print("  - classification_train.json")
    print("  - classification_validation.json")
    
    print(f"\n=== NEXT STEPS ===")
    print("1. Review data quality and balance")
    print("2. Consider data augmentation for low-representation categories")
    print("3. Choose your fine-tuning platform:")
    print("   - OpenAI: Use openai_train.jsonl for GPT fine-tuning")
    print("   - Hugging Face: Use huggingface_*.json for transformer models")
    print("   - Classification: Use classification_*.json for category prediction")

if __name__ == "__main__":
    main() 