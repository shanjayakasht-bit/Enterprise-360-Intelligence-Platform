"""Phase 4 predictive analytics: project delivery risk classification. Run as:

    python -m models.project_risk

Writes ANALYTICS.ML_PROJECT_RISK. See docs/predictive_analytics.md for the
honest discussion of this model's (expected-to-be-weak) performance.

TARGET: did the project finish late? 1 if status = 'Delayed', or status =
'Completed' with actual_end_date > planned_end_date; 0 if 'Completed' on
or before its planned end date. Training/evaluation is restricted to
projects with a RESOLVED outcome (status IN ('Completed', 'Delayed')) --
Planned/In Progress/On Hold/Cancelled projects have no determined outcome
yet and are excluded from training (though still scored for the output
table, using only planning-time features).

LEAKAGE PREVENTION: features are restricted to information knowable AT OR
NEAR PROJECT START. Explicitly EXCLUDED: actual_cost, cost_overrun_pct,
budget_utilization_pct (all computed FROM the realized outcome -- a project
that ran over cost is mechanically likely to also be the one that ran
late, so these would leak the answer), completion_pct (only meaningful
retrospectively for a resolved project), and project_risk_score/
project_risk_category (Phase 1's own formula output, the same leakage
class the brief warns against for the customer model). Only budget (set at
planning time), planned duration, service/project type, customer segment/
region, and delivery department are used.
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

logger = get_logger("project_risk")

NUMERIC_FEATURES = ["BUDGET", "PLANNED_DURATION_DAYS"]
CATEGORICAL_FEATURES = ["SEGMENT", "REGION_NAME", "SERVICE_NAME", "DEPARTMENT_NAME"]

PROJECTS_SQL = """
SELECT
    p.project_id, p.status,
    p.budget,
    DATEDIFF('day', start_dt.full_date, planned_dt.full_date) AS planned_duration_days,
    actual_dt.full_date > planned_dt.full_date AS finished_late_flag,  -- NULL unless actual_end_date_key resolves
    c.segment, reg.region_name, sv.service_name, dept.department_name
FROM CORE.FACT_PROJECTS p
JOIN CORE.DIM_CUSTOMER c ON c.customer_key = p.customer_key
LEFT JOIN CORE.DIM_REGION reg ON reg.region_key = c.region_key
LEFT JOIN CORE.DIM_SERVICE sv ON sv.service_key = p.service_key
LEFT JOIN CORE.DIM_EMPLOYEE pm ON pm.employee_key = p.project_manager_employee_key
LEFT JOIN CORE.DIM_DEPARTMENT dept ON dept.department_key = pm.department_key
JOIN CORE.DIM_DATE start_dt ON start_dt.date_key = p.start_date_key
JOIN CORE.DIM_DATE planned_dt ON planned_dt.date_key = p.planned_end_date_key
LEFT JOIN CORE.DIM_DATE actual_dt ON actual_dt.date_key = p.actual_end_date_key
"""

RISK_BANDS = [(0.66, "High"), (0.33, "Medium"), (0.0, "Low")]


def _risk_level(p):
    for threshold, label in RISK_BANDS:
        if p >= threshold:
            return label
    return "Low"


def load_data():
    df = fetch_dataframe(PROJECTS_SQL)
    # IS_DELAYED: 1 for an explicit 'Delayed' status, or a 'Completed' project
    # that finished after its planned_end_date; 0 for a 'Completed' project
    # that finished on or before it; NaN (unresolved) for everything else
    # (Planned/In Progress/On Hold/Cancelled), excluded from training.
    is_completed = df["STATUS"] == "Completed"
    df["IS_DELAYED"] = np.select(
        [df["STATUS"] == "Delayed", is_completed & (df["FINISHED_LATE_FLAG"] == True), is_completed & (df["FINISHED_LATE_FLAG"] == False)],
        [1, 1, 0],
        default=np.nan,
    )
    return df


def prepare(df, dummy_columns=None):
    """One-hot encodes the categorical features (aligned to dummy_columns --
    the training split's dummy column set -- when given, so a category seen
    only in the test/scoring split can never introduce a column the model
    wasn't trained on, and vice versa) and returns the combined
    numeric+encoded feature matrix."""
    numeric = df[NUMERIC_FEATURES].apply(pd.to_numeric, errors="coerce").copy()
    numeric["BUDGET"] = numeric["BUDGET"].fillna(numeric["BUDGET"].median())
    numeric["PLANNED_DURATION_DAYS"] = numeric["PLANNED_DURATION_DAYS"].fillna(numeric["PLANNED_DURATION_DAYS"].median())

    categorical = df[CATEGORICAL_FEATURES].fillna("Unknown")
    dummies = pd.get_dummies(categorical, prefix=CATEGORICAL_FEATURES)

    if dummy_columns is not None:
        dummies = dummies.reindex(columns=dummy_columns, fill_value=0)

    X = pd.concat([numeric.reset_index(drop=True), dummies.reset_index(drop=True)], axis=1)
    return X


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
    df = load_data()
    resolved = df[df["IS_DELAYED"].notna()].copy()
    resolved["IS_DELAYED"] = resolved["IS_DELAYED"].astype(int)
    logger.info("Loaded %d projects total; %d have a resolved outcome (Completed/Delayed) for training", len(df), len(resolved))

    y = resolved["IS_DELAYED"]
    class_counts = y.value_counts().to_dict()
    logger.info("Class distribution (1=delayed): %s", class_counts)

    train_idx, test_idx = train_test_split(
        resolved.index, test_size=0.25, random_state=RANDOM_STATE, stratify=y,
    )
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

    rf = RandomForestClassifier(n_estimators=300, max_depth=6, class_weight="balanced", random_state=RANDOM_STATE)
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

    save_model({"model": selected_model, "scaler": scaler if needs_scaling else None, "feature_columns": feature_names}, "project_risk")
    save_metrics({
        "model_version": MODEL_VERSION,
        "selected_algorithm": selected_name,
        "algorithms_compared": {"LogisticRegression": logreg_metrics, "RandomForest": rf_metrics},
        "class_distribution": class_counts,
        "train_rows": len(X_train),
        "test_rows": len(X_test),
        "features": NUMERIC_FEATURES + CATEGORICAL_FEATURES,
        "target": "project_finished_late (Delayed status, or Completed after planned_end_date)",
        "training_population": "projects with status IN ('Completed','Delayed') -- resolved outcomes only",
        "feature_importance": feature_importance,
    }, "project_risk")

    # Score every project (including still-open ones) using only
    # planning-time features, for the production risk table.
    X_all = prepare(df, dummy_columns=train_dummy_columns)
    X_all_scaled = scaler.transform(X_all) if needs_scaling else X_all
    all_proba = selected_model.predict_proba(X_all_scaled)[:, 1]
    all_pred = selected_model.predict(X_all_scaled)

    output = pd.DataFrame({
        "PROJECT_ID": df["PROJECT_ID"].values,
        "RISK_PROBABILITY": all_proba,
        "PREDICTED_RISK_CLASS": all_pred.astype(int),
        "RISK_LEVEL": [_risk_level(p) for p in all_proba],
        "MODEL_VERSION": MODEL_VERSION,
        "GENERATED_AT": run_timestamp(),
    })
    write_table(output, "ML_PROJECT_RISK")

    return {"selected_algorithm": selected_name, "metrics": selected_metrics, "n_scored": len(output)}


if __name__ == "__main__":
    try:
        run()
    except Exception:
        logger.exception("project_risk pipeline failed")
        sys.exit(1)
