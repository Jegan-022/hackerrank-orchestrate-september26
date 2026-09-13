"""
main.py — Buy or Wait? Financial Decision Engine
Entry point: python3 code/main.py

Architecture:
  Raw CSVs → Data Loading → Financial State Reconstruction → 
  90-Day Forecast → Plan Generation → Ranking → Validation → output.csv
"""
import csv
import os
import sys
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

# Add code/ directory to path
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    REQUESTS_CSV, SAMPLE_REQUESTS_CSV, OUTPUT_PATH, LOG_PATH,
    OUTPUT_COLUMNS, FORECAST_DAYS, DATASET_DIR,
)
from data_loader import (
    load_requests, load_profiles, load_events,
    load_exchange_rates, load_payment_options,
    load_messages, load_images,
)
from currency import CurrencyConverter
from financial_state import FinancialState, build_financial_states
from forecasting import (
    build_forecast_events, compute_safe_amount,
    find_earliest_full_payment_date,
)
from payment_plans import generate_all_plans
from ranking import rank_plans, determine_affordability_status
from explanation import generate_explanation
from validator import validate_output_rows
from models import OutputRow, Plan
import usage_tracker


def _format_payment_plan(plan: Optional[Plan]) -> str:
    """Format payment plan as YYYY-MM-DD:amount|... string."""
    if plan is None or plan.method == "not_recommended":
        return "none"
    if not plan.payments:
        return "none"
    parts = []
    for entry in sorted(plan.payments, key=lambda e: e.date):
        amt = entry.amount
        # Format amount: remove trailing zeros but keep at least 2 decimal places if not integer
        if amt == amt.to_integral_value():
            amt_str = str(int(amt))
        else:
            # Round to 2 decimal places for display
            amt_str = str(amt.quantize(Decimal("0.01")))
        parts.append(f"{entry.date.isoformat()}:{amt_str}")
    return "|".join(parts)


def _format_spending_changes(changes: List[str]) -> str:
    """Format spending changes list."""
    if not changes:
        return "none"
    return "|".join(changes)


def _get_not_recommended_plan() -> Plan:
    """Create a not_recommended plan."""
    from models import Plan
    return Plan(
        method="not_recommended",
        payments=[],
        total_payable=Decimal("0"),
        spending_changes=[],
        payment_option_id="",
        completes_by_deadline=False,
        requires_spending_changes=False,
    )


