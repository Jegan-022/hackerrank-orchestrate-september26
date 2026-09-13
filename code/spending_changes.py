"""
spending_changes.py — Spending change optimization.
Only modifies flexible recurring expenses to make otherwise-unsafe plans safe.
"""
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from models import FinancialEvent, FinancialProfile
from config import STOPPABLE_FLEXIBILITY, REDUCIBLE_FLEXIBILITY


def get_flexible_events(
    profile: FinancialProfile,
    cash_flow_events: List[FinancialEvent],
    request_date: date,
) -> List[FinancialEvent]:
    """
    Return events that are eligible for spending changes:
    - direction = debit
    - flexibility in (stoppable, reducible, reducible_or_stoppable)
    - category NOT in expense_categories_to_protect
    - category in (expense_categories_to_reduce OR expense_categories_to_stop)
    - Future events in the 90-day window
    """
    from datetime import timedelta
    horizon_end = request_date + timedelta(days=90)
    protected = set(profile.expense_categories_to_protect)
    reducible_cats = set(profile.expense_categories_to_reduce)
    stoppable_cats = set(profile.expense_categories_to_stop)
    allowed_cats = reducible_cats | stoppable_cats

    eligible = []
    for ev in cash_flow_events:
        if ev.direction != "debit":
            continue
        if ev.category in protected:
            continue
        if ev.category not in allowed_cats:
            continue
        if ev.flexibility not in (STOPPABLE_FLEXIBILITY | REDUCIBLE_FLEXIBILITY):
            continue
        effective_date = ev.settlement_date or ev.event_date
        if effective_date is None:
            continue
        if effective_date < request_date or effective_date > horizon_end:
            continue
        if ev.amount_in_home_currency is None:
            continue
        eligible.append(ev)

    return eligible


def can_stop(profile: FinancialProfile, ev: FinancialEvent) -> bool:
    """Can this event be stopped?"""
    stoppable_cats = set(profile.expense_categories_to_stop)
    protected = set(profile.expense_categories_to_protect)
    return (
        ev.flexibility in STOPPABLE_FLEXIBILITY
        and ev.category in stoppable_cats
        and ev.category not in protected
    )


def can_reduce(profile: FinancialProfile, ev: FinancialEvent) -> bool:
    """Can this event be reduced?"""
    reducible_cats = set(profile.expense_categories_to_reduce)
    protected = set(profile.expense_categories_to_protect)
    return (
        ev.flexibility in REDUCIBLE_FLEXIBILITY
        and ev.category in reducible_cats
        and ev.category not in protected
    )


def generate_spending_change_sets(
    profile: FinancialProfile,
    cash_flow_events: List[FinancialEvent],
    request_date: date,
    required_savings: Decimal,
) -> List[List[str]]:
    """
    Generate candidate spending change sets (up to 3 changes) that save
    at least required_savings from the 90-day forecast.

    Returns list of change lists, each change being:
    - "stop:event_id"
    - "reduce_to:event_id:new_amount"

    Changes must:
    - Only target flexible events
    - Not stop AND reduce the same event
    - Maximum 3 changes total
    - Actually save enough
    """
    flexible = get_flexible_events(profile, cash_flow_events, request_date)

    if not flexible:
        return []

    # Sort by savings potential (highest saving first)
    def saving_for_event(ev):
        if can_stop(profile, ev):
            return ev.amount_in_home_currency or Decimal("0")
        elif can_reduce(profile, ev) and ev.minimum_allowed_amount is not None:
            min_amt = ev.minimum_allowed_amount
            if ev.currency != profile.home_currency:
                # Already in home currency
                pass
            return (ev.amount_in_home_currency or Decimal("0")) - min_amt
        elif can_reduce(profile, ev):
            # Assume reduce to half
            return (ev.amount_in_home_currency or Decimal("0")) * Decimal("0.5")
        return Decimal("0")

    flexible.sort(key=saving_for_event, reverse=True)

    # Try single changes first, then pairs, then triples
    change_sets = []
    MAX_CHANGES = 3

    # Generate all single changes
    single_changes = []
    for ev in flexible[:10]:  # Limit candidates
        if can_stop(profile, ev):
            single_changes.append((f"stop:{ev.event_id}", saving_for_event(ev), ev.event_id, "stop"))
        if can_reduce(profile, ev):
            if ev.minimum_allowed_amount is not None:
                new_amt = ev.minimum_allowed_amount
            else:
                new_amt = (ev.amount_in_home_currency or Decimal("0")) * Decimal("0.5")
            new_amt = new_amt.quantize(Decimal("0.01"))
            saving = (ev.amount_in_home_currency or Decimal("0")) - new_amt
            single_changes.append((
                f"reduce_to:{ev.event_id}:{new_amt}",
                saving,
                ev.event_id,
                "reduce",
            ))

    # Check if any single change is sufficient
    for change_str, saving, eid, ctype in single_changes:
        if saving >= required_savings:
            change_sets.append([change_str])

    if change_sets:
        return change_sets[:3]  # Return up to 3 alternatives

    # Try pairs
    if len(single_changes) >= 2:
        for i in range(min(len(single_changes), 8)):
            for j in range(i + 1, min(len(single_changes), 8)):
                c1, s1, e1, t1 = single_changes[i]
                c2, s2, e2, t2 = single_changes[j]
                if e1 == e2:
                    continue  # Can't stop and reduce same event
                if s1 + s2 >= required_savings:
                    change_sets.append([c1, c2])
                    if len(change_sets) >= 3:
                        return change_sets

    # Try triples
    if len(single_changes) >= 3:
        for i in range(min(len(single_changes), 6)):
            for j in range(i + 1, min(len(single_changes), 6)):
                for k in range(j + 1, min(len(single_changes), 6)):
                    c1, s1, e1, t1 = single_changes[i]
                    c2, s2, e2, t2 = single_changes[j]
                    c3, s3, e3, t3 = single_changes[k]
                    if len({e1, e2, e3}) < 3:
                        continue  # Duplicate event
                    if s1 + s2 + s3 >= required_savings:
                        change_sets.append([c1, c2, c3])
                        if len(change_sets) >= 3:
                            return change_sets

    return change_sets


def apply_spending_changes(
    cash_flow_events: List[FinancialEvent],
    spending_changes: List[str],
) -> Dict[str, Optional[Decimal]]:
    """
    Convert spending change strings to a dict: event_id -> new_amount (None = stopped).
    Used by forecasting engine.
    """
    result: Dict[str, Optional[Decimal]] = {}
    for change in spending_changes:
        if change.startswith("stop:"):
            event_id = change[5:]
            result[event_id] = None  # None = stopped
        elif change.startswith("reduce_to:"):
            parts = change.split(":")
            if len(parts) >= 3:
                event_id = parts[1]
                try:
                    new_amount = Decimal(parts[2])
                    result[event_id] = new_amount
                except Exception:
                    pass
    return result
