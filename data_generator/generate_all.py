"""Orchestrates generation of all NEXORA datasets in dependency order, writes CSVs,
and runs validation against the result. Run from the project root as:

    python -m data_generator.generate_all              (uses config.settings.SAMPLE_MODE)
    python -m data_generator.generate_all --mode sample
    python -m data_generator.generate_all --mode full
"""

import argparse
import sys
import time
from pathlib import Path

from config.settings import RANDOM_SEED, SAMPLE_MODE
from data_generator import activity, customers, deals, employees, invoices, leads, payments, projects, subscriptions, support
from data_generator.config import FULL_SIZES, SAMPLE_SIZES
from validation import validate_business_rules, validate_relationships, validate_schema

ROOT_DIR = Path(__file__).resolve().parent.parent


def _output_dir(mode):
    return ROOT_DIR / "data" / ("sample" if mode == "sample" else "raw")


def generate(mode):
    sizes = SAMPLE_SIZES if mode == "sample" else FULL_SIZES
    out_dir = _output_dir(mode)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating NEXORA '{mode}' dataset (random seed={RANDOM_SEED}) ...")
    t0 = time.time()

    employees_df = employees.generate(sizes["employees"])
    customers_base_df = customers.generate_base(sizes["customers"], employees_df)

    leads_df = leads.generate(sizes["leads"], customers_base_df, employees_df)
    deals_df = deals.generate(sizes["deals"], customers_base_df, leads_df, employees_df)
    subscriptions_df = subscriptions.generate(sizes["subscriptions"], customers_base_df, deals_df)
    projects_df = projects.generate(sizes["projects"], customers_base_df, deals_df, employees_df)
    invoices_df = invoices.generate(sizes["invoices"], customers_base_df, subscriptions_df, projects_df)
    payments_df = payments.generate(invoices_df, customers_base_df)
    support_df = support.generate(sizes["support_tickets"], customers_base_df, employees_df)
    activity_df = activity.generate(sizes["customer_activity"], customers_base_df)

    customers_df = customers.finalize(customers_base_df, activity_df, support_df, payments_df)

    tables = {
        "customers": customers_df,
        "employees": employees_df,
        "leads": leads_df,
        "deals": deals_df,
        "subscriptions": subscriptions_df,
        "projects": projects_df,
        "invoices": invoices_df,
        "payments": payments_df,
        "support_tickets": support_df,
        "customer_activity": activity_df,
    }

    for name, df in tables.items():
        df.to_csv(out_dir / f"{name}.csv", index=False)

    elapsed = time.time() - t0
    print(f"\nGenerated {sum(len(df) for df in tables.values()):,} total rows across {len(tables)} files in {elapsed:.1f}s")
    print(f"Output directory: {out_dir}\n")
    for name, df in tables.items():
        print(f"  {name:<20s} {len(df):>7,} rows")

    return tables, out_dir


def run_validation(tables, mode):
    print("\nRunning validation...")
    all_results = validate_schema.run(tables) + validate_relationships.run(tables) + validate_business_rules.run(tables)
    all_passed = validate_schema.print_summary(all_results)

    report_dir = ROOT_DIR / "data" / "validation"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"validation_report_{mode}.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("NEXORA DATA VALIDATION SUMMARY\n")
        f.write("=" * 60 + "\n")
        for r in all_results:
            f.write(f"[{'PASS' if r.passed else 'FAIL'}] {r.name}: {r.detail}\n")
        f.write("-" * 60 + "\n")
        passed = sum(1 for r in all_results if r.passed)
        f.write(f"Total checks: {len(all_results)}   Passed: {passed}   Failed: {len(all_results) - passed}\n")
    print(f"Validation report written to: {report_path}")

    return all_passed


def main():
    parser = argparse.ArgumentParser(description="Generate NEXORA synthetic datasets.")
    parser.add_argument("--mode", choices=["sample", "full"], default="sample" if SAMPLE_MODE else "full")
    args = parser.parse_args()

    tables, _ = generate(args.mode)
    all_passed = run_validation(tables, args.mode)

    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
