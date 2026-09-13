#!/usr/bin/env python3
import csv
from collections import defaultdict

events = list(csv.DictReader(open('dataset/financial_events.csv', encoding='utf-8')))

targets = {
    'user_08': 452.00,
    'user_14': 1134.00,
    'user_15': 487.00,
    'user_18': 624.00,
    'user_22': 157.00,
    'user_21': 568.00,
    'user_06': 539.10,
}

for uid, target in targets.items():
    print(f"\n==================== {uid} (Target = {target}) ====================")
    user_ev = [e for e in events if e['user_id'] == uid]
    # Group by category
    by_cat = defaultdict(list)
    for e in user_ev:
        by_cat[e['category']].append(e)
    
    # Check monthly amounts per category (e.g. from last month)
    print("Distinct categories and their common/recurring amounts:")
    for cat, evts in sorted(by_cat.items()):
        amts = [e['amount'].strip() for e in evts if e['amount'].strip() and e['direction'] == 'debit']
        from collections import Counter
        common = Counter(amts).most_common(3)
        print(f"  {cat}: count={len(evts)} most_common={common}")
