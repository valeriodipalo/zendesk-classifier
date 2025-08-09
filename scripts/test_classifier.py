#!/usr/bin/env python3
"""
Test AI Ticket Classifier with Real Examples
This script tests classification accuracy using examples from the refined taxonomy
"""

import pandas as pd
import json
import re

def load_test_cases():
    """Load real examples from refined taxonomy for testing"""
    df = pd.read_csv('refined_taxonomy_compact.csv')
    
    test_cases = []
    
    for _, row in df.iterrows():
        category = row['category']
        examples_text = row['all_examples']
        
        if pd.isna(examples_text):
            continue
            
        # Parse examples
        examples = examples_text.split(' || ')
        
        for example in examples[:3]:  # Take first 3 examples per category
            # Extract subject and message
            if 'Subject:' in example and 'Message:' in example:
                parts = example.split(' | Message: ')
                if len(parts) >= 2:
                    subject = parts[0].replace('1. Subject: ', '').replace('2. Subject: ', '').replace('3. Subject: ', '')
                    message = parts[1][:200]  # Truncate long messages
                    
                    test_cases.append({
                        'expected_category': category,
                        'subject': subject,
                        'message': message,
                        'full_text': f"Subject: {subject}\nMessage: {message}"
                    })
    
    return test_cases

def simulate_classification(text):
    """
    Simulate AI classification (replace this with actual AI model call)
    This is a simple rule-based classifier for demonstration
    """
    text_lower = text.lower()
    
    # Simple keyword-based classification for testing
    if any(word in text_lower for word in ['refund', 'money back', 'chargeback']):
        return {'classification': 'refund', 'confidence': 90, 'reasoning': 'Refund keywords detected'}
    
    elif any(word in text_lower for word in ['hair shorter', 'hair longer', 'change hair', 'make adjustments']):
        return {'classification': 'regeneration', 'confidence': 85, 'reasoning': 'Regeneration request detected'}
    
    elif any(word in text_lower for word in ['never received', 'didn\'t get', 'where are my']):
        return {'classification': 'pictures-not-received-spam', 'confidence': 88, 'reasoning': 'Photos not received'}
    
    elif any(word in text_lower for word in ['receipt', 'invoice', 'billing']):
        return {'classification': 'invoice', 'confidence': 92, 'reasoning': 'Invoice request detected'}
    
    elif any(word in text_lower for word in ['seo', 'guest post', 'website ranking']):
        return {'classification': 'sppam', 'confidence': 95, 'reasoning': 'Spam content detected'}
    
    elif any(word in text_lower for word in ['followers', 'collaboration', 'promote']):
        return {'classification': 'influencers', 'confidence': 80, 'reasoning': 'Influencer collaboration'}
    
    elif any(word in text_lower for word in ['new photos', 'different pictures', 'reupload']):
        return {'classification': 'reupload', 'confidence': 85, 'reasoning': 'Photo reupload request'}
    
    elif any(word in text_lower for word in ['linkedin', 'shared on linkedin']):
        return {'classification': 'linkedin', 'confidence': 90, 'reasoning': 'LinkedIn sharing request'}
    
    elif any(word in text_lower for word in ['team', 'enterprise', 'bulk']):
        return {'classification': 'team-info', 'confidence': 80, 'reasoning': 'Team/enterprise inquiry'}
    
    elif any(word in text_lower for word in ['feedback', 'suggestion', 'how did we do']):
        return {'classification': 'feedback', 'confidence': 75, 'reasoning': 'Customer feedback'}
    
    else:
        return {'classification': 'miscellaneous', 'confidence': 40, 'reasoning': 'No clear category match'}

def evaluate_classifier():
    """Test and evaluate classifier performance"""
    test_cases = load_test_cases()
    print(f"Loaded {len(test_cases)} test cases")
    
    results = {
        'total': 0,
        'correct': 0,
        'high_confidence_correct': 0,
        'high_confidence_total': 0,
        'category_performance': {}
    }
    
    detailed_results = []
    
    for case in test_cases:
        classification_result = simulate_classification(case['full_text'])
        
        expected = case['expected_category']
        predicted = classification_result['classification']
        confidence = classification_result['confidence']
        
        is_correct = (expected == predicted)
        is_high_confidence = (confidence >= 80)
        
        results['total'] += 1
        if is_correct:
            results['correct'] += 1
        
        if is_high_confidence:
            results['high_confidence_total'] += 1
            if is_correct:
                results['high_confidence_correct'] += 1
        
        # Track per-category performance
        if expected not in results['category_performance']:
            results['category_performance'][expected] = {'total': 0, 'correct': 0}
        
        results['category_performance'][expected]['total'] += 1
        if is_correct:
            results['category_performance'][expected]['correct'] += 1
        
        detailed_results.append({
            'expected': expected,
            'predicted': predicted,
            'confidence': confidence,
            'correct': is_correct,
            'subject': case['subject'][:50] + '...' if len(case['subject']) > 50 else case['subject'],
            'reasoning': classification_result['reasoning']
        })
    
    return results, detailed_results

