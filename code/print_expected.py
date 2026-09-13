#!/usr/bin/env python3
"""Show all sample expected answers to understand the algorithm."""
import csv, sys
sys.path.insert(0, 'code')

with open('dataset/sample_requests.csv') as f:
    samples = list(csv.DictReader(f))

for s in samples:
    rid = s['request_id']
    safe = s['amount_safe_to_pay']
    status = s['affordability_status']
    method = s['recommended_payment_method']
    plan = s['payment_plan'][:60] if s['payment_plan'] else ''
    changes = s['spending_changes_needed']
    earliest = s['earliest_date_for_full_payment']
    print(f"{rid}: safe={safe}, status={status}, method={method}")
    if plan and plan != 'none':
        print(f"       plan={plan}")
    if changes and changes != 'none':
        print(f"       changes={changes}")
    if earliest:
        print(f"       earliest={earliest}")
