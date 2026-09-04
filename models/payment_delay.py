"""Phase 4 predictive analytics: invoice payment delay classification. Run as:

    python -m models.payment_delay

Writes ANALYTICS.ML_PAYMENT_DELAY. Unlike the customer-churn and project-risk
models in this phase, this one finds genuine signal -- see
docs/predictive_analytics.md for why (a latent per-customer "health" factor
in the Phase 1 generator drives usage/engagement/satisfaction AND payment
reliability together, confirmed empirically: PRODUCT_USAGE_SCORE correlates
-0.33 with a customer's own average days_late, and a customer's early-vs-
late payment history is itself autocorrelated at 0.52 split-half).

TARGET: was a given invoice's payment late? days_late > 0 -> 1, else 0.
Training/evaluation is restricted to invoices that HAVE a recorded payment
(status resolved); Unpaid/Overdue/Cancelled invoices have no outcome yet
and are excluded from training (but still scored, using only pre-payment-
outcome features, for the production table).

LEAKAGE PREVENTION:
  - amount_paid, payment_date, and days_late itself are never features --
    they ARE (or directly determine) the target.
  - CUSTOMER_HISTORICAL_AVG_DELAY is computed leave-one-out: each invoice's
    feature is the customer's average days_late across their OTHER paid
    invoices only, excluding the invoice being scored. Using a customer's
    own average INCLUDING the current invoice would let the target leak
    directly into its own feature.
  - invoice_amount, invoice_age (due_date - invoice_date), segment, region,
    and the customer's usage/engagement/satisfaction scores are all known
    at invoice-issue time, independent of how this particular invoice is
    eventually paid.
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

logger = get_logger("payment_delay")

NUMERIC_FEATURES = [
    "TOTAL_AMOUNT", "INVOICE_AGE_DAYS", "PRODUCT_USAGE_SCORE", "ENGAGEMENT_SCORE",
    "SATISFACTION_SCORE", "CUSTOMER_HISTORICAL_AVG_DELAY",
]
CATEGORICAL_FEATURES = ["SEGMENT", "REGION_NAME"]

INVOICES_SQL = """
SELECT
    i.invoice_id, c.customer_id, i.status,
    i.total_amount,
    DATEDIFF('day', inv_dt.full_date, due_dt.full_date) AS invoice_age_days,
    c.segment, reg.region_name,
    c.product_usage_score, c.engagement_score, c.satisfaction_score,
    pay.days_late
