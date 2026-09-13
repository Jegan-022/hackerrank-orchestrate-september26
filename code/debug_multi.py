#!/usr/bin/env python3
"""Compare expected vs actual for multiple failing requests."""
import sys, csv
sys.path.insert(0, 'code')
from data_loader import load_events, load_profiles, load_exchange_rates, load_images, load_messages, load_requests
from currency import CurrencyConverter
from financial_state import FinancialState
from forecasting import build_forecast_events, compute_safe_amount, find_earliest_full_payment_date
from decimal import Decimal
from datetime import date

events_all, events_by_user, events_by_id = load_events()
profiles = load_profiles()
rates = load_exchange_rates()
converter = CurrencyConverter(rates)
_, images_by_event, _ = load_images()
_, messages_by_user, _, _ = load_messages()
requests = load_requests('dataset/sample_requests.csv')
requests_by_id = {r.request_id: r for r in requests}

# Requests to debug
TARGET_REQUESTS = ['request_03', 'request_05', 'request_10', 'request_08']

with open('dataset/sample_requests.csv') as f:
    expected = {r['request_id']: r for r in csv.DictReader(f)}

for rid in TARGET_REQUESTS:
    req = requests_by_id[rid]
    exp = expected[rid]
    uid = req.user_id
    profile = profiles[uid]
    
    print(f'\n{"="*60}')
    print(f'{rid}: user={uid} date={req.request_date} requested={req.requested_amount}')
    print(f'  Balance: {profile.current_available_balance}, min: {profile.minimum_balance_to_keep}, currency: {profile.home_currency}')
    print(f'  Expected: safe={exp["amount_safe_to_pay"]}, status={exp["affordability_status"]}, method={exp["recommended_payment_method"]}')
    print(f'  Expected payment_plan: {exp.get("payment_plan","")}')
    
    user_events = events_by_user.get(uid, [])
    user_messages = messages_by_user.get(uid, [])
    
    state = FinancialState(
        profile=profile, events=user_events, events_by_id=events_by_id,
        messages=user_messages, images_by_event=images_by_event, converter=converter
    )
    
    from event_resolver import get_cash_flow_events
    print(f'  Cash flow events: {len(state.cash_flow_events)}')
    
    # Show scheduled/pending events
    future_events = [ev for ev in state.cash_flow_events 
                     if ev.status in ('scheduled','pending')]
    print(f'  Scheduled/pending events: {len(future_events)}')
    for ev in future_events:
        print(f'    {ev.event_id}: {ev.event_date} {ev.status} {ev.direction} {ev.category} {ev.amount_in_home_currency}')
    
    # Income history
    income_evs = [ev for ev in state.cash_flow_events if ev.direction == 'credit' and ev.status == 'settled']
    print(f'  Settled income events: {len(income_evs)}')
    for ev in sorted(income_evs, key=lambda x: x.event_date)[-3:]:
        print(f'    {ev.event_id}: {ev.event_date} {ev.category} {ev.amount} {ev.currency}')
    
    forecast = build_forecast_events(profile, state.cash_flow_events, req.request_date, converter)
    credits_fc = [(d, delta, cat) for d, delta, cat, eid in forecast if delta > 0]
    debits_fc = [(d, delta, cat) for d, delta, cat, eid in forecast if delta < 0]
    print(f'  Forecast: {len(debits_fc)} debits, {len(credits_fc)} credits')
    if credits_fc:
        print(f'  Credits in forecast:')
        for c in credits_fc[:5]:
            print(f'    {c}')
    
    total_out = sum(-d for _,d,_,_ in forecast if d < 0)
    total_in = sum(d for _,d,_,_ in forecast if d > 0)
    print(f'  Total out: {total_out:.2f}, in: {total_in:.2f}')
    print(f'  End balance (no payment): {profile.current_available_balance + total_in - total_out:.2f}')
    
    safe = compute_safe_amount(profile.current_available_balance, profile.minimum_balance_to_keep, 
                               req.requested_amount, req.request_date, forecast)
    earliest = find_earliest_full_payment_date(
        profile.current_available_balance, profile.minimum_balance_to_keep,
        req.requested_amount, req.request_date, forecast)
    print(f'  Got: safe={safe}, earliest={earliest}')
