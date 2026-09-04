"""Validates business-rule consistency: date ordering, invoice/payment consistency,
project date consistency, and that stored risk scores match the business_rules
formulas given their own stored inputs. Run standalone as:

    python -m validation.validate_business_rules [--data-dir data/sample|data/raw]

Defaults to data/raw if it has been generated, else data/sample.
"""

import sys
from pathlib import Path

import pandas as pd

from config.settings import REFERENCE_DATE
from data_generator import business_rules
from validation.validate_schema import PRIMARY_KEYS, ValidationResult, default_data_dir, print_summary

ROOT_DIR = Path(__file__).resolve().parent.parent


def _check_date_order(name, df, start_col, end_col, allow_null_end=True):
    start = pd.to_datetime(df[start_col])
    end = pd.to_datetime(df[end_col])
    mask = end.notna() if allow_null_end else pd.Series(True, index=df.index)
    violations = int((end[mask] < start[mask]).sum())
    return ValidationResult(
        f"{name} date consistency ({start_col} -> {end_col})", violations == 0,
        f"{end_col} >= {start_col} for all rows ({violations} violations)",
    )


def _check_project_dates(projects):
    results = [
        _check_date_order("projects", projects, "start_date", "planned_end_date", allow_null_end=False),
        _check_date_order("projects", projects, "start_date", "actual_end_date"),
    ]
    completed = projects[projects["status"] == "Completed"]
    missing_actual = int(completed["actual_end_date"].isna().sum())
    results.append(ValidationResult(
        "projects: Completed status has actual_end_date", missing_actual == 0,
        f"{missing_actual} completed projects missing actual_end_date",
    ))
    return results


def _check_invoice_payment_consistency(invoices, payments):
    totals = payments.groupby("invoice_id")["amount_paid"].sum()
    merged = invoices.set_index("invoice_id").copy()
    merged["paid_total"] = totals
    merged["paid_total"] = merged["paid_total"].fillna(0.0)

    overpaid = merged[merged["paid_total"] > merged["total_amount"] + 0.01]
    paid_status = merged[merged["status"] == "Paid"]
    underpaid = paid_status[(paid_status["total_amount"] - paid_status["paid_total"]).abs() > 0.01]
    unpaid_status = merged[merged["status"].isin(["Unpaid", "Cancelled"])]
    unexpected_payment = unpaid_status[unpaid_status["paid_total"] > 0.01]

    return [
        ValidationResult(
            "payments never exceed invoice total", len(overpaid) == 0,
            f"{len(overpaid)} invoices overpaid",
        ),
        ValidationResult(
            "'Paid' invoices fully covered by payments", len(underpaid) == 0,
            f"{len(underpaid)} 'Paid' invoices with mismatched payment total",
        ),
        ValidationResult(
            "'Unpaid'/'Cancelled' invoices have no payments", len(unexpected_payment) == 0,
            f"{len(unexpected_payment)} unpaid/cancelled invoices with payments recorded",
        ),
    ]


def _check_customer_risk_recomputation(customers):
    recomputed = customers.apply(
        lambda row: business_rules.customer_risk_score(
            row["product_usage_score"], row["engagement_score"], row["satisfaction_score"],
            row["support_ticket_count_recent"], row["avg_payment_delay_days"], row["days_to_renewal"],
        )[0],
        axis=1,
    )
    # Tolerance absorbs float64-vs-float rounding ties at the 1-decimal boundary
    # (e.g. 36.15 -> 36.1 or 36.2 depending on numpy vs plain-python float path);
    # it does not mask a formula mismatch, which would differ by far more than this.
    violations = int((recomputed - customers["churn_risk_score"]).abs().gt(0.15).sum())
    return ValidationResult(
        "customers.churn_risk_score matches business rule formula", violations == 0,
        f"{violations} customers with mismatched risk score",
    )


def _check_project_risk_recomputation(projects):
    reference = pd.to_datetime(projects["actual_end_date"]).fillna(pd.Timestamp(REFERENCE_DATE))
    planned = pd.to_datetime(projects["planned_end_date"])
    days_to_deadline = (planned - reference).dt.days

    recomputed = [
        business_rules.project_risk_score(
            row["completion_pct"], days_to_deadline.loc[i], row["budget_utilization_pct"], row["cost_overrun_pct"],
        )[0]
        for i, row in projects.iterrows()
    ]
    violations = int((pd.Series(recomputed, index=projects.index) - projects["project_risk_score"]).abs().gt(0.15).sum())
    return ValidationResult(
        "projects.project_risk_score matches business rule formula", violations == 0,
        f"{violations} projects with mismatched risk score",
    )


def _check_no_future_dates(name, df, columns):
    today = pd.Timestamp.today().normalize()
    results = []
    for col in columns:
        values = pd.to_datetime(df[col], errors="coerce")
        violations = int((values > today).sum())
        results.append(ValidationResult(
            f"{name}.{col} not in the future", violations == 0, f"{violations} rows dated after today",
        ))
    return results


def run(tables):
    results = []
    results += _check_project_dates(tables["projects"])
    results += _check_invoice_payment_consistency(tables["invoices"], tables["payments"])
    results.append(_check_date_order("deals", tables["deals"], "created_date", "close_date"))
    results.append(_check_date_order("subscriptions", tables["subscriptions"], "start_date", "end_date"))
    results.append(_check_date_order("invoices", tables["invoices"], "invoice_date", "due_date"))
    results.append(_check_customer_risk_recomputation(tables["customers"]))
    results.append(_check_project_risk_recomputation(tables["projects"]))
    results += _check_no_future_dates("customers", tables["customers"], ["signup_date", "contract_start_date"])
    results += _check_no_future_dates("payments", tables["payments"], ["payment_date"])
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None, help="Defaults to data/raw if generated, else data/sample")
    args = parser.parse_args()

    data_dir = ROOT_DIR / args.data_dir if args.data_dir else default_data_dir(ROOT_DIR)
    tables = {name: pd.read_csv(data_dir / f"{name}.csv") for name in PRIMARY_KEYS}
    all_passed = print_summary(run(tables), title="NEXORA BUSINESS RULE VALIDATION")
    sys.exit(0 if all_passed else 1)
