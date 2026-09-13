#!/usr/bin/env python3
import csv

events = list(csv.DictReader(open('dataset/financial_events.csv', encoding='utf-8')))
for uid in ['user_08', 'user_14', 'user_15', 'user_18', 'user_06']:
    user_ev = [e for e in events if e['user_id'] == uid]
    dates = [e['event_date'] for e in user_ev]
    statuses = set(e['status'] for e in user_ev)
    print(f"{uid}: count={len(user_ev)}, min_date={min(dates)}, max_date={max(dates)}, statuses={statuses}")
