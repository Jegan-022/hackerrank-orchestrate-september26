#!/usr/bin/env python3
"""Check income events for specific users."""
import csv

for uid in ['user_03', 'user_05', 'user_08', 'user_13']:
    with open('dataset/financial_events.csv') as f:
        events = [r for r in csv.DictReader(f) if r['user_id'] == uid and r['direction'] == 'credit']
    events.sort(key=lambda x: x['event_date'])
    print(f'\n{uid} income events ({len(events)} total):')
    for ev in events[-6:]:
        print(f'  {ev["event_id"]} {ev["event_date"]} {ev["status"]} amount={ev["amount"]} {ev["currency"]} {ev["category"]} {ev["event_type"]}')
