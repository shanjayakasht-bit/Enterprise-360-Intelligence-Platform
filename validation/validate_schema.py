"""Validates dataset schemas: primary key uniqueness, nulls in mandatory fields,
and numeric range constraints. Run standalone as:

    python -m validation.validate_schema [--data-dir data/sample|data/raw]

Defaults to data/raw if it has been generated, else data/sample.
"""

from collections import namedtuple

import pandas as pd

ValidationResult = namedtuple("ValidationResult", ["name", "passed", "detail"])

PRIMARY_KEYS = {
    "customers": "customer_id",
    "employees": "employee_id",
    "leads": "lead_id",
    "deals": "deal_id",
    "subscriptions": "subscription_id",
    "projects": "project_id",
    "invoices": "invoice_id",
    "payments": "payment_id",
    "support_tickets": "ticket_id",
    "customer_activity": "activity_id",
}

MANDATORY_FIELDS = {
    "customers": ["customer_id", "company_name", "segment", "region", "signup_date", "renewal_date"],
    "employees": ["employee_id", "full_name", "department", "hire_date"],
    "leads": ["lead_id", "customer_id", "created_date", "status"],
    "deals": ["deal_id", "customer_id", "deal_stage", "created_date"],
    "subscriptions": ["subscription_id", "customer_id", "plan", "start_date"],
    "projects": ["project_id", "customer_id", "start_date", "status"],
    "invoices": ["invoice_id", "customer_id", "invoice_date", "due_date", "total_amount"],
    "payments": ["payment_id", "invoice_id", "customer_id", "payment_date", "amount_paid"],
    "support_tickets": ["ticket_id", "customer_id", "created_date", "status"],
    "customer_activity": ["activity_id", "customer_id", "activity_date"],
}

RANGE_CONSTRAINTS = {
    "customers": [
        ("product_usage_score", 0, 100), ("engagement_score", 0, 100),
        ("satisfaction_score", 0, 100), ("churn_risk_score", 0, 100),
    ],
    "leads": [("lead_score", 0, 100)],
    "deals": [("discount_pct", 0, 1)],
    "projects": [("completion_pct", 0, 100), ("project_risk_score", 0, 100)],
    "support_tickets": [("satisfaction_rating", 1, 5)],
}


def _check_primary_key(name, df):
    pk = PRIMARY_KEYS[name]
    n_nulls = int(df[pk].isna().sum())
    n_dupes = int(df[pk].duplicated().sum())
    passed = n_nulls == 0 and n_dupes == 0
    return ValidationResult(
        f"{name}.{pk} primary key", passed,
        f"{len(df)} rows, {n_nulls} null keys, {n_dupes} duplicate keys",
    )


def _check_mandatory_fields(name, df):
    fields = MANDATORY_FIELDS[name]
    null_counts = {f: int(df[f].isna().sum()) for f in fields}
    total_nulls = sum(null_counts.values())
    passed = total_nulls == 0
    detail = "no nulls in mandatory fields" if passed else f"nulls found: {null_counts}"
    return ValidationResult(f"{name} mandatory fields", passed, detail)


def _check_ranges(name, df):
    violations = []
    for column, low, high in RANGE_CONSTRAINTS.get(name, []):
        series = df[column].dropna()
        out_of_range = int(((series < low) | (series > high)).sum())
        if out_of_range:
            violations.append(f"{column} ({out_of_range} rows outside [{low}, {high}])")
    passed = len(violations) == 0
    detail = "within expected ranges" if passed else "; ".join(violations)
    return ValidationResult(f"{name} range constraints", passed, detail)


def run(tables):
    results = []
    for name, df in tables.items():
        results.append(_check_primary_key(name, df))
        results.append(_check_mandatory_fields(name, df))
        if name in RANGE_CONSTRAINTS:
            results.append(_check_ranges(name, df))
    return results


def print_summary(results, title="NEXORA DATA VALIDATION SUMMARY"):
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)
    for r in results:
        print(f"[{'PASS' if r.passed else 'FAIL'}] {r.name}: {r.detail}")
    print("-" * 60)
    print(f"Total checks: {len(results)}   Passed: {len(passed)}   Failed: {len(failed)}")
    print("=" * 60)
    return len(failed) == 0


def _load_tables(data_dir):
    return {name: pd.read_csv(data_dir / f"{name}.csv") for name in PRIMARY_KEYS}


def default_data_dir(root_dir):
    """Auto-selects the dataset to validate: the full data/raw dataset once it has
    been generated, otherwise falls back to data/sample so sample-mode validation
    keeps working unchanged. An explicit --data-dir always overrides this."""
    raw_dir = root_dir / "data" / "raw"
    if (raw_dir / "customers.csv").exists():
        return raw_dir
    return root_dir / "data" / "sample"


if __name__ == "__main__":
    import argparse
    import sys
    from pathlib import Path

    ROOT_DIR = Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None, help="Defaults to data/raw if generated, else data/sample")
    args = parser.parse_args()

    data_dir = ROOT_DIR / args.data_dir if args.data_dir else default_data_dir(ROOT_DIR)
    tables = _load_tables(data_dir)
    all_passed = print_summary(run(tables), title="NEXORA SCHEMA VALIDATION")
    sys.exit(0 if all_passed else 1)
