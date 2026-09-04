"""Phase 3 data mining: business anomaly detection via Isolation Forest.
Run as:

    python -m mining.anomaly_detection

Two complementary passes over two different, meaningful business datasets
(see docs/data_mining.md for the full rationale):

  1. entity_type='CUSTOMER' -- financial/support/usage behavior per
     customer, from ANALYTICS.VW_CUSTOMER_360.
  2. entity_type='PROJECT'  -- budget/cost behavior per project, from
     ANALYTICS.VW_PROJECT_RISK.

Writes ANALYTICS.DM_BUSINESS_ANOMALIES. Isolation Forest flags statistical
outliers, not causes -- every flagged record's "reason" is derived
transparently from whichever input features deviated most from the
population, not claimed as an explanation the model itself produced.
"""

import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from mining.common import fetch_dataframe, get_logger, run_timestamp, write_table

logger = get_logger("anomaly_detection")

RANDOM_STATE = 42
CONTAMINATION = 0.05  # expect ~5% of entities to be flagged -- a conventional
                       # starting point for Isolation Forest when there is no
                       # labeled ground truth to tune against; see docs/data_mining.md

CUSTOMER_FEATURES = [
    "TOTAL_REVENUE", "OUTSTANDING_AMOUNT", "AVERAGE_PAYMENT_DELAY",
    "SUPPORT_TICKET_COUNT", "AVERAGE_USAGE_SCORE",
]
PROJECT_FEATURES = ["BUDGET", "ACTUAL_COST", "COST_VARIANCE", "BUDGET_UTILIZATION_PCT", "COST_OVERRUN_PCT"]


def _top_deviations(z_row, feature_names, raw_row, medians, n=2):
    """Returns (observed_value, expected_context) strings built from the n
    features with the largest |z-score| for this record -- a transparent,
    inspectable "why this was flagged", not a causal claim from the model."""
    order = np.argsort(-np.abs(z_row))[:n]
    observed_parts, expected_parts = [], []
    for i in order:
        feat = feature_names[i]
        observed_parts.append(f"{feat}={raw_row[feat]:.2f} (z={z_row[i]:+.2f})")
        expected_parts.append(f"{feat} typical(median)={medians[feat]:.2f}")
    return "; ".join(observed_parts), "; ".join(expected_parts)


def _score_entity(df, feature_columns, entity_id_col, entity_type, anomaly_type):
    features = df[feature_columns].apply(pd.to_numeric, errors="coerce").copy()
    null_counts = features.isna().sum()
    features = features.fillna(features.median())
    if null_counts.sum():
        logger.info("[%s/%s] filled nulls with column medians: %s",
                    entity_type, anomaly_type, dict(null_counts[null_counts > 0]))

    scaler = StandardScaler()
    scaled = scaler.fit_transform(features)
    z_scores = scaled  # StandardScaler output IS the z-score, reused directly for explainability

    model = IsolationForest(contamination=CONTAMINATION, random_state=RANDOM_STATE, n_estimators=200)
    model.fit(scaled)
    raw_scores = model.decision_function(scaled)   # higher = more normal, lower/negative = more anomalous
    predictions = model.predict(scaled)             # -1 = anomaly, 1 = normal

    medians = features.median()

    records = []
    for idx in range(len(df)):
        observed, expected = _top_deviations(z_scores[idx], feature_columns, features.iloc[idx], medians)
        records.append({
            "ENTITY_TYPE": entity_type,
            "ENTITY_ID": str(df[entity_id_col].iloc[idx]),
            "ANOMALY_TYPE": anomaly_type,
            "ANOMALY_SCORE": float(raw_scores[idx]),
            "IS_ANOMALY": bool(predictions[idx] == -1),
            "OBSERVED_VALUE": observed,
            "EXPECTED_CONTEXT": expected,
        })
    result = pd.DataFrame(records)
    n_anomalies = int(result["IS_ANOMALY"].sum())
    logger.info("[%s/%s] scored %d entities, %d flagged (%.1f%%)",
                entity_type, anomaly_type, len(result), n_anomalies, 100 * n_anomalies / len(result))
    return result


def score_customers():
    df = fetch_dataframe("SELECT CUSTOMER_ID, " + ", ".join(CUSTOMER_FEATURES) + " FROM ANALYTICS.VW_CUSTOMER_360")
    return _score_entity(df, CUSTOMER_FEATURES, "CUSTOMER_ID", "CUSTOMER", "FINANCIAL_SUPPORT_USAGE")


def score_projects():
    df = fetch_dataframe("SELECT PROJECT_ID, " + ", ".join(PROJECT_FEATURES) + " FROM ANALYTICS.VW_PROJECT_RISK")
    return _score_entity(df, PROJECT_FEATURES, "PROJECT_ID", "PROJECT", "COST_BUDGET_PATTERN")


def run():
    customer_results = score_customers()
    project_results = score_projects()

    combined = pd.concat([customer_results, project_results], ignore_index=True)
    combined["GENERATED_AT"] = run_timestamp()

    write_table(combined, "DM_BUSINESS_ANOMALIES")

    top_anomalies = combined[combined["IS_ANOMALY"]].sort_values("ANOMALY_SCORE").head(10)
    if not top_anomalies.empty:
        logger.info("Most anomalous records:\n%s",
                    top_anomalies[["ENTITY_TYPE", "ENTITY_ID", "ANOMALY_SCORE", "OBSERVED_VALUE"]].to_string(index=False))

    return {
        "records_scored": len(combined),
        "anomalies_detected": int(combined["IS_ANOMALY"].sum()),
        "anomaly_rate": float(combined["IS_ANOMALY"].mean()),
        "combined_df": combined,
    }


if __name__ == "__main__":
    try:
        run()
    except Exception:
        logger.exception("anomaly_detection pipeline failed")
        sys.exit(1)
