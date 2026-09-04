"""Validates foreign key integrity between related datasets. Run standalone as:

    python -m validation.validate_relationships [--data-dir data/sample|data/raw]

Defaults to data/raw if it has been generated, else data/sample.
"""

from validation.validate_schema import PRIMARY_KEYS, ValidationResult, default_data_dir, print_summary

FOREIGN_KEYS = [
    ("leads", "customer_id", "customers", "customer_id"),
    ("leads", "assigned_salesperson_id", "employees", "employee_id"),
    ("deals", "customer_id", "customers", "customer_id"),
    ("deals", "sales_rep_id", "employees", "employee_id"),
    ("deals", "lead_id", "leads", "lead_id"),
    ("subscriptions", "customer_id", "customers", "customer_id"),
    ("subscriptions", "deal_id", "deals", "deal_id"),
    ("projects", "customer_id", "customers", "customer_id"),
    ("projects", "project_manager_id", "employees", "employee_id"),
    ("projects", "deal_id", "deals", "deal_id"),
    ("invoices", "customer_id", "customers", "customer_id"),
    ("invoices", "subscription_id", "subscriptions", "subscription_id"),
    ("invoices", "project_id", "projects", "project_id"),
    ("payments", "invoice_id", "invoices", "invoice_id"),
    ("payments", "customer_id", "customers", "customer_id"),
    ("support_tickets", "customer_id", "customers", "customer_id"),
    ("support_tickets", "agent_id", "employees", "employee_id"),
    ("customer_activity", "customer_id", "customers", "customer_id"),
    ("customers", "account_manager_id", "employees", "employee_id"),
    ("employees", "manager_id", "employees", "employee_id"),
]


def _check_fk(tables, child, child_col, parent, parent_col):
    child_df = tables[child]
    parent_ids = set(tables[parent][parent_col].dropna())
    values = child_df[child_col].dropna()
    orphans = int((~values.isin(parent_ids)).sum())
    passed = orphans == 0
    return ValidationResult(
        f"{child}.{child_col} -> {parent}.{parent_col}", passed,
        f"{len(values)} non-null references checked, {orphans} orphaned",
    )


def _check_invoice_linkage(tables):
    invoices = tables["invoices"]
    unlinked = int((invoices["subscription_id"].isna() & invoices["project_id"].isna()).sum())
    total = len(invoices)
    return ValidationResult(
        "invoices linkage to subscription/project", True,
        f"{total - unlinked}/{total} invoices linked to a subscription or project (standalone invoices allowed)",
    )


def run(tables):
    results = [_check_fk(tables, *fk) for fk in FOREIGN_KEYS]
    results.append(_check_invoice_linkage(tables))
    return results


if __name__ == "__main__":
    import argparse
    import sys
    from pathlib import Path

    import pandas as pd

    ROOT_DIR = Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None, help="Defaults to data/raw if generated, else data/sample")
    args = parser.parse_args()

    data_dir = ROOT_DIR / args.data_dir if args.data_dir else default_data_dir(ROOT_DIR)
    tables = {name: pd.read_csv(data_dir / f"{name}.csv") for name in PRIMARY_KEYS}
    all_passed = print_summary(run(tables), title="NEXORA RELATIONSHIP VALIDATION")
    sys.exit(0 if all_passed else 1)
