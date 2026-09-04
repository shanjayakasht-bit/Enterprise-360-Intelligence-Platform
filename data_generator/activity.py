"""Generates the customer_activity dataset. Volume and engagement points are biased
by each customer's usage/engagement propensity, which customers.finalize later rolls
back up into product_usage_score and engagement_score."""

import pandas as pd
from dateutil.relativedelta import relativedelta

from .master_data import ACTIVITY_TYPES, HISTORY_START, NP_RNG, REFERENCE_DATE, RNG, make_id


def generate(n, customers_df):
    weights = (0.3 + customers_df["_usage_propensity"] + customers_df["_engagement_propensity"]).tolist()
    customer_ids = customers_df["customer_id"].tolist()
    engagement_lookup = customers_df.set_index("customer_id")["_engagement_propensity"]
    contract_start_lookup = customers_df.set_index("customer_id")["contract_start_date"]

    rows = []
    for i in range(1, n + 1):
        customer_id = RNG.choices(customer_ids, weights=weights, k=1)[0]
        contract_start = pd.Timestamp(contract_start_lookup.loc[customer_id]).date()
        window_start = max(contract_start, HISTORY_START)
        span_days = max((REFERENCE_DATE - window_start).days, 0)
        activity_date = window_start + relativedelta(days=RNG.randint(0, span_days))

        propensity = float(engagement_lookup.loc[customer_id])
        duration_minutes = round(max(1.0, NP_RNG.normal(8 + propensity * 25, 6)), 1)
        engagement_points = round(duration_minutes * (0.8 + propensity), 1)

        rows.append({
            "activity_id": make_id("ACT", i),
            "customer_id": customer_id,
            "activity_date": activity_date.isoformat(),
            "activity_type": RNG.choice(ACTIVITY_TYPES),
            "duration_minutes": duration_minutes,
            "engagement_points": engagement_points,
        })

    return pd.DataFrame(rows)
