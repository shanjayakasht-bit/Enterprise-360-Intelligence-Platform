"""Generates the leads dataset, tied to existing customer accounts (expansion/upsell
pipeline) and assigned to salespeople."""

import pandas as pd
from dateutil.relativedelta import relativedelta

from .master_data import LEAD_SOURCES, LEAD_STATUSES, NP_RNG, REFERENCE_DATE, RNG, make_id, random_date

LEAD_STATUS_WEIGHTS = [0.15, 0.20, 0.20, 0.15, 0.20, 0.10]


def generate(n, customers_df, employees_df):
    salespeople = employees_df.loc[employees_df["department"] == "Sales", "employee_id"].tolist()
    customer_ids = customers_df["customer_id"].tolist()
    signup_lookup = customers_df.set_index("customer_id")["signup_date"]

    rows = []
    for i in range(1, n + 1):
        customer_id = RNG.choice(customer_ids)
        signup_date = pd.Timestamp(signup_lookup.loc[customer_id]).date()
        created_date = random_date(RNG, signup_date, REFERENCE_DATE) if signup_date < REFERENCE_DATE else REFERENCE_DATE

        status = RNG.choices(LEAD_STATUSES, weights=LEAD_STATUS_WEIGHTS, k=1)[0]
        converted = status == "Converted"
        converted_date = None
        if converted:
            converted_date = min(created_date + relativedelta(days=RNG.randint(3, 60)), REFERENCE_DATE)

        rows.append({
            "lead_id": make_id("LEAD", i),
            "customer_id": customer_id,
            "lead_source": RNG.choice(LEAD_SOURCES),
            "created_date": created_date.isoformat(),
            "assigned_salesperson_id": RNG.choice(salespeople) if salespeople else None,
            "status": status,
            "lead_score": round(max(0.0, min(100.0, NP_RNG.normal(55, 20))), 1),
            "converted_to_deal": converted,
            "converted_date": converted_date.isoformat() if converted_date else None,
        })

    return pd.DataFrame(rows)