def print_evaluation_results(results, detailed_results):
    """Print comprehensive evaluation results"""
    print("\n" + "="*80)
    print("AI TICKET CLASSIFIER EVALUATION RESULTS")
    print("="*80)
    
    # Overall Performance
    overall_accuracy = (results['correct'] / results['total']) * 100
    print(f"\n📊 OVERALL PERFORMANCE:")
    print(f"   Total Test Cases: {results['total']}")
    print(f"   Correct Classifications: {results['correct']}")
    print(f"   Overall Accuracy: {overall_accuracy:.1f}%")
    
    # High Confidence Performance
    if results['high_confidence_total'] > 0:
        hc_accuracy = (results['high_confidence_correct'] / results['high_confidence_total']) * 100
        print(f"\n🎯 HIGH CONFIDENCE PERFORMANCE (≥80%):")
        print(f"   High Confidence Cases: {results['high_confidence_total']}")
        print(f"   High Confidence Correct: {results['high_confidence_correct']}")
        print(f"   High Confidence Accuracy: {hc_accuracy:.1f}%")
    
    # Per-Category Performance
    print(f"\n📋 CATEGORY PERFORMANCE:")
    for category, perf in results['category_performance'].items():
        accuracy = (perf['correct'] / perf['total']) * 100 if perf['total'] > 0 else 0
        print(f"   {category:25} | {perf['correct']:2d}/{perf['total']:2d} | {accuracy:5.1f}%")
    
    # Sample Results
    print(f"\n🔍 SAMPLE CLASSIFICATIONS:")
    for i, result in enumerate(detailed_results[:10]):  # Show first 10
        status = "✅" if result['correct'] else "❌"
        print(f"   {status} {result['subject']}")
        print(f"      Expected: {result['expected']} | Predicted: {result['predicted']} ({result['confidence']}%)")
        print(f"      Reasoning: {result['reasoning']}")
        print()
    
    # Improvement Suggestions
    print(f"\n💡 IMPROVEMENT SUGGESTIONS:")
    
    # Find categories with low performance
    low_performance = []
    for category, perf in results['category_performance'].items():
        accuracy = (perf['correct'] / perf['total']) * 100 if perf['total'] > 0 else 0
        if accuracy < 70:
            low_performance.append((category, accuracy, perf['total']))
    
    if low_performance:
        print("   Categories needing improvement:")
        for category, accuracy, total in low_performance:
            print(f"   - {category}: {accuracy:.1f}% accuracy ({total} cases)")
        print("   → Consider adding more specific keywords or refining definitions")
    else:
        print("   ✅ All categories performing well!")
    
    print(f"\n📈 RECOMMENDATIONS:")
    print("   1. Add more semantic similarity checks for edge cases")
    print("   2. Implement confidence calibration for better uncertainty handling")
    print("   3. Use vector embeddings for better semantic understanding")
    print("   4. Add conversation context for multi-turn tickets")

def main():
    """Run classifier evaluation"""
    print("🚀 Testing AI Ticket Classifier...")
    print("Loading test cases from refined taxonomy...")
    
    try:
        results, detailed_results = evaluate_classifier()
        print_evaluation_results(results, detailed_results)
        
        # Save detailed results
        with open('classifier_test_results.json', 'w') as f:
            json.dump({
                'summary': results,
                'detailed_results': detailed_results
            }, f, indent=2)
        
        print(f"\n💾 Detailed results saved to: classifier_test_results.json")
        
    except Exception as e:
        print(f"❌ Error during evaluation: {e}")
        print("Make sure refined_taxonomy_compact.csv exists in the current directory")

if __name__ == "__main__":
    main() 