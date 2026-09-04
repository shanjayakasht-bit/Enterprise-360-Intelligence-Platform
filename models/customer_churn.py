"""Phase 4 predictive analytics: customer churn / risk classification. Run as:

    python -m models.customer_churn

Writes ANALYTICS.ML_CUSTOMER_RISK. Full detail, including an important
honest finding about this target's predictability, is in
docs/predictive_analytics.md -- read that before trusting this model's
metrics at face value.

TARGET: for customers with EXACTLY ONE subscription, did that subscription
end up Cancelled or Expired (CORE.FACT_SUBSCRIPTIONS.status)? This is a
genuine, independently recorded business OUTCOME -- not a risk score. It is
deliberately NOT Phase 1's own churn_risk_category (or a binarized version
of it): that field is a deterministic formula OF the very behavioral
features below, so using it as the target while also using its own inputs
as features would just have the model re-learn a known formula, not
predict anything.

Restricting to single-subscription customers is itself a leakage fix, not
an arbitrary choice: an earlier version of this pipeline used "ANY
subscription Cancelled/Expired" across ALL of a customer's subscriptions
and got a suspiciously good ROC-AUC (~0.71). Investigating why revealed a
mechanical artifact, not real signal -- each subscription independently
has a ~1/3 chance of ending up Cancelled/Expired (see
data_generator/master_data.py's SUBSCRIPTION_STATUSES weights), so
P(at least one cancelled | n subscriptions) = 1 - (2/3)^n rises with
subscription count alone, with zero behavioral content. Bigger customers
(higher TOTAL_REVENUE, more subscriptions) were mechanically more likely to
trip that target, which is exactly why TOTAL_REVENUE dominated that
version's feature importance -- it was standing in for subscription count,
not genuine churn risk. Restricting to n_subscriptions == 1 removes this
confound entirely (a single Bernoulli draw has no count to be confounded
by). See docs/predictive_analytics.md for the full empirical investigation
and both versions' numbers.

FEATURES are pulled from ANALYTICS.VW_CUSTOMER_HEALTH and VW_CUSTOMER_360,
explicitly EXCLUDING: churn_risk_score/category, health_score/customer_
health_score, customer_status/risk_classification (all derived FROM
churn_risk_score -- the exact leakage the brief warns against), and
active_subscriptions/arr/mrr (definitionally tied to subscription status,
which the target is built from).
"""

import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, confusion_matrix, f1_score, precision_score,
    recall_score, roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from models.common import (
    MODEL_VERSION, RANDOM_STATE, fetch_dataframe, get_logger, run_timestamp,
    save_metrics, save_model, write_table,
)

logger = get_logger("customer_churn")

FEATURE_COLUMNS = [
    "PRODUCT_USAGE_SCORE", "ENGAGEMENT_SCORE", "SATISFACTION_SCORE",
    "SUPPORT_TICKET_COUNT_RECENT", "OPEN_TICKET_COUNT", "AVG_PAYMENT_DELAY_DAYS",
    "OUTSTANDING_AMOUNT", "DAYS_TO_RENEWAL", "TOTAL_REVENUE", "SLA_BREACHES",
    "PROJECT_RISK", "ACTIVITY_COUNT",
]

FEATURES_SQL = """
SELECT
    h.customer_id,
    h.product_usage_score, h.engagement_score, h.satisfaction_score,
    h.support_ticket_count_recent, h.open_ticket_count, h.avg_payment_delay_days,
    h.outstanding_amount, h.days_to_renewal,
    c360.total_revenue, c360.sla_breaches, c360.project_risk, c360.activity_count
FROM ANALYTICS.VW_CUSTOMER_HEALTH h
JOIN ANALYTICS.VW_CUSTOMER_360 c360 ON c360.customer_id = h.customer_id
"""

TARGET_SQL = """
WITH sub_counts AS (
    SELECT c.customer_id,
           COUNT(s.subscription_id) AS n_subscriptions,
           MAX(IFF(s.status IN ('Cancelled', 'Expired'), 1, 0)) AS churned
    FROM CORE.DIM_CUSTOMER c
    LEFT JOIN CORE.FACT_SUBSCRIPTIONS s ON s.customer_key = c.customer_key
    WHERE c.is_current = TRUE AND c.customer_key <> -1
    GROUP BY c.customer_id
)
SELECT customer_id, churned FROM sub_counts WHERE n_subscriptions = 1
"""

RISK_BANDS = [(0.66, "High"), (0.33, "Medium"), (0.0, "Low")]


def _risk_level(p):
    for threshold, label in RISK_BANDS:
        if p >= threshold:
            return label
    return "Low"


def load_data():
    features = fetch_dataframe(FEATURES_SQL)
    target = fetch_dataframe(TARGET_SQL)
    df = features.merge(target, on="CUSTOMER_ID", how="inner")
    return df


