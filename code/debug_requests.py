#!/usr/bin/env python3
"""Deep debug single request."""
import sys
sys.path.insert(0, 'code')
from data_loader import load_events, load_profiles, load_exchange_rates
from currency import CurrencyConverter
from decimal import Decimal
from datetime import date

events_all, events_by_user, events_by_id = load_events()
profiles = load_profiles()
rates = load_exchange_rates()
converter = CurrencyConverter(rates)

# request_01: user_01, date=2024-03-03, requested=25256 ZAR
# expected_safe=25256 (affordable_now, full_payment)
user_id = 'user_01'
req_date = date(2024, 3, 3)
profile = profiles[user_id]
user_events = events_by_user.get(user_id, [])

from event_resolver import resolve_events, get_cash_flow_events
from forecasting import build_forecast_events, compute_safe_amount

resolved = resolve_events(events_by_id, user_events)
cash_flow = get_cash_flow_events(resolved)

print(f'Balance: {profile.current_available_balance}, min: {profile.minimum_balance_to_keep}')
print(f'Cash flow events: {len(cash_flow)}')

forecast = build_forecast_events(profile, cash_flow, req_date, converter)
print(f'Forecast events (90d): {len(forecast)}')

total_out = sum(-d for _,d,_,_ in forecast if d < 0)
total_in = sum(d for _,d,_,_ in forecast if d > 0)
print(f'Total outflow: {total_out:.2f}, inflow: {total_in:.2f}')
print(f'Net: {total_in - total_out:.2f}')
balance_no_payment = profile.current_available_balance + total_in - total_out
print(f'Balance after 90d (no payment): {balance_no_payment:.2f}')
print(f'Available for payment (worst case): {balance_no_payment - profile.minimum_balance_to_keep:.2f}')

print('\nForecast events:')
for d, delta, cat, eid in forecast:
    print(f'  {d} {delta:.2f} {cat} {eid}')

safe = compute_safe_amount(profile.current_available_balance, profile.minimum_balance_to_keep, Decimal('25256'), req_date, forecast)
print(f'\namount_safe_to_pay: {safe}')

# Also check request_03: user_03, date=2019-09-03, requested=5491000 IDR
# expected_safe=873000, expected earliest=2019-11-15
print('\n\n=== request_03 ===')
user_id3 = 'user_03'
req_date3 = date(2019, 9, 3)
profile3 = profiles[user_id3]
user_events3 = events_by_user.get(user_id3, [])
resolved3 = resolve_events(events_by_id, user_events3)
cash_flow3 = get_cash_flow_events(resolved3)
forecast3 = build_forecast_events(profile3, cash_flow3, req_date3, converter)
print(f'Balance: {profile3.current_available_balance}, min: {profile3.minimum_balance_to_keep}')
print(f'Forecast events: {len(forecast3)}')
total_out3 = sum(-d for _,d,_,_ in forecast3 if d < 0)
total_in3 = sum(d for _,d,_,_ in forecast3 if d > 0)
print(f'Total outflow: {total_out3:.2f}, inflow: {total_in3:.2f}')
print(f'Balance after 90d (no payment): {profile3.current_available_balance + total_in3 - total_out3:.2f}')
print(f'Expected safe: 873000 (with income coming in)')
print('\nForecast events:')
for d, delta, cat, eid in forecast3[:20]:
    print(f'  {d} {delta:.2f} {cat} {eid}')
safe3 = compute_safe_amount(profile3.current_available_balance, profile3.minimum_balance_to_keep, Decimal('5491000'), req_date3, forecast3)
print(f'amount_safe_to_pay: {safe3}')
