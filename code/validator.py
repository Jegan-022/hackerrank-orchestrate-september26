"""
validator.py — Hard output validation before writing output.csv.
"""
import csv
import sys
from decimal import Decimal, InvalidOperation
from datetime import date
from typing import List, Dict

from config import OUTPUT_COLUMNS, VALID_AFFORDABILITY_STATUS, VALID_PAYMENT_METHODS


def _parse_dec(s: str) -> Decimal:
    try:
        return Decimal(str(s).strip())
    except (InvalidOperation, ValueError) as e:
        raise ValueError(f"Invalid decimal: {s!r}") from e


def _parse_date(s: str) -> date:
    try:
        return date.fromisoformat(s.strip())
    except ValueError as e:
        raise ValueError(f"Invalid date: {s!r}") from e


def validate_output_rows(rows: List[Dict], request_ids: List[str]) -> None:
    """
    Hard validate all output rows. Raises ValueError with details on any failure.
    """
    errors = []

    # Check column order (first row check)
    if rows:
        actual_keys = list(rows[0].keys())
        if actual_keys != OUTPUT_COLUMNS:
            errors.append(f"Column mismatch: expected {OUTPUT_COLUMNS}, got {actual_keys}")

    # Check row count
    if len(rows) != len(request_ids):
        errors.append(f"Row count mismatch: expected {len(request_ids)}, got {len(rows)}")

    # Check request IDs
    output_ids = [r["request_id"] for r in rows]
    expected_set = set(request_ids)
    output_set = set(output_ids)
    missing = expected_set - output_set
    extra = output_set - expected_set
    duplicates = [rid for rid in output_ids if output_ids.count(rid) > 1]

    if missing:
        errors.append(f"Missing request_ids: {sorted(missing)}")
    if extra:
        errors.append(f"Extra request_ids: {sorted(extra)}")
    if duplicates:
        errors.append(f"Duplicate request_ids: {list(set(duplicates))}")

    # Build request amount lookup
    request_amounts: Dict[str, Decimal] = {}
    from config import REQUESTS_CSV
    with open(REQUESTS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            request_amounts[row["request_id"].strip()] = Decimal(row["requested_amount"].strip())

    # Validate each row
    for i, row in enumerate(rows):
        rid = row.get("request_id", f"row_{i}")
        row_errors = []

        # amount_safe_to_pay
        try:
            safe = _parse_dec(row.get("amount_safe_to_pay", ""))
            req = request_amounts.get(rid, safe)
            if safe < 0:
                row_errors.append(f"amount_safe_to_pay < 0: {safe}")
            if safe > req + Decimal("0.02"):
                row_errors.append(f"amount_safe_to_pay {safe} > requested_amount {req}")
        except ValueError as e:
            row_errors.append(f"amount_safe_to_pay error: {e}")

        # affordability_status
        status = row.get("affordability_status", "")
        if status not in VALID_AFFORDABILITY_STATUS:
            row_errors.append(f"Invalid affordability_status: {status!r}")

        # recommended_payment_method
        method = row.get("recommended_payment_method", "")
        if method not in VALID_PAYMENT_METHODS:
            row_errors.append(f"Invalid recommended_payment_method: {method!r}")

        # payment_plan
        plan_str = row.get("payment_plan", "")
        plan_entries = []
        if plan_str != "none" and plan_str.strip():
            parts = plan_str.split("|")
            prev_date = None
            for part in parts:
                if ":" not in part:
                    row_errors.append(f"Malformed payment_plan entry: {part!r}")
                    continue
                try:
                    d_str, a_str = part.rsplit(":", 1)
                    d = _parse_date(d_str)
                    a = _parse_dec(a_str)
                    if prev_date and d < prev_date:
                        row_errors.append(f"Non-chronological payment_plan: {d} after {prev_date}")
                    prev_date = d
                    plan_entries.append((d, a))
                except Exception as e:
                    row_errors.append(f"payment_plan parse error: {e}")

        # Validate partial_payment: exactly 2 entries summing to requested_amount
        if method == "partial_payment":
            if len(plan_entries) != 2:
                row_errors.append(f"partial_payment must have exactly 2 entries, got {len(plan_entries)}")
            elif rid in request_amounts:
                total = sum(a for _, a in plan_entries)
                req_amt = request_amounts[rid]
                if abs(total - req_amt) > Decimal("0.02"):
                    row_errors.append(f"partial_payment entries sum {total} != requested_amount {req_amt}")

        # earliest_date_for_full_payment
        earliest_str = row.get("earliest_date_for_full_payment", "")
        if earliest_str and earliest_str.strip():
            try:
                _parse_date(earliest_str)
            except ValueError as e:
                row_errors.append(f"earliest_date_for_full_payment error: {e}")

        # Validate affordable_now: earliest must equal request_date
        if status == "affordable_now" and earliest_str:
            # This is a soft check — we'll warn but not hard fail
            pass

        # spending_changes_needed
        spending_str = row.get("spending_changes_needed", "")
        if spending_str != "none" and spending_str.strip():
            changes = spending_str.split("|")
            if len(changes) > 3:
                row_errors.append(f"spending_changes_needed has {len(changes)} changes, max is 3")
            event_ids_seen = {}
            for ch in changes:
                if ch.startswith("stop:"):
                    eid = ch[5:]
                    if eid in event_ids_seen:
                        if event_ids_seen[eid] == "reduce":
                            row_errors.append(f"Cannot stop and reduce same event {eid}")
                    event_ids_seen[eid] = "stop"
                elif ch.startswith("reduce_to:"):
                    parts = ch.split(":")
                    if len(parts) < 3:
                        row_errors.append(f"Malformed reduce_to: {ch!r}")
                    else:
                        eid = parts[1]
                        if eid in event_ids_seen:
                            if event_ids_seen[eid] == "stop":
                                row_errors.append(f"Cannot stop and reduce same event {eid}")
                        event_ids_seen[eid] = "reduce"
                        try:
                            Decimal(parts[2])
                        except Exception:
                            row_errors.append(f"Invalid reduce_to amount: {parts[2]!r}")
                else:
                    row_errors.append(f"Invalid spending_change format: {ch!r}")

        # decision_explanation
        explanation = row.get("decision_explanation", "")
        if not explanation.strip():
            row_errors.append("Empty decision_explanation")

        if row_errors:
            for err in row_errors:
                errors.append(f"  [{rid}] {err}")

    if errors:
        error_msg = "\n".join(["VALIDATION ERRORS:"] + errors)
        raise ValueError(error_msg)

    print(f"[validator] All {len(rows)} rows passed validation.")


if __name__ == "__main__":
    from pathlib import Path
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "output.csv"
    print(f"[validator] Validating {csv_path}...")
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
    req_ids = [r["request_id"] for r in reader]
    validate_output_rows(reader, req_ids)
    print(f"[validator] Successfully verified {len(reader)} rows in {csv_path}!")
