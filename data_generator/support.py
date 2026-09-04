"""Generates the support_tickets dataset. Customers with lower satisfaction/usage
propensity file more tickets, skew toward higher priority, and rate resolutions
lower -- the signal customers.finalize later aggregates into churn risk."""

import pandas as pd
from dateutil.relativedelta import relativedelta

from .master_data import (
    HISTORY_START,
    NP_RNG,
    REFERENCE_DATE,
    RNG,
    SUPPORT_CATEGORIES,
    SUPPORT_CHANNELS,
    SUPPORT_PRIORITIES,
    SUPPORT_STATUSES,
    make_id,
)

STATUS_WEIGHTS = [0.10, 0.15, 0.40, 0.30, 0.05]
SLA_HOURS = {"Critical": 8, "High": 24, "Medium": 72, "Low": 120}


def generate(n, customers_df, employees_df):
    agents = employees_df.loc[employees_df["department"] == "Customer Support", "employee_id"].tolist()

    weights = (2.2 - customers_df["_satisfaction_propensity"] - 0.6 * customers_df["_usage_propensity"]).clip(lower=0.2)
    customer_ids = customers_df["customer_id"].tolist()
    customer_weights = weights.tolist()
    satisfaction_lookup = customers_df.set_index("customer_id")["_satisfaction_propensity"]
    contract_start_lookup = customers_df.set_index("customer_id")["contract_start_date"]

    rows = []
    for i in range(1, n + 1):
        customer_id = RNG.choices(customer_ids, weights=customer_weights, k=1)[0]
        contract_start = pd.Timestamp(contract_start_lookup.loc[customer_id]).date()
        window_start = max(contract_start, HISTORY_START)
        span_days = max((REFERENCE_DATE - window_start).days, 0)
        created_date = window_start + relativedelta(days=RNG.randint(0, span_days))

        propensity = float(satisfaction_lookup.loc[customer_id])
        priority_weights = [0.35, 0.35, 0.20, 0.10] if propensity > 0.5 else [0.15, 0.30, 0.35, 0.20]
        priority = RNG.choices(SUPPORT_PRIORITIES, weights=priority_weights, k=1)[0]
        status = RNG.choices(SUPPORT_STATUSES, weights=STATUS_WEIGHTS, k=1)[0]

        resolution_date = None
        resolution_time_hours = None
        satisfaction_rating = None
        if status in ("Resolved", "Closed"):
            sla = SLA_HOURS[priority]
            resolution_time_hours = round(max(0.5, NP_RNG.normal(sla * (1.3 - propensity * 0.5), sla * 0.3)), 1)
            days_to_resolve = max(1, round(resolution_time_hours / 24))
            resolution_date = min(created_date + relativedelta(days=days_to_resolve), REFERENCE_DATE)
            base_rating = 2.4 + propensity * 2.6
            satisfaction_rating = int(round(max(1, min(5, NP_RNG.normal(base_rating, 0.8)))))

        rows.append({
            "ticket_id": make_id("TCKT", i),
            "customer_id": customer_id,
            "agent_id": RNG.choice(agents) if agents else None,
            "category": RNG.choice(SUPPORT_CATEGORIES),
            "priority": priority,
            "channel": RNG.choice(SUPPORT_CHANNELS),
            "status": status,
            "created_date": created_date.isoformat(),
            "resolution_date": resolution_date.isoformat() if resolution_date else None,
            "resolution_time_hours": resolution_time_hours,
            "satisfaction_rating": satisfaction_rating,
        })

    return pd.DataFrame(rows)
