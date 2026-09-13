#!/usr/bin/env python3
import csv

events = list(csv.DictReader(open('dataset/financial_events.csv', encoding='utf-8')))

user_ev = [e for e in events if e['user_id'] == 'user_22']
user_ev.sort(key=lambda x: x['event_date'])
for e in user_ev:
    print(f"  {e['event_date']}: amt={e['amount']} cat={e['category']} type={e['event_type']} dir={e['direction']} status={e['status']} desc={e['description']}")
