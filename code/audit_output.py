"""
audit_output.py — Strict audit of output.csv against all AGENTS.md rules.
"""
import csv
from decimal import Decimal
from datetime import date

def run_audit(path="output.csv"):
    requests = {r["request_id"]: r for r in csv.DictReader(open("dataset/requests.csv", encoding="utf-8"))}
    outputs = {r["request_id"]: r for r in csv.DictReader(open(path, encoding="utf-8"))}

    print(f"Auditing {path} ({len(outputs)} rows)...")
    assert len(requests) == len(outputs) == 250, f"Expected 250 rows, got {len(outputs)}"

    status_dist = {}
    method_dist = {}
    errors = []

    for rid, out in outputs.items():
        req = requests[rid]
        req_amt = Decimal(req["requested_amount"])
        req_date = date.fromisoformat(req["request_date"])
        desired_date = date.fromisoformat(req["desired_completion_date"])

        safe_amt = Decimal(out["amount_safe_to_pay"])
        status = out["affordability_status"]
        method = out["recommended_payment_method"]
        plan = out["payment_plan"]
        earliest_date = out["earliest_date_for_full_payment"]
        changes = out["spending_changes_needed"]
        exp = out["decision_explanation"]

        status_dist[status] = status_dist.get(status, 0) + 1
        method_dist[method] = method_dist.get(method, 0) + 1

        # Check bounds
        if not (Decimal(0) <= safe_amt <= req_amt):
            errors.append(f"{rid}: safe_amt {safe_amt} not in [0, {req_amt}]")

        # Check consistency with status
        if status == "affordable_now":
            if method != "full_payment":
                errors.append(f"{rid}: affordable_now must have full_payment, got {method}")
            if earliest_date != req["request_date"]:
                errors.append(f"{rid}: affordable_now earliest_date {earliest_date} != request_date {req['request_date']}")

        elif status == "affordable_later":
            if method != "wait":
                errors.append(f"{rid}: affordable_later must have wait, got {method}")
            if not earliest_date:
                errors.append(f"{rid}: affordable_later missing earliest_date")
            else:
                ed = date.fromisoformat(earliest_date)
                if ed > desired_date:
                    errors.append(f"{rid}: earliest_date {ed} after deadline {desired_date}")

        elif status == "not_affordable":
            if method != "not_recommended":
                errors.append(f"{rid}: not_affordable must have not_recommended, got {method}")
            if plan != "none":
                errors.append(f"{rid}: not_affordable plan must be none, got {plan}")
            if earliest_date != "":
                errors.append(f"{rid}: not_affordable earliest_date must be empty, got {earliest_date}")

        elif status == "affordable_with_plan":
            if method not in ("installments", "partial_payment", "full_payment"):
                errors.append(f"{rid}: affordable_with_plan invalid method {method}")
            if plan == "none":
                errors.append(f"{rid}: affordable_with_plan must have payment_plan")

        # Check explanation
        if not exp.strip():
            errors.append(f"{rid}: empty decision_explanation")

    if errors:
        print(f"FAILED: {len(errors)} errors found:")
        for e in errors[:10]:
            print(f"  {e}")
        return False
    else:
        print("ALL 250 ROWS PASSED 100% HARD CONTRACT AUDIT!")
        print(f"Affordability distribution: {status_dist}")
        print(f"Payment method distribution: {method_dist}")
        return True

if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "output.csv"
    success = run_audit(target)
    if not success:
        sys.exit(1)