def prepare(df):
    X = df[FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce").copy()
    null_counts = X.isna().sum()
    # AVG_PAYMENT_DELAY_DAYS null => no payments recorded => 0 (no observed delay).
    # PROJECT_RISK null => no projects => 0 (no project risk).
    # OUTSTANDING_AMOUNT null => customer has zero invoices (VW_CUSTOMER_HEALTH's
    # SUM over no rows) => 0 (no outstanding balance, correctly, not unknown).
    X["AVG_PAYMENT_DELAY_DAYS"] = X["AVG_PAYMENT_DELAY_DAYS"].fillna(0)
    X["PROJECT_RISK"] = X["PROJECT_RISK"].fillna(0)
    X["OUTSTANDING_AMOUNT"] = X["OUTSTANDING_AMOUNT"].fillna(0)
    remaining = X.isna().sum().sum()
    if remaining:
        raise ValueError(f"unexpected NaNs after imputation: {X.isna().sum()[X.isna().sum() > 0]}")
    logger.info("Null counts before imputation: %s", dict(null_counts[null_counts > 0]))
    y = df["CHURNED"].astype(int)
    return X, y


def evaluate(name, model, X_test, y_test):
    proba = model.predict_proba(X_test)[:, 1]
    pred = model.predict(X_test)
    metrics = {
        "accuracy": accuracy_score(y_test, pred),
        "precision": precision_score(y_test, pred, zero_division=0),
        "recall": recall_score(y_test, pred, zero_division=0),
        "f1": f1_score(y_test, pred, zero_division=0),
        "roc_auc": roc_auc_score(y_test, proba),
        "confusion_matrix": confusion_matrix(y_test, pred).tolist(),
    }
    logger.info("[%s] accuracy=%.3f precision=%.3f recall=%.3f f1=%.3f roc_auc=%.3f",
                name, metrics["accuracy"], metrics["precision"], metrics["recall"], metrics["f1"], metrics["roc_auc"])
    return metrics


def run():
    all_features = fetch_dataframe(FEATURES_SQL)
    logger.info("Loaded features for %d current customers (full population, for scoring)", len(all_features))

    df = load_data()
    logger.info("Loaded %d single-subscription customers with resolvable target (for training/evaluation)", len(df))

    X, y = prepare(df)
    class_counts = y.value_counts().to_dict()
    logger.info("Class distribution (1=churned): %s", class_counts)

    X_train, X_test, y_train, y_test, id_train, id_test = train_test_split(
        X, y, df["CUSTOMER_ID"], test_size=0.25, random_state=RANDOM_STATE, stratify=y,
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    logreg = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=RANDOM_STATE)
    logreg.fit(X_train_scaled, y_train)
    logreg_metrics = evaluate("LogisticRegression", logreg, X_test_scaled, y_test)

    rf = RandomForestClassifier(n_estimators=300, max_depth=6, class_weight="balanced", random_state=RANDOM_STATE)
    rf.fit(X_train, y_train)  # tree model: no scaling needed
    rf_metrics = evaluate("RandomForest", rf, X_test, y_test)

    # Model selection: compare on F1 and ROC-AUC together (not accuracy alone,
    # per the brief) -- see docs/predictive_analytics.md for the honest
    # discussion of why both models land near chance-level here.
    candidates = {"LogisticRegression": (logreg, logreg_metrics, True), "RandomForest": (rf, rf_metrics, False)}
    selected_name = max(candidates, key=lambda k: (candidates[k][1]["roc_auc"], candidates[k][1]["f1"]))
    selected_model, selected_metrics, needs_scaling = candidates[selected_name]
    logger.info("Selected model: %s", selected_name)

    feature_importance = None
    if selected_name == "RandomForest":
        feature_importance = dict(zip(FEATURE_COLUMNS, selected_model.feature_importances_.tolist()))
    else:
        feature_importance = dict(zip(FEATURE_COLUMNS, selected_model.coef_[0].tolist()))

    save_model({"model": selected_model, "scaler": scaler if needs_scaling else None, "features": FEATURE_COLUMNS}, "customer_churn")
    metrics_payload = {
        "model_version": MODEL_VERSION,
        "selected_algorithm": selected_name,
        "algorithms_compared": {"LogisticRegression": logreg_metrics, "RandomForest": rf_metrics},
        "class_distribution": class_counts,
        "train_rows": len(X_train),
        "test_rows": len(X_test),
        "features": FEATURE_COLUMNS,
        "target": "single_subscription_customer_ended_cancelled_or_expired",
        "training_population": "customers with exactly 1 subscription (see file header: removes a mechanical count-based confound found in an earlier version)",
        "feature_importance": feature_importance,
    }
    save_metrics(metrics_payload, "customer_churn")

    # Score the FULL current-customer population (not just the single-
    # subscription training population) -- a production risk table should
    # cover every current customer. The model generalizes its learned
    # (honestly weak) pattern to customers with 0 or multiple subscriptions
    # too; see docs/predictive_analytics.md for why this extrapolation is
    # reasonable here (the features themselves are defined for everyone).
    X_all, _ = prepare(all_features.assign(CHURNED=0))  # CHURNED unused, only needed by prepare()'s signature
    X_all_scaled = scaler.transform(X_all) if needs_scaling else X_all
    all_proba = selected_model.predict_proba(X_all_scaled)[:, 1]
    all_pred = selected_model.predict(X_all_scaled)

    output = pd.DataFrame({
        "CUSTOMER_ID": all_features["CUSTOMER_ID"].values,
        "RISK_PROBABILITY": all_proba,
        "PREDICTED_CLASS": all_pred.astype(int),
        "RISK_LEVEL": [_risk_level(p) for p in all_proba],
        "MODEL_VERSION": MODEL_VERSION,
        "GENERATED_AT": run_timestamp(),
    })
    write_table(output, "ML_CUSTOMER_RISK")

    return {"selected_algorithm": selected_name, "metrics": selected_metrics, "n_scored": len(output)}


if __name__ == "__main__":
    try:
        run()
    except Exception:
        logger.exception("customer_churn pipeline failed")
        sys.exit(1)
