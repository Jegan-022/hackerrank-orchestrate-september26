#!/usr/bin/env python3
import csv

requests = {r['user_id']: r for r in csv.DictReader(open('dataset/sample_requests.csv', encoding='utf-8'))}
events = list(csv.DictReader(open('dataset/financial_events.csv', encoding='utf-8')))
profiles = {r['user_id']: r for r in csv.DictReader(open('dataset/financial_profiles.csv', encoding='utf-8'))}

for uid in ['user_08', 'user_14', 'user_15', 'user_18', 'user_22', 'user_06', 'user_21']:
    req = requests[uid]
    req_date = req['request_date']
    safe = req['amount_safe_to_pay']
    bal = profiles[uid]['current_available_balance']
    min_b = profiles[uid]['minimum_balance_to_keep']
    print(f"\n=== {uid}: req_date={req_date}, bal={bal}, min={min_b}, safe={safe} ===")
    user_ev = [e for e in events if e['user_id'] == uid]
    for e in user_ev:
        if e['status'] in ('pending', 'scheduled') or e['event_date'] >= req_date:
            print(f"  {e['event_id']}: date={e['event_date']} type={e['event_type']} dir={e['direction']} status={e['status']} amt={e['amount']} cat={e['category']} desc={e['description']}")
