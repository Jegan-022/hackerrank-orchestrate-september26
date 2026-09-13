#!/usr/bin/env python3
"""Analysis script to understand the dataset structure."""
import csv
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET = os.path.join(BASE, 'dataset')

def load_csv(name):
    with open(os.path.join(DATASET, name), encoding='utf-8') as f:
        return list(csv.DictReader(f))

samples = load_csv('sample_requests.csv')
print('=== SAMPLE ANALYSIS ===')
for s in samples:
    rid = s['request_id']
    status = s['affordability_status']
    method = s['recommended_payment_method']
    spending = s['spending_changes_needed']
    safe = s['amount_safe_to_pay']
    earliest = s['earliest_date_for_full_payment']
    print(f'  {rid}: status={status} method={method} safe={safe} earliest={earliest} spending={spending}')

events = load_csv('financial_events.csv')
images = load_csv('images.csv')

blank_amount_events = {r['event_id']: r for r in events if not r['amount'].strip()}
image_by_event = {r['related_event_id']: r for r in images}

print(f'\n=== BLANK AMOUNT EVENTS ({len(blank_amount_events)}) ===')
for eid, ev in blank_amount_events.items():
    img = image_by_event.get(eid, None)
    print(f'  {eid} (user={ev["user_id"]}, type={ev["event_type"]}, status={ev["status"]}) -> image: {img["image_id"] if img else "NO IMAGE"}')

# Check linked events
linked_events = [r for r in events if r['linked_event_id'].strip()]
print(f'\n=== LINKED EVENTS ({len(linked_events)}) ===')
for ev in linked_events[:10]:
    print(f'  {ev["event_id"]} -> {ev["linked_event_id"]} ({ev["event_type"]}, {ev["status"]})')

# Check messages
messages = load_csv('messages.csv')
print(f'\n=== MESSAGES ({len(messages)}) ===')
msg_with_event = [m for m in messages if m['related_event_id'].strip()]
msg_with_request = [m for m in messages if m['request_id'].strip()]
msg_with_user_only = [m for m in messages if not m['related_event_id'].strip() and not m['request_id'].strip()]
print(f'  Messages with related_event_id: {len(msg_with_event)}')
print(f'  Messages with request_id: {len(msg_with_request)}')
print(f'  Messages with user only: {len(msg_with_user_only)}')

# Unique statuses by event type
print('\n=== STATUS BY EVENT TYPE ===')
from collections import defaultdict
type_status = defaultdict(set)
for ev in events:
    type_status[ev['event_type']].add(ev['status'])
for t, statuses in sorted(type_status.items()):
    print(f'  {t}: {sorted(statuses)}')

# Check requests
requests = load_csv('requests.csv')
print(f'\n=== REQUESTS ===')
print(f'  Total: {len(requests)}')
req_ids = [r['request_id'] for r in requests]
print(f'  Range: {min(req_ids)} to {max(req_ids)}')

# Check payment options count per request
options = load_csv('request_payment_options.csv')
from collections import Counter
opts_per_req = Counter(o['request_id'] for o in options)
print(f'\n=== PAYMENT OPTIONS PER REQUEST ===')
print(f'  Distribution: {sorted(Counter(opts_per_req.values()).items())}')
print(f'  Methods: {sorted(set(o["payment_method"] for o in options))}')
