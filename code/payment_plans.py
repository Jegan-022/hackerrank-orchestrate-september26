"""
payment_plans.py — Generate all candidate payment plans for a request.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Tuple

from models import (
    Plan, PaymentEntry, PaymentOption, FinancialProfile, FinancialEvent,
)
from forecasting import (
    build_forecast_events, run_forecast, compute_safe_amount,
    find_earliest_full_payment_date, FORECAST_DAYS,
)
from spending_changes import (
    generate_spending_change_sets, apply_spending_changes,
)
from currency import CurrencyConverter


def _is_installment_eligible(
    profile: FinancialProfile,
    option: PaymentOption,
    request_date: date,
    desired_completion_date: date,
) -> bool:
    """Check if an installment option is eligible given user preferences."""
    if "installments" not in profile.payment_methods_user_will_consider:
        return False
    if option.payment_method != "installments":
        return False
    # Check max_installment_months
    if profile.max_installment_months is not None:
        # Number of months = (number_of_payments * payment_frequency_days) / 30
        freq = option.payment_frequency_days or 30
        total_months = (option.number_of_payments * freq) / 30
        if total_months > profile.max_installment_months:
            return False
    # Check last payment date is within desired_completion_date
    freq = option.payment_frequency_days or 30
    last_payment_date = option.first_payment_date + timedelta(
        days=freq * (option.number_of_payments - 1)
    )
    if last_payment_date > desired_completion_date:
        return False
    return True


def _build_installment_payment_entries(option: PaymentOption) -> List[PaymentEntry]:
    """Build the exact payment schedule for an installment option."""
    entries = []
    freq = option.payment_frequency_days or 30
    current_date = option.first_payment_date
    for i in range(option.number_of_payments):
        entries.append(PaymentEntry(
            date=current_date,
            amount=option.payment_amount,
        ))
        current_date += timedelta(days=freq)
    return entries


def _check_installment_safe(
    starting_balance: Decimal,
    minimum_balance: Decimal,
    profile: FinancialProfile,
    option: PaymentOption,
    base_forecast_events: List[Tuple],
    request_date: date,
    spending_changes_dict: Optional[Dict] = None,
) -> bool:
    """Check if an installment plan keeps the forecast safe."""
    freq = option.payment_frequency_days or 30
    balance = starting_balance

    entries = _build_installment_payment_entries(option)
    # Sort all events + installment payments chronologically
    all_events = list(base_forecast_events)
    for entry in entries:
        all_events.append((entry.date, -entry.amount, "installment_payment", "installment"))
    all_events.sort(key=lambda x: x[0])

    # Filter to forecast window
    horizon_end = request_date + timedelta(days=FORECAST_DAYS)
    all_events = [(d, delta, cat, eid) for d, delta, cat, eid in all_events if d >= request_date and d <= horizon_end]

    for evt_date, delta, cat, eid in all_events:
        balance += delta
        if balance < minimum_balance:
            return False
    return True


def generate_all_plans(
    profile: FinancialProfile,
    cash_flow_events: List[FinancialEvent],
    options: List[PaymentOption],
    request_date: date,
    requested_amount: Decimal,
    desired_completion_date: date,
    allows_partial_payment: bool,
    converter: CurrencyConverter,
) -> List[Plan]:
    """
    Generate all candidate plans. Returns a list of Plan objects.
    """
    home_currency = profile.home_currency
    min_balance = profile.minimum_balance_to_keep
    starting_balance = profile.current_available_balance

    # Build base forecast events (no payment)
    base_forecast = build_forecast_events(
        profile, cash_flow_events, request_date, converter,
    )

    # Compute amount_safe_to_pay (before spending changes)
    safe_amount = compute_safe_amount(
        starting_balance, min_balance, requested_amount, request_date, base_forecast,
    )

    # Find earliest full payment date (without spending changes)
    earliest_full_date = find_earliest_full_payment_date(
        starting_balance, min_balance, requested_amount, request_date, base_forecast,
    )

    plans: List[Plan] = []

    # --- Plan 1: FULL PAYMENT NOW ---
    if "full_payment" in profile.payment_methods_user_will_consider:
        if safe_amount >= requested_amount:
            plan = Plan(
                method="full_payment",
                payments=[PaymentEntry(date=request_date, amount=requested_amount)],
                total_payable=requested_amount,
                spending_changes=[],
                payment_option_id="",
                completes_by_deadline=(request_date <= desired_completion_date),
                requires_spending_changes=False,
            )
            plans.append(plan)

    # --- Plan 2: PARTIAL PAYMENT ---
    if (
        allows_partial_payment
        and "partial_payment" in profile.payment_methods_user_will_consider
        and Decimal("0") < safe_amount < requested_amount
        and earliest_full_date is not None
        and earliest_full_date <= desired_completion_date
    ):
        remaining = requested_amount - safe_amount
        plan = Plan(
            method="partial_payment",
            payments=[
                PaymentEntry(date=request_date, amount=safe_amount),
                PaymentEntry(date=earliest_full_date, amount=remaining),
            ],
            total_payable=requested_amount,
            spending_changes=[],
            payment_option_id="",
            completes_by_deadline=(earliest_full_date <= desired_completion_date),
            requires_spending_changes=False,
        )
        plans.append(plan)

    # --- Plan 3: INSTALLMENTS ---
    for option in options:
        if not _is_installment_eligible(profile, option, request_date, desired_completion_date):
            continue
        # Check if installment plan is safe
        is_safe = _check_installment_safe(
            starting_balance, min_balance, profile, option,
            base_forecast, request_date,
        )
        if is_safe:
            entries = _build_installment_payment_entries(option)
            freq = option.payment_frequency_days or 30
            last_date = option.first_payment_date + timedelta(
                days=freq * (option.number_of_payments - 1)
            )
            plan = Plan(
                method="installments",
                payments=entries,
                total_payable=option.total_payable_amount,
                spending_changes=[],
                payment_option_id=option.payment_option_id,
                completes_by_deadline=(last_date <= desired_completion_date),
                requires_spending_changes=False,
            )
            plans.append(plan)

    # --- Plan 4: WAIT (full payment later) ---
    if (
        "full_payment" in profile.payment_methods_user_will_consider
        and earliest_full_date is not None
        and earliest_full_date > request_date
        and earliest_full_date <= desired_completion_date
    ):
        plan = Plan(
            method="wait",
            payments=[PaymentEntry(date=earliest_full_date, amount=requested_amount)],
            total_payable=requested_amount,
            spending_changes=[],
            payment_option_id="",
            completes_by_deadline=(earliest_full_date <= desired_completion_date),
            requires_spending_changes=False,
        )
        plans.append(plan)

    # --- Plan 5: WITH SPENDING CHANGES ---
    # Only try spending changes if no safe plan exists without them
    if not any(p.completes_by_deadline and not p.requires_spending_changes for p in plans):
        # Compute how much extra savings we need
        # We need to free up enough to make full payment safe
        needed_savings = requested_amount - safe_amount
        if needed_savings > Decimal("0"):
            change_sets = generate_spending_change_sets(
                profile, cash_flow_events, request_date, needed_savings
            )
            for change_set in change_sets[:3]:
                # Build forecast with spending changes applied
                changes_dict = apply_spending_changes(cash_flow_events, change_set)
                modified_forecast = build_forecast_events(
                    profile, cash_flow_events, request_date, converter,
                    spending_changes=changes_dict,
                )
                # Check if full payment is now safe
                modified_safe = compute_safe_amount(
                    starting_balance, min_balance, requested_amount,
                    request_date, modified_forecast,
                )
                if modified_safe >= requested_amount:
                    if "full_payment" in profile.payment_methods_user_will_consider:
                        plan = Plan(
                            method="full_payment",
                            payments=[PaymentEntry(date=request_date, amount=requested_amount)],
                            total_payable=requested_amount,
                            spending_changes=change_set,
                            payment_option_id="",
                            completes_by_deadline=(request_date <= desired_completion_date),
                            requires_spending_changes=True,
                        )
                        plans.append(plan)

                # Try installments with spending changes
                for option in options:
                    if not _is_installment_eligible(profile, option, request_date, desired_completion_date):
                        continue
                    is_safe = _check_installment_safe(
                        starting_balance, min_balance, profile, option,
                        modified_forecast, request_date,
                    )
                    if is_safe:
                        entries = _build_installment_payment_entries(option)
                        freq = option.payment_frequency_days or 30
                        last_date = option.first_payment_date + timedelta(
                            days=freq * (option.number_of_payments - 1)
                        )
                        plan = Plan(
                            method="installments",
                            payments=entries,
                            total_payable=option.total_payable_amount,
                            spending_changes=change_set,
                            payment_option_id=option.payment_option_id,
                            completes_by_deadline=(last_date <= desired_completion_date),
                            requires_spending_changes=True,
                        )
                        plans.append(plan)

    return plans, safe_amount, earliest_full_date
