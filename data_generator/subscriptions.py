"""Generates the subscriptions dataset, preferentially attached to Closed Won deals."""

import pandas as pd
from dateutil.relativedelta import relativedelta

from . import business_rules
from .master_data import (
    BILLING_CYCLES,
    PLAN_BASE_MRR,
    REFERENCE_DATE,
    RNG,
    SEGMENT_PLAN_WEIGHTS,
    SUBSCRIPTION_PLANS,
    SUBSCRIPTION_STATUSES,
    make_id,
    weighted_choice,
)


def generate(n, customers_df, deals_df):
    customer_lookup = customers_df.set_index("customer_id")
    customer_ids = customer_lookup.index.tolist()

    won_deals = deals_df[deals_df["is_won"] == True].to_dict("records")  # noqa: E712
    RNG.shuffle(won_deals)
    deal_idx = 0

    rows = []
    for i in range(1, n + 1):
        deal_id = None
        if deal_idx < len(won_deals):
            deal = won_deals[deal_idx]
            deal_idx += 1
            customer_id = deal["customer_id"]
            deal_id = deal["deal_id"]
            start_date = min(
                pd.Timestamp(deal["close_date"]).date() + relativedelta(days=RNG.randint(1, 10)), REFERENCE_DATE
            )
            segment = deal["segment"]
            region = deal["region"]
        else:
            customer_id = RNG.choice(customer_ids)
            customer = customer_lookup.loc[customer_id]
            start_date = pd.Timestamp(customer["contract_start_date"]).date()
            segment = customer["segment"]
            region = customer["region"]

        plan = weighted_choice(RNG, SUBSCRIPTION_PLANS, SEGMENT_PLAN_WEIGHTS[segment])
        billing_cycle = RNG.choice(BILLING_CYCLES)
        status = RNG.choice(SUBSCRIPTION_STATUSES)
        term_years = RNG.choice([1, 2]) if status == "Expired" else 1
        end_date = start_date + relativedelta(years=term_years)

        mrr = business_rules.priced_amount(PLAN_BASE_MRR[plan], region, segment, start_date.month, noise=0.10)

        rows.append({
            "subscription_id": make_id("SUB", i),
            "customer_id": customer_id,
            "deal_id": deal_id,
            "plan": plan,
            "billing_cycle": billing_cycle,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "mrr": mrr,
            "status": status,
            "auto_renew": bool(status == "Active" and RNG.random() > 0.15),
        })

    return pd.DataFrame(rows)