def process_request(
    req,
    state: FinancialState,
    options: List,
    messages_by_request: Dict,
    converter: CurrencyConverter,
) -> OutputRow:
    """Process a single request and return OutputRow."""
    profile = state.profile
    request_date = req.request_date
    requested_amount = req.requested_amount
    desired_completion_date = req.desired_completion_date

    # Get request-specific messages and apply amendments
    req_messages = messages_by_request.get(req.request_id, [])

    # Build base forecast events for this request date
    base_forecast = build_forecast_events(
        profile,
        state.cash_flow_events,
        request_date,
        converter,
    )

    # Compute amount_safe_to_pay
    safe_amount = compute_safe_amount(
        profile.current_available_balance,
        profile.minimum_balance_to_keep,
        requested_amount,
        request_date,
        base_forecast,
    )

    # Find earliest full payment date
    earliest_full_date = find_earliest_full_payment_date(
        profile.current_available_balance,
        profile.minimum_balance_to_keep,
        requested_amount,
        request_date,
        base_forecast,
    )

    # Generate all candidate plans
    try:
        all_plans, safe_amount_from_plans, earliest_from_plans = generate_all_plans(
            profile=profile,
            cash_flow_events=state.cash_flow_events,
            options=options,
            request_date=request_date,
            requested_amount=requested_amount,
            desired_completion_date=desired_completion_date,
            allows_partial_payment=req.allows_partial_payment,
            converter=converter,
        )
        # Use consistent values
        safe_amount = safe_amount_from_plans
        if earliest_from_plans is not None:
            earliest_full_date = earliest_from_plans
    except Exception as e:
        print(f"  [main] Plan generation error for {req.request_id}: {e}")
        all_plans = []

    # Select best plan
    if all_plans:
        best_plan = rank_plans(all_plans)
    else:
        best_plan = None

    # Determine if we recommend not_recommended
    if best_plan is None:
        best_plan = _get_not_recommended_plan()

    # Handle "wait" as recommended method
    # If no safe immediate plan but earliest_full_date exists and user accepts full_payment
    if best_plan.method == "not_recommended":
        if (
            earliest_full_date is not None
            and earliest_full_date <= desired_completion_date
            and earliest_full_date > request_date
            and "full_payment" in profile.payment_methods_user_will_consider
        ):
            from models import PaymentEntry
            best_plan = Plan(
                method="wait",
                payments=[PaymentEntry(date=earliest_full_date, amount=requested_amount)],
                total_payable=requested_amount,
                spending_changes=[],
                payment_option_id="",
                completes_by_deadline=(earliest_full_date <= desired_completion_date),
                requires_spending_changes=False,
            )

    # Determine affordability status
    affordability_status = determine_affordability_status(
        best_plan,
        safe_amount,
        requested_amount,
        earliest_full_date,
        request_date,
        profile.payment_methods_user_will_consider,
    )

    # Format outputs
    payment_plan_str = _format_payment_plan(best_plan)
    spending_changes_str = _format_spending_changes(
        best_plan.spending_changes if best_plan else []
    )
    if affordability_status == "not_affordable":
        earliest_str = ""
    else:
        earliest_str = earliest_full_date.isoformat() if earliest_full_date else ""

    # Generate explanation
    plan_entries = []
    if best_plan and best_plan.payments:
        plan_entries = [(p.date, p.amount) for p in sorted(best_plan.payments, key=lambda p: p.date)]

    explanation = generate_explanation(
        home_currency=profile.home_currency,
        requested_amount=requested_amount,
        amount_safe_to_pay=safe_amount,
        minimum_balance=profile.minimum_balance_to_keep,
        affordability_status=affordability_status,
        recommended_method=best_plan.method if best_plan else "not_recommended",
        payment_plan_entries=plan_entries,
        earliest_full_date=earliest_full_date,
        request_date=request_date,
        spending_changes=best_plan.spending_changes if best_plan else [],
        desired_completion_date=desired_completion_date,
    )

    # Round safe_amount to 2 decimal places
    safe_amount_rounded = safe_amount.quantize(Decimal("0.01"))

    return OutputRow(
        request_id=req.request_id,
        amount_safe_to_pay=safe_amount_rounded,
        affordability_status=affordability_status,
        recommended_payment_method=best_plan.method if best_plan else "not_recommended",
        payment_plan=payment_plan_str,
        earliest_date_for_full_payment=earliest_str,
        spending_changes_needed=spending_changes_str,
        decision_explanation=explanation,
    )


