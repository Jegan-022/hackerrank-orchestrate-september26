"""
ranking.py — Deterministic 6-level plan ranking.
"""
from decimal import Decimal
from typing import List, Optional

from models import Plan


def _payment_option_id_sort_key(pid: str) -> int:
    """Convert payment_option_id like 'payment_option_01' to integer for sorting."""
    parts = pid.split("_")
    try:
        return int(parts[-1])
    except (ValueError, IndexError):
        return 999999


def rank_plans(plans: List[Plan]) -> Optional[Plan]:
    """
    Rank candidate plans using 6-level lexicographic ordering.
    Returns the best plan, or None if no plans.

    Ranking (lower = better):
    1. completes_by_deadline: True > False (True is preferred)
    2. requires_spending_changes: False > True (no changes preferred)
    3. total_payable: lower is better
    4. first payment date: earlier is better
    5. number of payments: fewer is better
    6. payment_option_id: lowest numeric ID wins
    """
    if not plans:
        return None

    def sort_key(plan: Plan):
        # 1. completes_by_deadline: True=0, False=1 (lower is better)
        k1 = 0 if plan.completes_by_deadline else 1
        # 2. requires_spending_changes: False=0, True=1
        k2 = 1 if plan.requires_spending_changes else 0
        # 3. total_payable: lower is better
        k3 = float(plan.total_payable)
        # 4. first payment date: earlier is better
        first_date = min(p.date for p in plan.payments) if plan.payments else None
        k4 = first_date.toordinal() if first_date else 9999999
        # 5. number of payments: fewer is better
        k5 = len(plan.payments)
        # 6. payment_option_id: lowest numeric value wins
        k6 = _payment_option_id_sort_key(plan.payment_option_id) if plan.payment_option_id else 0

        return (k1, k2, k3, k4, k5, k6)

    sorted_plans = sorted(plans, key=sort_key)
    return sorted_plans[0]


def determine_affordability_status(
    best_plan: Optional[Plan],
    safe_amount: Decimal,
    requested_amount: Decimal,
    earliest_full_date,
    request_date,
    user_methods: List[str],
) -> str:
    """
    Determine the affordability_status from the best plan.

    affordable_now: full amount safe today AND user accepts full_payment
    affordable_with_plan: completed via partial/installments/spending_changes
    affordable_later: full amount safe later (but not now), user accepts full_payment
    not_affordable: cannot be completed safely within forecast period
    """
    if best_plan is None:
        return "not_affordable"

    method = best_plan.method

    if method == "full_payment" and not best_plan.requires_spending_changes:
        # Full payment now without spending changes = affordable_now
        payments = best_plan.payments
        if payments and payments[0].date == request_date:
            return "affordable_now"
        return "affordable_with_plan"

    if method in ("full_payment", "partial_payment", "installments"):
        return "affordable_with_plan"

    if method == "wait":
        return "affordable_later"

    if method == "not_recommended":
        return "not_affordable"

    return "not_affordable"
