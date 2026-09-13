#!/usr/bin/env python3
import csv
from datetime import date, timedelta
from collections import defaultdict
import statistics

events = list(csv.DictReader(open('dataset/financial_events.csv', encoding='utf-8')))

for uid in ['user_03', 'user_04', 'user_08', 'user_11', 'user_13', 'user_14']:
    user_ev = [e for e in events if e['user_id'] == uid and e['direction'] == 'credit']
    print(f"\n=== {uid} credits ===")
    
    # Subgroup by description
    by_desc = defaultdict(list)
    for e in user_ev:
        by_desc[e['description']].append(e)
    
    for desc, evts in by_desc.items():
        dates = sorted([date.fromisoformat(e['event_date']) for e in evts if e['event_date']])
        gaps = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
        amts = [e['amount'] for e in evts if e['amount']]
        print(f"  '{desc}' ({len(evts)}): dates={[str(d) for d in dates]}, gaps={gaps}, amts={amts}")
