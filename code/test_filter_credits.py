#!/usr/bin/env python3
import sys
sys.path.insert(0, 'code')
import csv
from datetime import date
from collections import defaultdict

events = list(csv.DictReader(open('dataset/financial_events.csv', encoding='utf-8')))

ONE_OFF_CREDIT_KEYWORDS = (
    "bonus", "commission", "arrears", "refund", "reimbursement",
    "prize", "reversal", "proceeds", "prorated", "peak-season", "temporary"
)

for uid in [f"user_{i:02d}" for i in range(1, 26)]:
    credits = [
        e for e in events
        if e['user_id'] == uid
        and e['direction'] == 'credit'
        and not any(kw in e['description'].lower() for kw in ONE_OFF_CREDIT_KEYWORDS)
    ]
    dates = [e['event_date'] for e in credits]
    amts = [e['amount'] for e in credits if e['amount']]
    days = [date.fromisoformat(d).day for d in dates if d]
    print(f"{uid}: regular credits count={len(credits)}, days={set(days)}, amts={set(amts[:5])}")
