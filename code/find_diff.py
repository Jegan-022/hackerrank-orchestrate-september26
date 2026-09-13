#!/usr/bin/env python3
import csv

events = list(csv.DictReader(open('dataset/financial_events.csv', encoding='utf-8')))

targets = {
    'user_08': 452.00,
    'user_14': 1134.00,
    'user_15': 487.00,
    'user_18': 624.00,
    'user_22': 157.00,
    'user_06': 539.10,
    'user_21': 568.00,
    'user_24': 20625.00,
}

for uid, target in targets.items():
    print(f"\n=== {uid} (Target diff: {target}) ===")
    user_ev = [e for e in events if e['user_id'] == uid]
    for e in user_ev:
        try:
            amt = float(e['amount']) if e['amount'].strip() else None
        except:
            amt = None
        if amt is not None and (abs(amt - target) < 0.01 or target % amt == 0 or abs(amt - target) < target):
            print(f"  Event {e['event_id']}: date={e['event_date']} type={e['event_type']} dir={e['direction']} status={e['status']} amt={amt} desc={e['description']}")
