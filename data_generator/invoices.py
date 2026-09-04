"""Generates the invoices dataset, billed against subscriptions, projects, or
(occasionally) standalone, always tied to a valid customer."""

import pandas as pd
from dateutil.relativedelta import relativedelta

from . import business_rules
from .master_data import INVOICE_STATUSES, REFERENCE_DATE, RNG, make_id

# Paid, Unpaid, Overdue, Partially Paid, Cancelled
INVOICE_STATUS_WEIGHTS = [0.58, 0.10, 0.13, 0.14, 0.05]


def generate(n, customers_df, subscriptions_df, projects_df):
    customer_lookup = customers_df.set_index("customer_id")
    customer_ids = customer_lookup.index.tolist()

    sub_sources = subscriptions_df.to_dict("records")
    proj_sources = projects_df.to_dict("records")
    RNG.shuffle(sub_sources)
    RNG.shuffle(proj_sources)

    rows = []
    for i in range(1, n + 1):
        roll = RNG.random()
        subscription_id = None
        project_id = None

        if roll < 0.65 and sub_sources:
            source = sub_sources[RNG.randrange(len(sub_sources))]
            customer_id = source["customer_id"]
            subscription_id = source["subscription_id"]
            base_amount = source["mrr"] * (12 if source["billing_cycle"] == "Annual" else 1)
            earliest = pd.Timestamp(source["start_date"]).date()
        elif roll < 0.90 and proj_sources:
            source = proj_sources[RNG.randrange(len(proj_sources))]
            customer_id = source["customer_id"]
            project_id = source["project_id"]
            base_amount = source["budget"] * RNG.uniform(0.15, 0.4)
            earliest = pd.Timestamp(source["start_date"]).date()
        else:
            customer_id = RNG.choice(customer_ids)
            customer = customer_lookup.loc[customer_id]
            earliest = pd.Timestamp(customer["contract_start_date"]).date()
            base_amount = {"Enterprise": 15000, "Mid-Market": 6000, "SMB": 2000, "Startup": 800}[customer["segment"]]

        region = customer_lookup.loc[customer_id, "region"]
        segment = customer_lookup.loc[customer_id, "segment"]

        earliest = min(earliest, REFERENCE_DATE)
        span_days = max((REFERENCE_DATE - earliest).days, 0)
        invoice_date = earliest + relativedelta(days=RNG.randint(0, span_days))
        due_date = invoice_date + relativedelta(days=RNG.choice([15, 30, 30, 45, 60]))

        amount = business_rules.priced_amount(base_amount, region, segment, invoice_date.month, noise=0.06)

        status = RNG.choices(INVOICE_STATUSES, weights=INVOICE_STATUS_WEIGHTS, k=1)[0]
        if due_date >= REFERENCE_DATE and status == "Overdue":
            status = "Unpaid"

        tax = 0.0
        total_amount = round(amount + tax, 2)

        rows.append({
            "invoice_id": make_id("INV", i),
            "customer_id": customer_id,
            "subscription_id": subscription_id,
            "project_id": project_id,
            "invoice_date": invoice_date.isoformat(),
            "due_date": due_date.isoformat(),
            "amount": amount,
            "tax": tax,
            "total_amount": total_amount,
            "status": status,
        })

    return pd.DataFrame(rows)
