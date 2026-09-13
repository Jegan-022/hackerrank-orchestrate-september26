#!/usr/bin/env python3
"""Compare generated sample output against expected values."""
import csv
import os
from pathlib import Path

BASE = Path(__file__).parent.parent
SAMPLE_EXPECTED = BASE / "dataset" / "sample_requests.csv"
SAMPLE_GENERATED = BASE / "output_sample.csv"

expected_fields = [
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
]

with open(SAMPLE_EXPECTED) as f:
    expected = {r["request_id"]: r for r in csv.DictReader(f)}

with open(SAMPLE_GENERATED) as f:
    generated = {r["request_id"]: r for r in csv.DictReader(f)}

print(f"Expected: {len(expected)} rows | Generated: {len(generated)} rows\n")

matches = 0
mismatches = 0

for rid in sorted(expected.keys()):
    exp = expected[rid]
    gen = generated.get(rid)
    if gen is None:
        print(f"MISSING: {rid}")
        mismatches += 1
        continue
    
    row_match = True
    diffs = []
    for field in expected_fields:
        ev = exp.get(field, "").strip()
        gv = gen.get(field, "").strip()
        
        # Normalize amounts for comparison
        if field == "amount_safe_to_pay":
            try:
                from decimal import Decimal
                ev_d = Decimal(ev) if ev else None
                gv_d = Decimal(gv) if gv else None
                if ev_d is not None and gv_d is not None:
                    diff = abs(ev_d - gv_d)
                    if diff > Decimal("1.0"):  # Allow 1 unit tolerance
                        diffs.append(f"  {field}: expected={ev} got={gv} (diff={diff})")
                        row_match = False
                    continue
            except Exception:
                pass
        
        if ev != gv:
            diffs.append(f"  {field}:\n    expected: {ev}\n    got:      {gv}")
            row_match = False
    
    if row_match:
        matches += 1
        print(f"  PASS: {rid} ({exp['affordability_status']}, {exp['recommended_payment_method']})")
    else:
        mismatches += 1
        print(f"FAIL: {rid} ({exp['affordability_status']}, {exp['recommended_payment_method']})")
        for d in diffs:
            print(d)

print(f"\n=== SCORE: {matches}/{len(expected)} correct ({100*matches/len(expected):.1f}%) ===")
