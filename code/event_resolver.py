"""
event_resolver.py — Resolves linked event chains, deduplication, and status filtering.

Resolution priority (from problem_statement.md and AGENTS.md):
1. Explicit cancellation, settlement, or amendment
2. Newer record from same source
3. Settled event over estimate/forecast
4. Financially safer interpretation
"""
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict

from models import FinancialEvent


# Statuses that contribute to cash flow (debit = money out, credit = money in)
# Only these statuses are used for forecasting
ACTIVE_DEBIT_STATUSES = {"pending", "scheduled", "settled"}
ACTIVE_CREDIT_STATUSES = {"scheduled", "settled"}  # NOT pending credits
HISTORICAL_STATUSES = {"settled"}
EXCLUDE_STATUSES = {"cancelled", "failed"}
NON_CASH_STATUSES = {"unrealized"}


def resolve_events(
    events_by_id: Dict[str, FinancialEvent],
    user_events: List[FinancialEvent],
) -> List[FinancialEvent]:
    """
    Resolve linked event chains and deduplicate for a given user's events.
    Returns the list of events that should be used for cash flow calculation.
    """
    # Build the event graph: which events supersede which
    # linked_event_id points to an EARLIER event that this event modifies
    superseded_by: Dict[str, str] = {}  # earlier_id -> later_id
    for ev in user_events:
        if ev.linked_event_id:
            # This event supersedes linked_event_id
            superseded_by[ev.linked_event_id] = ev.event_id

    # Identify events that should be excluded
    excluded_ids: Set[str] = set()

    # 1. Exclude cancelled and failed events
    for ev in user_events:
        if ev.status in {"cancelled", "failed"}:
            excluded_ids.add(ev.event_id)

    # 2. Exclude non-cash (investment valuations)
    for ev in user_events:
        if ev.direction == "non_cash" or ev.status == "unrealized":
            excluded_ids.add(ev.event_id)

    # 3. Resolve linked chains:
    # If event A is superseded by event B:
    #   - If B is a refund for A: exclude A (or handle B as net)
    #   - If B is a cancellation of A: exclude A (B itself is likely cancelled)
    #   - If B amends A: exclude A, use B
    for earlier_id, later_id in superseded_by.items():
        later = events_by_id.get(later_id)
        if later is None:
            continue
        if later.status in {"cancelled", "failed"}:
            # Both are cancelled — exclude both
            excluded_ids.add(earlier_id)
            excluded_ids.add(later_id)
        elif later.event_type == "refund":
            # The earlier event is a debit, the refund credits back.
            # We keep BOTH as they represent real cash flows.
            # Don't exclude either unless they are cancelled/failed.
            pass
        else:
            # Later event amends/settles earlier — exclude earlier
            excluded_ids.add(earlier_id)

    # 4. Deduplicate pending + settled representations of same transaction
    # If a settled event exists that was previously pending (same description, amount, user),
    # exclude the pending version.
    # This is covered by linked_event_id chains above.

    # 5. Pending credit exclusion: credit events with status=pending are NOT counted
    # (bonuses, commissions, refunds pending) - handled in forecasting

    result = [ev for ev in user_events if ev.event_id not in excluded_ids]
    return result


def get_cash_flow_events(resolved_events: List[FinancialEvent]) -> List[FinancialEvent]:
    """
    From resolved events, return only those that affect cash flow.
    - Settled debits and credits: yes
    - Pending debits: yes (reserved)
    - Pending credits: NO
    - Scheduled debits/credits: yes
    - Investment purchases (settled): yes (money out)
    - Investment sales (settled): yes (money in)
    - Subscription (settled): yes (money out)
    - debt_payment (settled/scheduled): yes
    """
    cash_events = []
    for ev in resolved_events:
        if ev.direction == "non_cash":
            continue
        if ev.status in {"cancelled", "failed", "unrealized"}:
            continue
        if ev.direction == "credit" and ev.status == "pending":
            # Pending credits: do not count until settled
            continue
        cash_events.append(ev)
    return cash_events


