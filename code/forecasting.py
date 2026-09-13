"""
forecasting.py — 90-day deterministic cash-flow forecast engine.

KEY PRINCIPLE: current_available_balance already reflects all historical settled events.
Only FUTURE events go into the 90-day forecast:
  - Explicitly scheduled future events
  - Pending debits (reserved)
  - Recurring projections from historical patterns
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple, Dict
from collections import defaultdict
import statistics

from models import FinancialEvent, FinancialProfile
from currency import CurrencyConverter


FORECAST_DAYS = 90



ONE_OFF_CREDIT_KEYWORDS = (
    "bonus", "commission", "arrears", "refund", "reimbursement",
    "prize", "reversal", "proceeds", "prorated", "peak-season", "temporary"
)

FIXED_CATEGORIES = {
    'salary', 'rent', 'housing', 'mortgage', 'debt_repayment', 'insurance',
    'utilities', 'streaming', 'music_subscription', 'delivery_membership',
    'cloud_storage', 'gym', 'education', 'family_support'
}


def _add_months(orig_date: date, months: int) -> date:
    """Add calendar months to date, capping at end of month."""
    import calendar
    y = orig_date.year + (orig_date.month + months - 1) // 12
    m = (orig_date.month + months - 1) % 12 + 1
    max_day = calendar.monthrange(y, m)[1]
    d = min(orig_date.day, max_day)
    return date(y, m, d)


def _detect_recurring(
    settled_events: List[FinancialEvent],
    request_date: date,
    home_currency: str,
    converter,
    horizon_end: date,
    scheduled_future: Optional[List[FinancialEvent]] = None,
) -> List[Tuple[date, Decimal, str, str, str]]:
    """
    Detect recurring patterns from historical settled events (and scheduled future events).
    Returns list of (future_date, amount, category, direction, event_type).
    Only returns dates >= request_date.
    """
    grouped = defaultdict(list)
    for ev in settled_events:
        if ev.event_date is None or ev.amount is None:
            continue
        if ev.direction == 'credit' and any(kw in (ev.description or '').lower() for kw in ONE_OFF_CREDIT_KEYWORDS):
            continue
        if ev.category in FIXED_CATEGORIES:
            desc_key = (ev.description or '').strip().lower()
            key = (ev.category, ev.direction, ev.event_type, desc_key)
        else:
            key = (ev.category, ev.direction, ev.event_type, '')
        grouped[key].append(ev)

    # Also incorporate scheduled future events into groups for detecting salary recurrence
    if scheduled_future:
        for ev in scheduled_future:
            if ev.event_date is None or ev.amount is None:
                continue
            if ev.direction == 'credit' and ev.event_type in ('income',):
                if any(kw in (ev.description or '').lower() for kw in ONE_OFF_CREDIT_KEYWORDS):
                    continue
                desc_lower = (ev.description or '').strip().lower()
                matched = False
                for (cat, direct, et, dk) in list(grouped.keys()):
                    if cat == ev.category and direct == ev.direction and et == ev.event_type:
                        grouped[(cat, direct, et, dk)].append(ev)
                        matched = True
                        break
                if not matched:
                    key = (ev.category, ev.direction, ev.event_type, desc_lower)
                    grouped[key].append(ev)

    results = []
    for (category, direction, etype, desc_key), evts in grouped.items():
        if len(evts) < 2:
            # For salary/income: if there's exactly 1 event and it's relatively recent,
            # project it monthly as a conservative estimate
            if len(evts) == 1 and direction == 'credit' and etype == 'income':
                ev = evts[0]
                if ev.amount is None:
                    continue
                use_date = ev.settlement_date or ev.event_date
                if ev.currency == home_currency:
                    amt_hc = ev.amount
                else:
                    amt_hc = converter.convert(ev.amount, ev.currency, home_currency, use_date)
                if amt_hc is None:
                    continue
                m = 1
                while True:
                    next_date = _add_months(use_date, m)
                    if next_date > horizon_end:
                        break
                    if next_date >= request_date:
                        results.append((next_date, amt_hc, category, direction, etype))
                    m += 1
            continue

        evts_sorted = sorted(evts, key=lambda e: e.event_date)
        dates = [e.event_date for e in evts_sorted]
        gaps = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]

        if not gaps:
            continue

        mean_gap = sum(gaps) / len(gaps)
        std_gap = statistics.stdev(gaps) if len(gaps) > 1 else 0.0

        # Only recognize well-defined intervals
        is_recurring = False
        interval_days = None

        if 6 <= mean_gap <= 8 and std_gap < 2.0:
            is_recurring, interval_days = True, 7
        elif 13 <= mean_gap <= 16 and std_gap < 3.0:
            is_recurring, interval_days = True, 14
        elif 27 <= mean_gap <= 33 and std_gap < 5.0:
            is_recurring, interval_days = True, 30
        elif 58 <= mean_gap <= 65 and std_gap < 7.0:
            is_recurring, interval_days = True, 60
        elif 88 <= mean_gap <= 95 and std_gap < 10.0:
            is_recurring, interval_days = True, 90
        elif len(evts) >= 3 and mean_gap > 0 and std_gap / mean_gap < 0.20:
            is_recurring, interval_days = True, round(mean_gap)

        if not is_recurring or not interval_days or interval_days <= 0:
            continue

        # Average/mode amount in home currency from recent history
        amounts_hc = []
        for ev in evts_sorted[-6:]:
            use_date = ev.settlement_date or ev.event_date
            if ev.currency == home_currency:
                amounts_hc.append(ev.amount)
            else:
                conv = converter.convert(ev.amount, ev.currency, home_currency, use_date)
                if conv is not None:
                    amounts_hc.append(conv)

        if not amounts_hc:
            continue

        if category in FIXED_CATEGORIES:
            try:
                avg_amount = statistics.mode(amounts_hc)
            except Exception:
                avg_amount = amounts_hc[-1]
        else:
            avg_amount = sum(amounts_hc) / Decimal(len(amounts_hc))

        # Project forward from last event
        last_date = evts_sorted[-1].event_date

        if 27 <= interval_days <= 33:
            m = 1
            while True:
                next_date = _add_months(last_date, m)
                if next_date > horizon_end:
                    break
                if next_date >= request_date:
                    results.append((next_date, avg_amount, category, direction, etype))
                m += 1
        elif 58 <= interval_days <= 65:
            m = 1
            while True:
                next_date = _add_months(last_date, 2 * m)
                if next_date > horizon_end:
                    break
                if next_date >= request_date:
                    results.append((next_date, avg_amount, category, direction, etype))
                m += 1
        elif 88 <= interval_days <= 95:
            m = 1
            while True:
                next_date = _add_months(last_date, 3 * m)
                if next_date > horizon_end:
                    break
                if next_date >= request_date:
                    results.append((next_date, avg_amount, category, direction, etype))
                m += 1
        else:
            next_date = last_date + timedelta(days=interval_days)
            while next_date <= horizon_end:
                if next_date >= request_date:
                    results.append((next_date, avg_amount, category, direction, etype))
                next_date += timedelta(days=interval_days)

    return results


def build_forecast_events(
    profile: FinancialProfile,
    cash_flow_events: List[FinancialEvent],
    request_date: date,
    converter: CurrencyConverter,
    spending_changes: Optional[Dict[str, Optional[Decimal]]] = None,
) -> List[Tuple[date, Decimal, str, str]]:
    """
    Build list of (date, delta_in_home_currency, category, event_id) for the 90-day window.
    Negative delta = money out, positive = money in.

    current_available_balance already includes all historical settled amounts.
    Only include: scheduled/pending events + recurring projections from history.

    spending_changes: event_id -> new_amount (None = stopped)
    """
    home_currency = profile.home_currency
    horizon_end = request_date + timedelta(days=FORECAST_DAYS)
    spending_changes = spending_changes or {}

    forecast = []

    # Separate historical (settled, past) from future events
    settled_past = [
        ev for ev in cash_flow_events
        if ev.status == "settled"
        and ev.event_date is not None
        and ev.event_date < request_date
    ]

    future_explicit = [
        ev for ev in cash_flow_events
        if ev.status in ("scheduled", "pending")
        or (ev.status == "settled" and ev.event_date is not None and ev.event_date >= request_date)
    ]

    # 1. Explicit future/scheduled/pending events
    for ev in future_explicit:
        if ev.amount_in_home_currency is None:
            continue

        effective_date = ev.settlement_date or ev.event_date
        if effective_date is None or effective_date < request_date or effective_date > horizon_end:
            continue

        # Pending credits: don't count (not yet received)
        if ev.status == "pending" and ev.direction == "credit":
            continue

        if ev.event_id in spending_changes:
            new_amt = spending_changes[ev.event_id]
            if new_amt is None:
                continue  # stopped
            delta = new_amt if ev.direction == "credit" else -new_amt
        else:
            delta = ev.amount_in_home_currency if ev.direction == "credit" else -ev.amount_in_home_currency

        forecast.append((effective_date, delta, ev.category, ev.event_id))

    # Build a set of (category, direction, date) already covered by explicit events
    covered = defaultdict(set)
    for d, delta, cat, eid in forecast:
        direction = "credit" if delta > 0 else "debit"
        covered[(cat, direction)].add(d)

    # 2. Recurring projections from historical settled patterns
    # Pass scheduled future income events so salary can be projected even with sparse history
    scheduled_credits = [ev for ev in future_explicit if ev.direction == "credit" and ev.status == "scheduled"]
    recurring = _detect_recurring(
        settled_past, request_date, home_currency, converter, horizon_end,
        scheduled_future=scheduled_credits,
    )

    for (rec_date, rec_amount, rec_category, rec_direction, rec_etype) in recurring:
        if rec_date < request_date or rec_date > horizon_end:
            continue

        # Skip if already covered by an explicit scheduled/pending event nearby (+/- 5 days)
        existing_dates = covered.get((rec_category, rec_direction), set())
        if any(abs((rec_date - d).days) <= 5 for d in existing_dates):
            continue

        delta = rec_amount if rec_direction == "credit" else -rec_amount
        forecast.append((rec_date, delta, rec_category, f"recurring_{rec_category}"))

    # Sort chronologically
    forecast.sort(key=lambda x: x[0])
    return forecast


def run_forecast(
    starting_balance: Decimal,
    forecast_events: List[Tuple[date, Decimal, str, str]],
    minimum_balance: Decimal,
    initial_payment: Optional[Tuple[date, Decimal]] = None,
    extra_payments: Optional[List[Tuple[date, Decimal]]] = None,
) -> Tuple[Decimal, bool, List[Tuple[date, Decimal]]]:
    """
    Simulate the 90-day cash flow.
    initial_payment: (date, amount) paid at request_date

    Returns (min_balance, is_safe, balance_history).
    """
    balance = starting_balance

    if initial_payment:
        balance -= initial_payment[1]

    if balance < minimum_balance:
        return balance, False, [(initial_payment[0] if initial_payment else date.today(), balance)]

    all_events = list(forecast_events)
    if extra_payments:
        for ep_date, ep_amount in extra_payments:
            all_events.append((ep_date, -ep_amount, "extra_payment", "extra"))
    all_events.sort(key=lambda x: x[0])

    min_balance = balance
    balance_history = []

    for evt_date, delta, category, evt_id in all_events:
        balance += delta
        if balance < min_balance:
            min_balance = balance
        balance_history.append((evt_date, balance))
        if balance < minimum_balance:
            return min_balance, False, balance_history

    return min_balance, True, balance_history


def compute_safe_amount(
    starting_balance: Decimal,
    minimum_balance: Decimal,
    requested_amount: Decimal,
    request_date: date,
    forecast_events: List[Tuple[date, Decimal, str, str]],
) -> Decimal:
    """
    Binary search: max amount X such that paying X on request_date keeps 90-day forecast safe.
    Returns value in [0, requested_amount].
    """
    # Check 0 is safe baseline
    _, safe_zero, _ = run_forecast(
        starting_balance, forecast_events, minimum_balance,
        initial_payment=(request_date, Decimal("0")),
    )
    if not safe_zero:
        return Decimal("0")

    # Check full amount
    _, safe_full, _ = run_forecast(
        starting_balance, forecast_events, minimum_balance,
        initial_payment=(request_date, requested_amount),
    )
    if safe_full:
        return requested_amount

    # Binary search
    low, high = Decimal("0"), requested_amount
    for _ in range(60):
        if high - low < Decimal("0.01"):
            break
        mid = (low + high) / 2
        _, safe, _ = run_forecast(
            starting_balance, forecast_events, minimum_balance,
            initial_payment=(request_date, mid),
        )
        if safe:
            low = mid
        else:
            high = mid

    result = low.quantize(Decimal("0.01"))
    return max(Decimal("0"), min(result, requested_amount))


def find_earliest_full_payment_date(
    starting_balance: Decimal,
    minimum_balance: Decimal,
    requested_amount: Decimal,
    request_date: date,
    base_forecast_events: List[Tuple[date, Decimal, str, str]],
    forecast_days: int = FORECAST_DAYS,
) -> Optional[date]:
    """
    Find the earliest date in [request_date, request_date+forecast_days]
    where paying requested_amount in full is safe.
    """
    horizon_end = request_date + timedelta(days=forecast_days)
    check_date = request_date

    while check_date <= horizon_end:
        # Build event list with payment on check_date
        # On same date: credits (delta > 0) come first, then payment/debits
        all_ev = list(base_forecast_events)
        all_ev.append((check_date, -requested_amount, "full_payment", "payment"))
        all_ev.sort(key=lambda x: (x[0], 0 if x[1] > 0 else 1))

        sim_balance = starting_balance
        safe = True
        for d, delta, cat, eid in all_ev:
            if d < request_date or d > horizon_end:
                continue
            sim_balance += delta
            if sim_balance < minimum_balance:
                safe = False
                break

        if safe:
            return check_date

        check_date += timedelta(days=1)

    return None
