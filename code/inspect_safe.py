#!/usr/bin/env python3
import csv
from decimal import Decimal

profiles = {r['user_id']: r for r in csv.DictReader(open('dataset/financial_profiles.csv', encoding='utf-8'))}
samples = list(csv.DictReader(open('dataset/sample_requests.csv', encoding='utf-8')))

for s in samples:
    p = profiles[s['user_id']]
    bal = Decimal(p['current_available_balance'])
    min_b = Decimal(p['minimum_balance_to_keep'])
    safe = Decimal(s['amount_safe_to_pay'])
    req_amt = Decimal(s['requested_amount'])
    margin = bal - min_b
    diff = safe - margin
    print(f"{s['request_id']} ({s['user_id']}): bal={bal} min={min_b} margin={margin} safe={safe} req={req_amt} diff={diff}")