FROM CORE.FACT_INVOICES i
JOIN CORE.DIM_CUSTOMER c ON c.customer_key = i.customer_key
LEFT JOIN CORE.DIM_REGION reg ON reg.region_key = c.region_key
JOIN CORE.DIM_DATE inv_dt ON inv_dt.date_key = i.invoice_date_key
JOIN CORE.DIM_DATE due_dt ON due_dt.date_key = i.due_date_key
LEFT JOIN (
    -- one row per invoice: total amount paid and the LATEST payment's
    -- days_late (an invoice can have multiple/partial payments; the final
    -- payment's days_late is the invoice-level "was it ultimately late" outcome)
    SELECT invoice_id, MAX(days_late) AS days_late
    FROM CORE.FACT_PAYMENTS
    GROUP BY invoice_id
) pay ON pay.invoice_id = i.invoice_id
"""

RISK_BANDS = [(0.66, "High"), (0.33, "Medium"), (0.0, "Low")]


def _risk_level(p):
    for threshold, label in RISK_BANDS:
        if p >= threshold:
            return label
    return "Low"


def _add_leave_one_out_history(df):
    """CUSTOMER_HISTORICAL_AVG_DELAY: each invoice gets the customer's mean
    days_late across their OTHER paid invoices, excluding itself. Customers
    with only one paid invoice (no "other" history) get the population
    median as a neutral prior, not their own (single, leaky) value."""
    df = df.copy()
    paid = df[df["DAYS_LATE"].notna()]
    per_customer_sum = paid.groupby("CUSTOMER_ID")["DAYS_LATE"].transform("sum")
    per_customer_count = paid.groupby("CUSTOMER_ID")["DAYS_LATE"].transform("count")
    loo_mean = (per_customer_sum - paid["DAYS_LATE"]) / (per_customer_count - 1)

    population_median = paid["DAYS_LATE"].median()
    loo_mean = loo_mean.where(per_customer_count > 1, population_median)

    df["CUSTOMER_HISTORICAL_AVG_DELAY"] = np.nan
    df.loc[paid.index, "CUSTOMER_HISTORICAL_AVG_DELAY"] = loo_mean

    # Invoices with no payment yet: use the customer's full paid history (no
    # leakage concern -- this invoice contributes no days_late to average).
    unpaid = df[df["DAYS_LATE"].isna()]
    customer_avg_all = paid.groupby("CUSTOMER_ID")["DAYS_LATE"].mean()
    df.loc[unpaid.index, "CUSTOMER_HISTORICAL_AVG_DELAY"] = (
        unpaid["CUSTOMER_ID"].map(customer_avg_all).fillna(population_median)
    )
    return df


def prepare(df, dummy_columns=None):
    numeric = df[NUMERIC_FEATURES].apply(pd.to_numeric, errors="coerce").copy()
    for col in numeric.columns:
        numeric[col] = numeric[col].fillna(numeric[col].median())

    categorical = df[CATEGORICAL_FEATURES].fillna("Unknown")
    dummies = pd.get_dummies(categorical, prefix=CATEGORICAL_FEATURES)
    if dummy_columns is not None:
        dummies = dummies.reindex(columns=dummy_columns, fill_value=0)

    return pd.concat([numeric.reset_index(drop=True), dummies.reset_index(drop=True)], axis=1)


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
    df = fetch_dataframe(INVOICES_SQL)
    df = _add_leave_one_out_history(df)
    logger.info("Loaded %d invoices total", len(df))

    resolved = df[df["DAYS_LATE"].notna()].copy()
    resolved["IS_DELAYED"] = (resolved["DAYS_LATE"] > 0).astype(int)
    logger.info("%d invoices have a recorded payment outcome (for training)", len(resolved))

    y = resolved["IS_DELAYED"]
    class_counts = y.value_counts().to_dict()
    logger.info("Class distribution (1=late): %s", class_counts)

    train_idx, test_idx = train_test_split(resolved.index, test_size=0.25, random_state=RANDOM_STATE, stratify=y)
    train_df, test_df = resolved.loc[train_idx], resolved.loc[test_idx]

    X_train = prepare(train_df)
    train_dummy_columns = [c for c in X_train.columns if c not in NUMERIC_FEATURES]
    X_test = prepare(test_df, dummy_columns=train_dummy_columns)
    y_train, y_test = train_df["IS_DELAYED"], test_df["IS_DELAYED"]

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    logreg = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=RANDOM_STATE)
    logreg.fit(X_train_scaled, y_train)
    logreg_metrics = evaluate("LogisticRegression", logreg, X_test_scaled, y_test)

    rf = RandomForestClassifier(n_estimators=300, max_depth=8, class_weight="balanced", random_state=RANDOM_STATE)
    rf.fit(X_train, y_train)
    rf_metrics = evaluate("RandomForest", rf, X_test, y_test)

    candidates = {"LogisticRegression": (logreg, logreg_metrics, True), "RandomForest": (rf, rf_metrics, False)}
    selected_name = max(candidates, key=lambda k: (candidates[k][1]["roc_auc"], candidates[k][1]["f1"]))
    selected_model, selected_metrics, needs_scaling = candidates[selected_name]
    logger.info("Selected model: %s", selected_name)

    feature_names = X_train.columns.tolist()
    if selected_name == "RandomForest":
        feature_importance = dict(zip(feature_names, selected_model.feature_importances_.tolist()))
    else:
        feature_importance = dict(zip(feature_names, selected_model.coef_[0].tolist()))

    save_model({"model": selected_model, "scaler": scaler if needs_scaling else None, "feature_columns": feature_names}, "payment_delay")
    save_metrics({
        "model_version": MODEL_VERSION,
        "selected_algorithm": selected_name,
        "algorithms_compared": {"LogisticRegression": logreg_metrics, "RandomForest": rf_metrics},
        "class_distribution": class_counts,
        "train_rows": len(X_train),
        "test_rows": len(X_test),
        "features": NUMERIC_FEATURES + CATEGORICAL_FEATURES,
        "target": "invoice_payment_was_late (days_late > 0)",
        "training_population": "invoices with a recorded payment (status resolved)",
        "feature_importance": feature_importance,
    }, "payment_delay")

    # Score every invoice (paid or not) for the production table.
    X_all = prepare(df, dummy_columns=train_dummy_columns)
    X_all_scaled = scaler.transform(X_all) if needs_scaling else X_all
    all_proba = selected_model.predict_proba(X_all_scaled)[:, 1]
    all_pred = selected_model.predict(X_all_scaled)

    output = pd.DataFrame({
        "INVOICE_ID": df["INVOICE_ID"].values,
        "CUSTOMER_ID": df["CUSTOMER_ID"].values,
        "DELAY_PROBABILITY": all_proba,
        "PREDICTED_DELAY": all_pred.astype(int),
        "RISK_LEVEL": [_risk_level(p) for p in all_proba],
        "MODEL_VERSION": MODEL_VERSION,
        "GENERATED_AT": run_timestamp(),
    })
    write_table(output, "ML_PAYMENT_DELAY")

    return {"selected_algorithm": selected_name, "metrics": selected_metrics, "n_scored": len(output)}


if __name__ == "__main__":
    try:
        run()
    except Exception:
        logger.exception("payment_delay pipeline failed")
        sys.exit(1)