def detect_recurring_events(
    user_events: List[FinancialEvent],
    request_date: date,
    home_currency: str,
    converter,
) -> List[Tuple[date, Decimal, str, str, str]]:
    """
    Detect recurring income/expense patterns from historical settled events.
    Returns list of (future_date, amount_in_home_currency, category, direction, event_type)
    for dates within the next 90 days from request_date.

    Detection strategy:
    - Group by (user, category, direction) 
    - Find events with roughly consistent monthly/weekly/biweekly intervals
    - Project forward from the most recent occurrence
    """
    from datetime import timedelta
    import statistics

    FORECAST_HORIZON = 90

    # Only use settled historical events for recurrence detection
    historical = [
        ev for ev in user_events
        if ev.status == "settled"
        and ev.direction in ("debit", "credit")
        and ev.event_date < request_date
        and ev.amount is not None
    ]

    # Group by (category, direction, event_type)
    grouped: Dict[Tuple[str, str, str], List[FinancialEvent]] = defaultdict(list)
    for ev in historical:
        key = (ev.category, ev.direction, ev.event_type)
        grouped[key].append(ev)

    recurring_projections = []

    for (category, direction, etype), evts in grouped.items():
        if len(evts) < 2:
            continue

        # Sort by date
        evts_sorted = sorted(evts, key=lambda e: e.event_date)

        # Calculate gaps between consecutive events
        dates = [e.event_date for e in evts_sorted]
        gaps = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]

        if not gaps:
            continue

        # Determine if gaps are consistent (std dev < 20% of mean)
        mean_gap = statistics.mean(gaps)
        if len(gaps) > 1:
            std_gap = statistics.stdev(gaps)
        else:
            std_gap = 0

        # Only treat as recurring if gap is reasonable (weekly=7, biweekly=14, monthly=28-31)
        is_recurring = False
        interval_days = None

        if 6 <= mean_gap <= 8 and std_gap < 3:
            is_recurring = True
            interval_days = 7
        elif 13 <= mean_gap <= 16 and std_gap < 4:
            is_recurring = True
            interval_days = 14
        elif 27 <= mean_gap <= 32 and std_gap < 5:
            is_recurring = True
            interval_days = 30
        elif 58 <= mean_gap <= 65 and std_gap < 7:
            is_recurring = True
            interval_days = 60
        elif 88 <= mean_gap <= 95 and std_gap < 10:
            is_recurring = True
            interval_days = 90
        elif len(evts) >= 3 and std_gap / max(mean_gap, 1) < 0.25:
            # Somewhat consistent — use mean gap
            is_recurring = True
            interval_days = round(mean_gap)

        if not is_recurring or interval_days is None or interval_days <= 0:
            continue

        # Use average amount (in home currency) from recent occurrences
        amounts_in_home = []
        for ev in evts_sorted[-6:]:  # Use last 6 occurrences
            if ev.amount is None:
                continue
            evt_date = ev.settlement_date or ev.event_date
            if ev.currency == home_currency:
                amounts_in_home.append(ev.amount)
            else:
                converted = converter.convert(ev.amount, ev.currency, home_currency, evt_date)
                if converted is not None:
                    amounts_in_home.append(converted)

        if not amounts_in_home:
            continue

        avg_amount = sum(amounts_in_home) / len(amounts_in_home)

        # Project forward from last occurrence
        last_date = evts_sorted[-1].event_date
        from datetime import timedelta
        next_date = last_date + timedelta(days=interval_days)

        horizon_end = request_date + timedelta(days=FORECAST_HORIZON)

        while next_date <= horizon_end:
            if next_date >= request_date:
                recurring_projections.append((
                    next_date,
                    avg_amount,
                    category,
                    direction,
                    etype,
                ))
            next_date += timedelta(days=interval_days)

    return recurring_projections
