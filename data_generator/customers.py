"""Generates the customers dataset.

Customers are generated in two passes. ``generate_base`` creates the account
record plus latent propensity scores (usage, engagement, satisfaction, payment
reliability) that bias how downstream tables (activity, support, payments) are
generated for that customer. ``finalize`` is called after every dependent table
exists; it aggregates real behavior back onto the customer record and computes
the churn risk score from business_rules, so risk genuinely reflects usage,
engagement, satisfaction, support volume, payment delay, and renewal proximity.
"""

import pandas as pd
from dateutil.relativedelta import relativedelta

from . import business_rules
from .master_data import (
    FAKE,
    HISTORY_START,
    INDUSTRIES,
    NP_RNG,
    RECENT_WINDOW_DAYS,
    REFERENCE_DATE,
    REGION_COUNTRIES,
    REGION_WEIGHTS,
    REGIONS,
    RNG,
    SEGMENT_PLAN_WEIGHTS,
    SEGMENT_WEIGHTS,
    SEGMENTS,
    SUBSCRIPTION_PLANS,
    make_id,
    random_date,
    weighted_choice,
)

PROPENSITY_COLUMNS = [
    "_usage_propensity", "_engagement_propensity", "_satisfaction_propensity", "_payment_reliability",
]


def generate_base(n, employees_df):
    account_managers = employees_df[employees_df["department"] == "Account Management"]
    am_by_region = {
        region: account_managers.loc[account_managers["region"] == region, "employee_id"].tolist()
        for region in REGIONS
    }
    all_am_ids = account_managers["employee_id"].tolist()

    rows = []
    for i in range(1, n + 1):
        customer_id = make_id("CUST", i)
        segment = weighted_choice(RNG, SEGMENTS, SEGMENT_WEIGHTS)
        region = weighted_choice(RNG, REGIONS, REGION_WEIGHTS)
        country = RNG.choice(REGION_COUNTRIES[region])
        industry = RNG.choice(INDUSTRIES)

        signup_date = random_date(RNG, HISTORY_START, REFERENCE_DATE - relativedelta(days=30))
        contract_start_date = signup_date + relativedelta(days=RNG.randint(1, 14))

        next_renewal = contract_start_date + relativedelta(years=1)
        while next_renewal < REFERENCE_DATE:
            next_renewal += relativedelta(years=1)

        plan = weighted_choice(RNG, SUBSCRIPTION_PLANS, SEGMENT_PLAN_WEIGHTS[segment])

        candidates = am_by_region.get(region) or all_am_ids
        account_manager_id = RNG.choice(candidates) if candidates else None

        # Latent health cohort: most accounts are healthy, a minority are chronically at-risk.
        # The four propensities derive from it (plus noise) so downstream behavior correlates.
        if RNG.random() < 0.16:
            health = float(max(0.0, min(1.0, NP_RNG.beta(2, 6))))
        else:
            health = float(max(0.0, min(1.0, NP_RNG.beta(6, 2))))

        usage_propensity = max(0.0, min(1.0, health + NP_RNG.normal(0, 0.08)))
        engagement_propensity = max(0.0, min(1.0, health + NP_RNG.normal(0, 0.08)))
        satisfaction_propensity = max(0.0, min(1.0, health + NP_RNG.normal(0, 0.10)))
        payment_reliability = max(0.0, min(1.0, health + NP_RNG.normal(0, 0.12)))

        base_acv = {"Basic": 5000, "Standard": 15000, "Premium": 45000, "Enterprise": 110000}[plan]
        annual_contract_value = business_rules.priced_amount(base_acv, region, segment, contract_start_date.month)

        rows.append({
            "customer_id": customer_id,
            "company_name": FAKE.company(),
            "industry": industry,
            "segment": segment,
            "region": region,
            "country": country,
            "account_manager_id": account_manager_id,
            "subscription_plan": plan,
            "signup_date": signup_date.isoformat(),
            "contract_start_date": contract_start_date.isoformat(),
            "renewal_date": next_renewal.isoformat(),
            "annual_contract_value": annual_contract_value,
            "_usage_propensity": usage_propensity,
            "_engagement_propensity": engagement_propensity,
            "_satisfaction_propensity": satisfaction_propensity,
            "_payment_reliability": payment_reliability,
        })

    return pd.DataFrame(rows)


def finalize(customers_df, activity_df, support_df, payments_df):
    df = customers_df.copy()
    window_start = pd.Timestamp(REFERENCE_DATE - relativedelta(days=RECENT_WINDOW_DAYS))
    today_ts = pd.Timestamp(REFERENCE_DATE)

    activity_df = activity_df.copy()
    activity_df["activity_date"] = pd.to_datetime(activity_df["activity_date"])
    recent_activity = activity_df[activity_df["activity_date"] >= window_start]
    engagement_points = recent_activity.groupby("customer_id")["engagement_points"].sum()
    activity_counts = recent_activity.groupby("customer_id").size()

    support_df = support_df.copy()
    support_df["created_date"] = pd.to_datetime(support_df["created_date"])
    recent_support = support_df[support_df["created_date"] >= window_start]
    ticket_counts = recent_support.groupby("customer_id").size()
    avg_satisfaction = (
        support_df.dropna(subset=["satisfaction_rating"]).groupby("customer_id")["satisfaction_rating"].mean()
    )

    avg_delay = payments_df.groupby("customer_id")["days_late"].mean()

    def usage_score(row):
        count = activity_counts.get(row["customer_id"], 0)
        return round(max(0.0, min(100.0, count * (4 + row["_usage_propensity"] * 6))), 1)

    def engagement_score(row):
        points = engagement_points.get(row["customer_id"], 0.0)
        return round(max(0.0, min(100.0, points / 8 * (0.6 + row["_engagement_propensity"]))), 1)

    def satisfaction_score(row):
        if row["customer_id"] in avg_satisfaction.index:
            rating = avg_satisfaction.loc[row["customer_id"]]
            return round(max(0.0, min(100.0, rating / 5 * 100)), 1)
        return round(max(0.0, min(100.0, 55 + row["_satisfaction_propensity"] * 45)), 1)

    df["product_usage_score"] = df.apply(usage_score, axis=1)
    df["engagement_score"] = df.apply(engagement_score, axis=1)
    df["satisfaction_score"] = df.apply(satisfaction_score, axis=1)
    df["support_ticket_count_recent"] = df["customer_id"].map(ticket_counts).fillna(0).astype(int)
    df["avg_payment_delay_days"] = df["customer_id"].map(avg_delay).fillna(0.0).round(1)
    df["days_to_renewal"] = (pd.to_datetime(df["renewal_date"]) - today_ts).dt.days

    scored = df.apply(
        lambda row: business_rules.customer_risk_score(
            row["product_usage_score"], row["engagement_score"], row["satisfaction_score"],
            row["support_ticket_count_recent"], row["avg_payment_delay_days"], row["days_to_renewal"],
        ),
        axis=1,
    )
    df["churn_risk_score"] = [s[0] for s in scored]
    df["churn_risk_category"] = [s[1] for s in scored]

    return df.drop(columns=PROPENSITY_COLUMNS)
