"""
explanation.py — Generate concise grounded decision explanations.
Uses deterministic templates first, LLM fallback if needed.
"""
from decimal import Decimal
from datetime import date
from typing import Optional, List

from config import LLM_MODEL, EXPLANATION_PROMPT_VERSION, GEMINI_API_KEY
from cache import get_cached, set_cached
import usage_tracker


def _format_amount(amount: Decimal, currency: str) -> str:
    """Format amount with currency for display."""
    # Format with thousand separators
    if amount == amount.to_integral_value():
        formatted = f"{int(amount):,}"
    else:
        formatted = f"{float(amount):,.2f}"
    return f"{currency} {formatted}"


def generate_explanation(
    home_currency: str,
    requested_amount: Decimal,
    amount_safe_to_pay: Decimal,
    minimum_balance: Decimal,
    affordability_status: str,
    recommended_method: str,
    payment_plan_entries: List[tuple],  # list of (date, amount)
    earliest_full_date: Optional[date],
    request_date: date,
    spending_changes: List[str],
    desired_completion_date: date,
) -> str:
    """
    Generate a 1-2 sentence explanation grounded in deterministic facts.
    Uses templates by default, LLM fallback only if needed.
    """
    curr = home_currency
    req_fmt = _format_amount(requested_amount, curr)
    safe_fmt = _format_amount(amount_safe_to_pay, curr)
    min_fmt = _format_amount(minimum_balance, curr)

    # Build spending change description
    change_desc = ""
    if spending_changes and spending_changes != ["none"]:
        parts = []
        for ch in spending_changes:
            if ch.startswith("stop:"):
                eid = ch[5:]
                parts.append(f"stop the {eid} subscription")
            elif ch.startswith("reduce_to:"):
                p = ch.split(":")
                if len(p) >= 3:
                    eid = p[1]
                    new_amt = p[2]
                    parts.append(f"reduce {eid} to {curr} {new_amt}")
        change_desc = ", ".join(parts)

    # Template selection by affordability status + method
    if affordability_status == "affordable_now" and recommended_method == "full_payment":
        return (
            f"Pay {req_fmt} today. "
            f"This leaves at least {min_fmt} available over the next 90 days."
        )

    elif affordability_status == "affordable_with_plan" and recommended_method == "full_payment" and spending_changes:
        return (
            f"{change_desc.capitalize()}, then pay {req_fmt} today. "
            f"This leaves at least {min_fmt} available."
        )

    elif affordability_status == "affordable_with_plan" and recommended_method == "installments":
        if payment_plan_entries:
            n = len(payment_plan_entries)
            amt_each = payment_plan_entries[0][1]
            amt_fmt = _format_amount(amt_each, curr)
            first_date = payment_plan_entries[0][0].strftime("%d %B %Y").lstrip("0")
            return (
                f"Use {n} installments of {amt_fmt}, starting {first_date}. "
                f"This leaves at least {min_fmt} available."
            )
        return f"Use installments to pay {req_fmt}. This keeps the {min_fmt} minimum protected."

    elif affordability_status == "affordable_with_plan" and recommended_method == "partial_payment":
        if len(payment_plan_entries) >= 2:
            p1_date = payment_plan_entries[0][0].strftime("%d %B %Y").lstrip("0")
            p1_amt = _format_amount(payment_plan_entries[0][1], curr)
            p2_date = payment_plan_entries[1][0].strftime("%d %B %Y").lstrip("0")
            p2_amt = _format_amount(payment_plan_entries[1][1], curr)
            return (
                f"Pay {p1_amt} today and the remaining {p2_amt} on {p2_date}. "
                f"This completes the full request and keeps the {min_fmt} minimum protected."
            )
        return f"Pay {safe_fmt} today and the remainder later. This keeps the {min_fmt} minimum protected."

    elif affordability_status == "affordable_later" and recommended_method == "wait":
        if earliest_full_date:
            pay_date = earliest_full_date.strftime("%d %B %Y").lstrip("0")
            return (
                f"Pay {req_fmt} in full on {pay_date}. "
                f"Paying earlier would take the balance below the {min_fmt} minimum."
            )
        return f"Wait until funds are available, then pay {req_fmt} in full."

    elif affordability_status == "not_affordable" and recommended_method == "not_recommended":
        if earliest_full_date is None:
            return (
                f"Do not make this payment by {desired_completion_date.strftime('%d %B %Y').lstrip('0')}. "
                f"None of the available options keeps the {min_fmt} minimum protected."
            )
        else:
            return (
                f"Do not proceed with the {req_fmt} request. "
                f"Although {safe_fmt} is available today, "
                f"the full amount cannot be completed safely within 90 days."
            )

    # Fallback
    return (
        f"Current balance allows paying {safe_fmt} safely. "
        f"The {min_fmt} minimum balance must be maintained throughout the forecast period."
    )