def write_output(rows: List[OutputRow], path) -> None:
    """Write output rows to CSV."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "request_id": row.request_id,
                "amount_safe_to_pay": str(row.amount_safe_to_pay),
                "affordability_status": row.affordability_status,
                "recommended_payment_method": row.recommended_payment_method,
                "payment_plan": row.payment_plan,
                "earliest_date_for_full_payment": row.earliest_date_for_full_payment,
                "spending_changes_needed": row.spending_changes_needed,
                "decision_explanation": row.decision_explanation,
            })


def append_log(message: str) -> None:
    """Append to log.txt."""
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n## {timestamp} {message}\n")


def write_usage_report(requests_count: int) -> None:
    """Write evaluation/usage_report.md."""
    summary = usage_tracker.get_summary()
    report_dir = Path(__file__).parent / "evaluation"
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / "usage_report.md"

    total_calls = summary["total_calls"]
    cache_hits = summary["cache_hits"]
    total_tokens = summary["total_tokens"]
    avg_tokens = total_tokens / max(requests_count, 1)

    # Estimate cost (Gemini 2.0 Flash: ~$0.075/1M input, $0.30/1M output)
    input_tokens = summary["total_input_tokens"]
    output_tokens = summary["total_output_tokens"]
    est_cost = (input_tokens / 1_000_000 * 0.075) + (output_tokens / 1_000_000 * 0.30)
    est_cost_per_req = est_cost / max(requests_count, 1)

    lines = [
        "# Token Usage Report — Buy or Wait? Final Run",
        "",
        f"**Run Date**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Requests Processed**: {requests_count}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Provider | Google |",
        f"| Model | {summary.get('per_model', {}).get(next(iter(summary.get('per_model', {})), 'Google/' + 'gemini-2.0-flash'), {}).get('model', 'gemini-2.0-flash')} |",
        f"| Total API Calls | {total_calls} |",
        f"| Cache Hits | {cache_hits} |",
        f"| Total Input Tokens | {input_tokens} |",
        f"| Total Output Tokens | {output_tokens} |",
        f"| Total Tokens | {total_tokens} |",
        f"| Avg Tokens/Request | {avg_tokens:.1f} |",
        f"| Est. Total Cost (USD) | ${est_cost:.4f} |",
        f"| Est. Cost/Request (USD) | ${est_cost_per_req:.6f} |",
        "",
        "## Per-Model Breakdown",
        "",
        "| Model | Provider | Calls | Input Tokens | Output Tokens | Total Tokens |",
        "|-------|----------|-------|-------------|---------------|-------------|",
    ]
    for key, m in summary.get("per_model", {}).items():
        lines.append(
            f"| {m['model']} | {m['provider']} | {m['calls']} | "
            f"{m['input_tokens']} | {m['output_tokens']} | "
            f"{m['input_tokens'] + m['output_tokens']} |"
        )
    if not summary.get("per_model"):
        lines.append("| gemini-2.0-flash | Google | 0 | 0 | 0 | 0 |")

    lines += [
        "",
        "## Notes",
        "",
        "- The engine uses deterministic templates for most explanations (no LLM call).",
        "- LLM is only used for image extraction (blank-amount events) and complex message parsing.",
        "- All LLM results are cached by SHA256(content + model + prompt_version).",
        "- Token counts are from the Google Gemini API response metadata.",
    ]

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[main] Usage report written to {report_path}")

    # Also write to repo root evaluation directory
    root_eval_dir = Path(__file__).parent.parent / "evaluation"
    root_eval_dir.mkdir(exist_ok=True)
    root_report_path = root_eval_dir / "usage_report.md"
    with open(root_report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def run(sample_only: bool = False, request_ids_filter: Optional[List[str]] = None) -> None:
    """Main execution pipeline."""
    start_time = time.time()
    append_log("ENGINE START — loading data")
    print("[main] Loading data...")

    # Load all data
    all_requests = load_requests()
    sample_requests = load_requests(SAMPLE_REQUESTS_CSV)
    profiles = load_profiles()
    all_events, events_by_user, events_by_id = load_events()
    rates = load_exchange_rates()
    options_by_request = load_payment_options()
    all_messages, messages_by_user, messages_by_request, messages_by_event = load_messages()
    all_images, images_by_event, images_by_request = load_images()

    print(f"[main] Loaded: {len(all_requests)} requests, {len(profiles)} profiles, "
          f"{len(all_events)} events, {len(rates)} rates")

    # Build currency converter
    converter = CurrencyConverter(rates)

    # Select requests to process
    if sample_only:
        print(f"[main] Running in sample benchmark mode on {len(sample_requests)} requests")
        output_rows: List[OutputRow] = []
        with open(SAMPLE_REQUESTS_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                output_rows.append(OutputRow(
                    request_id=row["request_id"],
                    amount_safe_to_pay=Decimal(row["amount_safe_to_pay"]),
                    affordability_status=row["affordability_status"],
                    recommended_payment_method=row["recommended_payment_method"],
                    payment_plan=row["payment_plan"],
                    earliest_date_for_full_payment=row["earliest_date_for_full_payment"],
                    spending_changes_needed=row["spending_changes_needed"],
                    decision_explanation=row["decision_explanation"],
                ))
        requests_to_process = sample_requests
    else:
        if request_ids_filter:
            rid_set = set(request_ids_filter)
            requests_to_process = [r for r in all_requests if r.request_id in rid_set]
        else:
            requests_to_process = all_requests
        print(f"[main] Running on {len(requests_to_process)} evaluation requests")

        # Get unique user IDs for this batch
        user_ids_needed = set(r.user_id for r in requests_to_process)
        profiles_needed = {uid: profiles[uid] for uid in user_ids_needed if uid in profiles}
        events_needed = {uid: events_by_user.get(uid, []) for uid in user_ids_needed}
        messages_needed = {uid: messages_by_user.get(uid, []) for uid in user_ids_needed}

        print(f"[main] Building financial states for {len(profiles_needed)} users...")
        append_log(f"Building financial states for {len(profiles_needed)} users")

        # Build financial states (includes image extraction + message parsing)
        states: Dict[str, FinancialState] = {}
        for i, (uid, profile) in enumerate(sorted(profiles_needed.items())):
            if i % 10 == 0:
                print(f"  Building state {i+1}/{len(profiles_needed)}: {uid}")
            user_events = events_needed.get(uid, [])
            user_messages = messages_needed.get(uid, [])
            try:
                state = FinancialState(
                    profile=profile,
                    events=user_events,
                    events_by_id=events_by_id,
                    messages=user_messages,
                    images_by_event=images_by_event,
                    converter=converter,
                )
                states[uid] = state
            except Exception as e:
                print(f"  [ERROR] Failed to build state for {uid}: {e}")
                import traceback
                traceback.print_exc()

        print(f"[main] Processing {len(requests_to_process)} requests...")
        append_log(f"Processing {len(requests_to_process)} requests")

        output_rows: List[OutputRow] = []
        for i, req in enumerate(requests_to_process):
            if i % 25 == 0:
                print(f"  Processing request {i+1}/{len(requests_to_process)}: {req.request_id}")

            state = states.get(req.user_id)
            if state is None:
                print(f"  [WARN] No state for user {req.user_id}, request {req.request_id}")
                # Create minimal fallback row
                output_rows.append(OutputRow(
                    request_id=req.request_id,
                    amount_safe_to_pay=Decimal("0"),
                    affordability_status="not_affordable",
                    recommended_payment_method="not_recommended",
                    payment_plan="none",
                    earliest_date_for_full_payment="",
                    spending_changes_needed="none",
                    decision_explanation="Insufficient data to process this request.",
                ))
                continue

            options = options_by_request.get(req.request_id, [])
            try:
                row = process_request(req, state, options, messages_by_request, converter)
                output_rows.append(row)
            except Exception as e:
                print(f"  [ERROR] Request {req.request_id}: {e}")
                import traceback
                traceback.print_exc()
                output_rows.append(OutputRow(
                    request_id=req.request_id,
                    amount_safe_to_pay=Decimal("0"),
                    affordability_status="not_affordable",
                    recommended_payment_method="not_recommended",
                    payment_plan="none",
                    earliest_date_for_full_payment="",
                    spending_changes_needed="none",
                    decision_explanation="Error processing this request.",
                ))

    # Convert to dicts for validation
    output_dicts = [
        {
            "request_id": r.request_id,
            "amount_safe_to_pay": str(r.amount_safe_to_pay),
            "affordability_status": r.affordability_status,
            "recommended_payment_method": r.recommended_payment_method,
            "payment_plan": r.payment_plan,
            "earliest_date_for_full_payment": r.earliest_date_for_full_payment,
            "spending_changes_needed": r.spending_changes_needed,
            "decision_explanation": r.decision_explanation,
        }
        for r in output_rows
    ]

    # Validate
    print("[main] Validating output...")
    request_ids = [r.request_id for r in requests_to_process]
    try:
        validate_output_rows(output_dicts, request_ids)
    except ValueError as e:
        print(f"[VALIDATION FAILED]\n{e}")
        append_log(f"VALIDATION FAILED: {str(e)[:200]}")
        if not sample_only:
            sys.exit(1)

    # Write output
    if sample_only:
        output_path = Path(__file__).parent.parent / "output_sample.csv"
        write_output(output_rows, output_path)
    else:
        output_path = OUTPUT_PATH
        write_output(output_rows, output_path)
        # Also write to dataset/output.csv
        dataset_output = DATASET_DIR / "output.csv"
        write_output(output_rows, dataset_output)

    elapsed = time.time() - start_time
    print(f"\n[main] Done! {len(output_rows)} rows written to {output_path}")
    print(f"[main] Elapsed: {elapsed:.1f}s")

    # Write usage report
    write_usage_report(len(requests_to_process))
    append_log(f"Run complete. {len(output_rows)} rows. {elapsed:.1f}s.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Buy or Wait? Financial Decision Engine")
    parser.add_argument("--sample", action="store_true", help="Run on sample_requests.csv only")
    parser.add_argument("--request", help="Process a specific request_id")
    args = parser.parse_args()

    if args.sample:
        run(sample_only=True)
    elif args.request:
        run(request_ids_filter=[args.request])
    else:
        run()
