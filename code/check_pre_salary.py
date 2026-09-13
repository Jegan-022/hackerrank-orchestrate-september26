#!/usr/bin/env python3
import sys
sys.path.insert(0, 'code')
from data_loader import load_events, load_profiles, load_exchange_rates, load_requests, load_messages, load_images
from currency import CurrencyConverter
from financial_state import build_financial_states
from forecasting import build_forecast_events
from datetime import date
from decimal import Decimal

profiles = load_profiles()
events_all, events_by_user, events_by_id = load_events()
rates = load_exchange_rates()
converter = CurrencyConverter(rates)
messages_all, messages_by_user, _, _ = load_messages()
_, images_by_event, _ = load_images()
states = build_financial_states(profiles, events_by_user, events_by_id, messages_by_user, images_by_event, converter)

requests = {r.user_id: r for r in load_requests('dataset/sample_requests.csv')}

targets = {
    'user_08': (date(2025, 2, 7), date(2025, 2, 15), Decimal('452.00')),
    'user_14': (date(2025, 8, 4), date(2025, 8, 15), Decimal('1134.00')),
    'user_15': (date(2026, 1, 6), date(2026, 1, 15), Decimal('487.00')),
    'user_18': (date(2026, 7, 7), date(2026, 7, 15), Decimal('624.00')),
    'user_06': (date(2026, 1, 3), date(2026, 1, 15), Decimal('539.10')),
    'user_21': (date(2026, 4, 3), date(2026, 4, 15), Decimal('568.00')),
    'user_22': (date(2024, 12, 5), date(2024, 12, 15), Decimal('157.00')),
    'user_24': (date(2026, 2, 8), date(2026, 2, 15), Decimal('20625.00')),
}

for uid, (req_d, sal_d, target_exp) in targets.items():
    state = states[uid]
    fc_events = build_forecast_events(state.profile, state.cash_flow_events, req_d, converter)
    
    # Filter debits between req_d and sal_d (delta < 0)
    pre_sal_debits = [e for e in fc_events if e[1] < 0 and req_d <= e[0] < sal_d]
    total_debits = -sum(e[1] for e in pre_sal_debits)
    print(f"\n{uid}: req={req_d} sal={sal_d} | target={target_exp} | our_forecast_debits={total_debits} (diff={total_debits - target_exp})")
    for d, amt, cat, eid in pre_sal_debits:
        print(f"   {d}: {-amt} ({cat}, {eid})")
