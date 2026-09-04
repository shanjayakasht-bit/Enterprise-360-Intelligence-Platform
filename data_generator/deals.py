"""Generates the deals dataset. A share of deals originate from converted leads
(preserving the lead -> deal link); the rest are direct sales-cycle opportunities."""

import pandas as pd
from dateutil.relativedelta import relativedelta

from . import business_rules
from .master_data import DEAL_STAGES, HISTORY_START, OPEN_DEAL_STAGES, PRODUCTS, REFERENCE_DATE, RNG, make_id

DEAL_STAGE_WEIGHTS = [0.10, 0.12, 0.15, 0.13, 0.30, 0.20]


def generate(n, customers_df, leads_df, employees_df):
    salespeople = employees_df.loc[employees_df["department"] == "Sales", "employee_id"].tolist()
    customer_lookup = customers_df.set_index("customer_id")
    customer_ids = customer_lookup.index.tolist()

    convertible_leads = leads_df[leads_df["converted_to_deal"]].to_dict("records")
    RNG.shuffle(convertible_leads)
    lead_idx = 0

    rows = []
    for i in range(1, n + 1):
        lead_id = None
        if lead_idx < len(convertible_leads):
            lead = convertible_leads[lead_idx]
            lead_idx += 1
            customer_id = lead["customer_id"]
            lead_id = lead["lead_id"]
            created_date = pd.Timestamp(lead["converted_date"]).date()
        else:
            customer_id = RNG.choice(customer_ids)
            signup_date = pd.Timestamp(customer_lookup.loc[customer_id, "signup_date"]).date()
            created_date = pd.Timestamp(
                max(signup_date, HISTORY_START)
                + relativedelta(days=RNG.randint(0, max((REFERENCE_DATE - max(signup_date, HISTORY_START)).days, 0)))
            ).date()

        segment = customer_lookup.loc[customer_id, "segment"]
        region = customer_lookup.loc[customer_id, "region"]

        stage = RNG.choices(DEAL_STAGES, weights=DEAL_STAGE_WEIGHTS, k=1)[0]
        is_open = stage in OPEN_DEAL_STAGES
        expected_close = created_date + relativedelta(days=RNG.randint(20, 120))

        if is_open:
            close_date = min(expected_close, REFERENCE_DATE + relativedelta(days=90))
            is_won = None
        else:
            close_date = min(created_date + relativedelta(days=RNG.randint(15, 150)), REFERENCE_DATE)
            is_won = stage == "Closed Won"

        base_value = {"Enterprise": 90000, "Mid-Market": 32000, "SMB": 9000, "Startup": 4000}[segment]
        deal_value = business_rules.priced_amount(base_value, region, segment, created_date.month)
        discount = business_rules.discount_pct(segment, deal_value)

        rows.append({
            "deal_id": make_id("DEAL", i),
            "customer_id": customer_id,
            "lead_id": lead_id,
            "sales_rep_id": RNG.choice(salespeople) if salespeople else None,
            "product": RNG.choice(PRODUCTS),
            "deal_stage": stage,
            "is_won": is_won,
            "deal_value": deal_value,
            "discount_pct": discount,
            "created_date": created_date.isoformat(),
            "close_date": close_date.isoformat(),
            "region": region,
            "segment": segment,
        })

    return pd.DataFrame(rows)
