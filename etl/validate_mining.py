"""Validates the Phase 3 data mining outputs. Run as:

    python -m etl.validate_mining

Checks customer segmentation (coverage, uniqueness, valid cluster IDs,
silhouette score, no NaN features, segment-name consistency), association
rules (support/confidence/lift bounds, no self-rules, thresholds honored),
anomaly detection (scores/labels present, valid entity IDs, no duplicate
keys), and that all 4 DM_* tables exist with row counts that reconcile
against independently-recomputed expectations -- plus that RAW/STAGING/CORE
remain unchanged.
"""

import sys

from etl.snowflake_connection import get_connection
from mining.association_rules import MIN_CONFIDENCE, MIN_LIFT, MIN_SUPPORT
from mining.customer_segmentation import prepare_features, load_customer_features

# Same Phase 2A/2B/2C baselines reused by etl/validate_analytics.py -- any
# drift means something outside Phase 3 touched RAW, STAGING, or CORE.
EXPECTED_RAW_STAGING_COUNTS = {
    "CUSTOMERS": 5000, "EMPLOYEES": 1000, "LEADS": 15000, "DEALS": 20000,
    "SUBSCRIPTIONS": 10000, "PROJECTS": 8000, "INVOICES": 30000, "PAYMENTS": 22777,
    "SUPPORT_TICKETS": 40000, "CUSTOMER_ACTIVITY": 50000,
}
EXPECTED_CORE_COUNTS = {
    "DIM_DATE": 4384, "DIM_REGION": 6, "DIM_DEPARTMENT": 10, "DIM_SERVICE": 16,
    "DIM_EMPLOYEE": 1001, "DIM_CUSTOMER": 5001,
    "FACT_LEADS": 15000, "FACT_DEALS": 20000, "FACT_SUBSCRIPTIONS": 10000,
    "FACT_PROJECTS": 8000, "FACT_INVOICES": 30000, "FACT_PAYMENTS": 22777,
    "FACT_SUPPORT": 40000, "FACT_CUSTOMER_ACTIVITY": 50000,
}
EXPECTED_ANALYTICS_COUNTS = {
    "VW_CUSTOMER_360": 5000, "VW_PROJECT_RISK": 8000,
}
MINING_TABLES = [
    "DM_CUSTOMER_SEGMENTS", "DM_CUSTOMER_CLUSTER_PROFILE",
    "DM_SERVICE_ASSOCIATIONS", "DM_BUSINESS_ANOMALIES",
]


def _scalar(cur, sql):
    cur.execute(sql)
    return cur.fetchone()[0]


def _table_exists(cur, table):
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'ANALYTICS' AND TABLE_NAME = %s",
        (table,),
    )
    return cur.fetchone()[0] == 1


