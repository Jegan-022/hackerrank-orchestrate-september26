#!/usr/bin/env python3
import csv

events = list(csv.DictReader(open('dataset/financial_events.csv', encoding='utf-8')))

for uid in ['user_08', 'user_15', 'user_22', 'user_06']:
    user_ev = [e for e in events if e['user_id'] == uid and e['event_date'] >= '2024-12-01']
    user_ev.sort(key=lambda x: x['event_date'])
    print(f"\n=== {uid} (recent events) ===")
    for e in user_ev[-15:]:
        print(f"  {e['event_date']}: amt={e['amount']} cat={e['category']} type={e['event_type']} dir={e['direction']} status={e['status']} desc={e['description']}")
