"""Generates the projects dataset, with project risk driven by completion percentage,
deadline proximity, budget utilization, and cost overrun via business_rules."""

import pandas as pd
from dateutil.relativedelta import relativedelta

from . import business_rules
from .master_data import NP_RNG, PROJECT_STATUSES, PROJECT_TYPES, REFERENCE_DATE, RNG, make_id

PROJECT_STATUS_WEIGHTS = [0.12, 0.28, 0.35, 0.08, 0.10, 0.07]


def generate(n, customers_df, deals_df, employees_df):
    project_managers = employees_df.loc[employees_df["department"] == "Project Management", "employee_id"].tolist()
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
                pd.Timestamp(deal["close_date"]).date() + relativedelta(days=RNG.randint(5, 20)), REFERENCE_DATE
            )
            region = deal["region"]
            segment = deal["segment"]
        else:
            customer_id = RNG.choice(customer_ids)
            customer = customer_lookup.loc[customer_id]
            start_date = pd.Timestamp(customer["contract_start_date"]).date()
            region = customer["region"]
            segment = customer["segment"]

        duration_weeks = RNG.randint(4, 40)
        planned_end_date = start_date + relativedelta(weeks=duration_weeks)
        status = RNG.choices(PROJECT_STATUSES, weights=PROJECT_STATUS_WEIGHTS, k=1)[0]
        planned_duration_days = max((planned_end_date - start_date).days, 1)

        if status == "Completed":
            completion_pct = 100.0
            # Most completed projects land close to on time; a minority run late.
            low = int(planned_duration_days * 0.80)
            high = max(int(planned_duration_days * 1.15), low + 1)
            actual_end_date = min(start_date + relativedelta(days=RNG.randint(low, high)), REFERENCE_DATE)
        elif status == "Cancelled":
            completion_pct = round(RNG.uniform(5, 70), 1)
            low = int(planned_duration_days * 0.2)
            high = max(int(planned_duration_days * 0.9), low + 1)
            actual_end_date = min(start_date + relativedelta(days=RNG.randint(low, high)), REFERENCE_DATE)
        elif status == "Delayed":
            completion_pct = round(RNG.uniform(20, 75), 1)
            actual_end_date = None
        elif status == "On Hold":
            completion_pct = round(RNG.uniform(10, 60), 1)
            actual_end_date = None
        elif status == "Planned":
            completion_pct = 0.0
            actual_end_date = None
        else:  # In Progress
            elapsed = max((REFERENCE_DATE - start_date).days, 0)
            completion_pct = round(max(0.0, min(100.0, elapsed / planned_duration_days * 100 * RNG.uniform(0.6, 1.1))), 1)
            actual_end_date = None

        base_budget = {"Enterprise": 250000, "Mid-Market": 90000, "SMB": 30000, "Startup": 12000}[segment]
        budget = business_rules.priced_amount(base_budget, region, segment, start_date.month, noise=0.12)

        cost_variance = float(NP_RNG.normal(1.0, 0.15))
        if status == "Delayed":
            cost_variance += RNG.uniform(0.05, 0.25)
        progress_fraction = 1.0 if status == "Completed" else completion_pct / 100
        actual_cost = round(max(0.0, budget * cost_variance * progress_fraction), 2)

        budget_utilization_pct = round((actual_cost / budget * 100) if budget else 0.0, 1)
        cost_overrun_pct = round(max(0.0, (actual_cost - budget) / budget * 100) if budget else 0.0, 1)

        reference_date = actual_end_date if actual_end_date else REFERENCE_DATE
        days_to_deadline = (planned_end_date - reference_date).days

        risk_score, risk_category = business_rules.project_risk_score(
            completion_pct, days_to_deadline, budget_utilization_pct, cost_overrun_pct,
        )

        rows.append({
            "project_id": make_id("PROJ", i),
            "customer_id": customer_id,
            "deal_id": deal_id,
            "project_manager_id": RNG.choice(project_managers) if project_managers else None,
            "project_type": RNG.choice(PROJECT_TYPES),
            "start_date": start_date.isoformat(),
            "planned_end_date": planned_end_date.isoformat(),
            "actual_end_date": actual_end_date.isoformat() if actual_end_date else None,
            "status": status,
            "completion_pct": completion_pct,
            "budget": budget,
            "actual_cost": actual_cost,
            "budget_utilization_pct": budget_utilization_pct,
            "cost_overrun_pct": cost_overrun_pct,
            "project_risk_score": risk_score,
            "project_risk_category": risk_category,
        })

    return pd.DataFrame(rows)