def run():
    conn = get_connection()
    checks = []

    print("NEXORA DATA MINING VALIDATION")

    try:
        cur = conn.cursor()

        # ============================================================
        # Customer Segmentation
        # ============================================================
        eligible = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.VW_CUSTOMER_360")
        clustered = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.DM_CUSTOMER_SEGMENTS")
        distinct_customers = _scalar(cur, "SELECT COUNT(DISTINCT customer_id) FROM ANALYTICS.DM_CUSTOMER_SEGMENTS")
        cur.execute("SELECT DISTINCT selected_k, silhouette_score FROM ANALYTICS.DM_CUSTOMER_CLUSTER_PROFILE")
        k_sil_rows = cur.fetchall()
        selected_k = k_sil_rows[0][0] if k_sil_rows else None
        silhouette = float(k_sil_rows[0][1]) if k_sil_rows else None

        coverage_ok = clustered == eligible
        checks.append(("Every eligible customer receives one cluster", coverage_ok,
                        f"eligible={eligible} clustered={clustered}"))
        no_dupes = clustered == distinct_customers
        checks.append(("No duplicate customer_id in DM_CUSTOMER_SEGMENTS", no_dupes,
                        f"rows={clustered} distinct={distinct_customers}"))

        cluster_ids_in_segments = {r[0] for r in cur.execute(
            "SELECT DISTINCT cluster_id FROM ANALYTICS.DM_CUSTOMER_SEGMENTS").fetchall()}
        cluster_ids_in_profile = {r[0] for r in cur.execute(
            "SELECT cluster_id FROM ANALYTICS.DM_CUSTOMER_CLUSTER_PROFILE").fetchall()}
        valid_cluster_ids = cluster_ids_in_segments == cluster_ids_in_profile and len(cluster_ids_in_profile) > 0
        checks.append(("Cluster IDs are valid (segments <-> profile match)", valid_cluster_ids,
                        f"segments={sorted(cluster_ids_in_segments)} profile={sorted(cluster_ids_in_profile)}"))

        silhouette_ok = silhouette is not None and -1.0 <= silhouette <= 1.0
        checks.append(("Silhouette score is calculated and in [-1, 1]", silhouette_ok, f"silhouette={silhouette}"))

        raw_df = load_customer_features()
        features = prepare_features(raw_df)
        no_nan = int(features.isna().sum().sum()) == 0
        checks.append(("No NaN model features after preprocessing", no_nan,
                        f"NaN count={int(features.isna().sum().sum())}"))

        cur.execute("""
            SELECT s.cluster_id, s.segment_name, p.segment_name
            FROM ANALYTICS.DM_CUSTOMER_SEGMENTS s
            JOIN ANALYTICS.DM_CUSTOMER_CLUSTER_PROFILE p ON p.cluster_id = s.cluster_id
            WHERE s.segment_name <> p.segment_name
        """)
        mismatches = cur.fetchall()
        names_consistent = len(mismatches) == 0
        checks.append(("Segment names match cluster profile logic", names_consistent,
                        "consistent" if names_consistent else f"{len(mismatches)} mismatched rows"))

        print("\nCustomer Segmentation")
        print(f"Eligible customers: {eligible}")
        print(f"Clustered customers: {clustered}")
        print(f"Selected K: {selected_k}")
        print(f"Silhouette Score: {silhouette}")
        seg_pass = coverage_ok and no_dupes and valid_cluster_ids and silhouette_ok and no_nan and names_consistent
        print("PASS" if seg_pass else "FAIL")

        # ============================================================
        # Association Rules
        # ============================================================
        cur.execute("SELECT support, confidence, lift, antecedent, consequent FROM ANALYTICS.DM_SERVICE_ASSOCIATIONS")
        rule_rows = cur.fetchall()
        n_rules = len(rule_rows)

        support_ok = all(0 <= float(r[0]) <= 1 for r in rule_rows)
        confidence_ok = all(0 <= float(r[1]) <= 1 for r in rule_rows)
        lift_ok = all(float(r[2]) > 0 for r in rule_rows)
        distinct_ok = all(r[3] != r[4] for r in rule_rows)
        thresholds_ok = all(
            float(r[0]) >= MIN_SUPPORT - 1e-9 and float(r[1]) >= MIN_CONFIDENCE - 1e-9 and float(r[2]) >= MIN_LIFT - 1e-9
            for r in rule_rows
        )
        checks.append(("Support in [0, 1] for all rules", support_ok, f"{n_rules} rules checked"))
        checks.append(("Confidence in [0, 1] for all rules", confidence_ok, f"{n_rules} rules checked"))
        checks.append(("Lift > 0 for all rules", lift_ok, f"{n_rules} rules checked"))
        checks.append(("Antecedent != consequent for all rules", distinct_ok, f"{n_rules} rules checked"))
        checks.append((f"All rules satisfy configured thresholds (support>={MIN_SUPPORT}, confidence>={MIN_CONFIDENCE}, lift>={MIN_LIFT})",
                        thresholds_ok, f"{n_rules} rules checked"))

        print("\nAssociation Rules")
        print(f"Rules generated: {n_rules}")
        assoc_pass = support_ok and confidence_ok and lift_ok and distinct_ok and thresholds_ok and n_rules > 0
        print("PASS" if assoc_pass else "FAIL")

        # ============================================================
        # Anomaly Detection
        # ============================================================
        total_scored = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.DM_BUSINESS_ANOMALIES")
        scores_present = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.DM_BUSINESS_ANOMALIES WHERE anomaly_score IS NULL") == 0
        labels_present = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.DM_BUSINESS_ANOMALIES WHERE is_anomaly IS NULL") == 0
        n_anomalies = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.DM_BUSINESS_ANOMALIES WHERE is_anomaly = TRUE")
        anomaly_rate = (n_anomalies / total_scored * 100) if total_scored else 0

        checks.append(("Anomaly scores exist for all records", scores_present, f"{total_scored} records checked"))
        checks.append(("Anomaly labels exist for all records", labels_present, f"{total_scored} records checked"))

        dup_keys = _scalar(cur, """
            SELECT COUNT(*) FROM (
                SELECT entity_type, entity_id, anomaly_type FROM ANALYTICS.DM_BUSINESS_ANOMALIES
                GROUP BY entity_type, entity_id, anomaly_type HAVING COUNT(*) > 1
            )
        """)
        checks.append(("No duplicate anomaly result keys", dup_keys == 0, f"{dup_keys} duplicate keys"))

        invalid_customer_ids = _scalar(cur, """
            SELECT COUNT(*) FROM ANALYTICS.DM_BUSINESS_ANOMALIES a
            WHERE a.entity_type = 'CUSTOMER'
              AND NOT EXISTS (SELECT 1 FROM CORE.DIM_CUSTOMER c WHERE c.customer_id = a.entity_id AND c.is_current = TRUE)
        """)
        invalid_project_ids = _scalar(cur, """
            SELECT COUNT(*) FROM ANALYTICS.DM_BUSINESS_ANOMALIES a
            WHERE a.entity_type = 'PROJECT'
              AND NOT EXISTS (SELECT 1 FROM CORE.FACT_PROJECTS p WHERE p.project_id = a.entity_id)
        """)
        entity_ids_valid = invalid_customer_ids == 0 and invalid_project_ids == 0
        checks.append(("Entity identifiers are valid", entity_ids_valid,
                        f"invalid_customer_ids={invalid_customer_ids} invalid_project_ids={invalid_project_ids}"))

        print("\nAnomaly Detection")
        print(f"Records scored: {total_scored}")
        print(f"Anomalies detected: {n_anomalies}")
        print(f"Anomaly rate: {anomaly_rate:.1f}%")
        anomaly_pass = scores_present and labels_present and dup_keys == 0 and entity_ids_valid
        print("PASS" if anomaly_pass else "FAIL")

        # ============================================================
        # Database: table existence + row-count reconciliation
        # ============================================================
        table_results = {}
        for t in MINING_TABLES:
            table_results[t] = _table_exists(cur, t)
            checks.append((f"{t} exists", table_results[t], "table found" if table_results[t] else "TABLE NOT FOUND"))

        cluster_profile_rows = _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.DM_CUSTOMER_CLUSTER_PROFILE")
        profile_reconciles = cluster_profile_rows == len(cluster_ids_in_profile)
        checks.append(("DM_CUSTOMER_CLUSTER_PROFILE row count reconciles with distinct cluster count",
                        profile_reconciles, f"profile_rows={cluster_profile_rows} distinct_clusters={len(cluster_ids_in_profile)}"))

        expected_anomaly_rows = eligible + _scalar(cur, "SELECT COUNT(*) FROM ANALYTICS.VW_PROJECT_RISK")
        anomaly_reconciles = total_scored == expected_anomaly_rows
        checks.append(("DM_BUSINESS_ANOMALIES row count reconciles with VW_CUSTOMER_360 + VW_PROJECT_RISK",
                        anomaly_reconciles, f"table={total_scored} expected={expected_anomaly_rows}"))

        # ---- RAW / STAGING / CORE / ANALYTICS source views unchanged ----
        for table, expected in EXPECTED_RAW_STAGING_COUNTS.items():
            raw_rows = _scalar(cur, f"SELECT COUNT(*) FROM RAW.{table}")
            stg_rows = _scalar(cur, f"SELECT COUNT(*) FROM STAGING.STG_{table}")
            checks.append((f"RAW.{table} unchanged", raw_rows == expected, f"expected {expected}, found {raw_rows}"))
            checks.append((f"STAGING.STG_{table} unchanged", stg_rows == expected, f"expected {expected}, found {stg_rows}"))
        for table, expected in EXPECTED_CORE_COUNTS.items():
            core_rows = _scalar(cur, f"SELECT COUNT(*) FROM CORE.{table}")
            checks.append((f"CORE.{table} unchanged", core_rows == expected, f"expected {expected}, found {core_rows}"))
        for view, expected in EXPECTED_ANALYTICS_COUNTS.items():
            view_rows = _scalar(cur, f"SELECT COUNT(*) FROM ANALYTICS.{view}")
            checks.append((f"ANALYTICS.{view} unchanged", view_rows == expected, f"expected {expected}, found {view_rows}"))
    finally:
        conn.close()

    print(f"\nMining tables checked: {len(MINING_TABLES)}")

    print("\n" + "=" * 60)
    print("Detailed checks:")
    for name, passed, detail in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}")
    print("-" * 60)
    passed_count = sum(1 for _, p, _ in checks if p)
    failed_count = len(checks) - passed_count
    print(f"Passed: {passed_count}")
    print(f"Failed: {failed_count}")
    print("=" * 60)

    return failed_count == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
