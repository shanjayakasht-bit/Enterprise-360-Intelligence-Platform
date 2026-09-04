"""Phase 3 data mining: customer segmentation via K-Means on
NEXORA_DB.ANALYTICS.VW_CUSTOMER_360. Run as:

    python -m mining.customer_segmentation

Writes ANALYTICS.DM_CUSTOMER_SEGMENTS (one row per customer) and
ANALYTICS.DM_CUSTOMER_CLUSTER_PROFILE (one row per cluster). Full detail
and rationale for every choice below is in docs/data_mining.md.
"""

import sys

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from mining.common import fetch_dataframe, get_logger, run_timestamp, write_table

logger = get_logger("customer_segmentation")

# Numeric, behavioral features from VW_CUSTOMER_360. customer_id/company_name
# (identifiers) and segment/region/industry/customer_status (categorical,
# and in customer_status's case a business-ASSIGNED label -- using it as a
# clustering input would just let the model reproduce that label rather
# than discover structure) are all deliberately excluded from the feature
# matrix.
#
# Also excluded, and why: WON_DEAL_VALUE and MRR are near-duplicates of
# TOTAL_REVENUE and ARR respectively (MRR = ARR / 12 exactly; won_deal_value
# and total_revenue differ only by the discount already netted out of
# total_revenue) -- including both would double-weight the same underlying
# signal. ACTIVITY_COUNT, DELAYED_PROJECTS, OPEN_TICKET_COUNT, PROJECT_COUNT
# and RECENT_ACTIVITY_DATE are lower-resolution proxies of signals already
# captured by the features below (usage score, project risk, SLA breaches,
# support ticket count) and were dropped to keep the feature set compact
# and non-redundant.
FEATURE_COLUMNS = [
    "TOTAL_REVENUE",
    "ARR",
    "ACTIVE_SUBSCRIPTIONS",
    "AVERAGE_USAGE_SCORE",
    "SUPPORT_TICKET_COUNT",
    "SLA_BREACHES",
    "AVERAGE_SUPPORT_SATISFACTION",
    "AVERAGE_PAYMENT_DELAY",
    "OUTSTANDING_AMOUNT",
    "PROJECT_RISK",
    "CUSTOMER_HEALTH_SCORE",
]

# Heavy-tailed monetary columns (max >> p95 in the live data -- e.g.
# OUTSTANDING_AMOUNT's max is ~9x its own 95th percentile) are winsorized
# at the 99th percentile before scaling, so a handful of very large
# accounts can't single-handedly pull cluster centroids toward them.
WINSORIZE_COLUMNS = ["TOTAL_REVENUE", "ARR", "OUTSTANDING_AMOUNT"]
WINSORIZE_PERCENTILE = 0.99

K_CANDIDATES = list(range(2, 9))
RANDOM_STATE = 42


def load_customer_features():
    df = fetch_dataframe("SELECT * FROM ANALYTICS.VW_CUSTOMER_360")
    return df


def prepare_features(df):
    """Explicit null handling and outlier capping -- see file header and
    docs/data_mining.md for the rationale behind each choice."""
    features = df[FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce").copy()

    null_counts_before = features.isna().sum()

    # AVERAGE_PAYMENT_DELAY is NULL for customers with zero recorded
    # payments (AVG over an empty set) -- there is no observed delay
    # behavior, so 0 ("no delay on record") is the honest neutral value,
    # not a guess.
    features["AVERAGE_PAYMENT_DELAY"] = features["AVERAGE_PAYMENT_DELAY"].fillna(0)

    # PROJECT_RISK is NULL for customers with zero projects -- there is no
    # project to carry risk, so 0 is again the correct value, not an
    # imputed guess.
    features["PROJECT_RISK"] = features["PROJECT_RISK"].fillna(0)

    # AVERAGE_SUPPORT_SATISFACTION is NULL for customers with zero rated
    # tickets -- this genuinely IS unknown (not "zero satisfaction"), so it
    # gets the population median rather than an assumed extreme.
    median_satisfaction = features["AVERAGE_SUPPORT_SATISFACTION"].median()
    features["AVERAGE_SUPPORT_SATISFACTION"] = features["AVERAGE_SUPPORT_SATISFACTION"].fillna(median_satisfaction)

    for col in WINSORIZE_COLUMNS:
        cap = features[col].quantile(WINSORIZE_PERCENTILE)
        n_capped = int((features[col] > cap).sum())
        features[col] = features[col].clip(upper=cap)
        if n_capped:
            logger.info("Winsorized %s: capped %d values at the %.0fth percentile (%.2f)",
                        col, n_capped, WINSORIZE_PERCENTILE * 100, cap)

    remaining_nulls = features.isna().sum().sum()
    if remaining_nulls:
        raise ValueError(f"unexpected NaNs remain after imputation: {features.isna().sum()[features.isna().sum() > 0]}")

    logger.info("Null counts before imputation: %s", dict(null_counts_before[null_counts_before > 0]))
    return features


def evaluate_k(scaled_features):
    """Fits K-Means for every candidate K and returns inertia + silhouette
    per K, so the final K is chosen from evidence, not assumed."""
    results = []
    for k in K_CANDIDATES:
        km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10)
        labels = km.fit_predict(scaled_features)
        sil = silhouette_score(scaled_features, labels)
        results.append({"k": k, "inertia": km.inertia_, "silhouette": sil})
        logger.info("K=%d: inertia=%.1f silhouette=%.4f", k, km.inertia_, sil)
    return pd.DataFrame(results)


def select_k(k_eval):
    """Picks the K with the highest silhouette score among candidates that
    still produce a business-usable number of segments (>= 3, so the
    result isn't just a binary split, and <= 8 to stay interpretable)."""
    usable = k_eval[(k_eval["k"] >= 3) & (k_eval["k"] <= 8)]
    best = usable.loc[usable["silhouette"].idxmax()]
    return int(best["k"]), float(best["silhouette"])


def name_segments(centers_df, overall_means):
    """Rule-based segment naming, applied AFTER clustering, from each
    cluster's characteristics -- never from the cluster number. Every
    cluster's centroid (already in z-score units, since K-Means was fit on
    standardized features) is summarized into three business axes --
    value, health, engagement -- and named from where it falls on each.
    See docs/data_mining.md for the full decision table and the actual
    resulting names for this run.
    """
    names = {}
    for cluster_id, row in centers_df.iterrows():
        value = np.mean([row["TOTAL_REVENUE"], row["ARR"]])
        health = np.mean([
            row["CUSTOMER_HEALTH_SCORE"], -row["PROJECT_RISK"], -row["SLA_BREACHES"],
            -row["SUPPORT_TICKET_COUNT"], -row["AVERAGE_PAYMENT_DELAY"], row["AVERAGE_SUPPORT_SATISFACTION"],
        ])
        engagement = np.mean([row["AVERAGE_USAGE_SCORE"], row["ACTIVE_SUBSCRIPTIONS"]])

        if value > 0.3 and health > 0.3:
            name = "Strategic"
        elif value > 0.3 and health <= 0.3:
            name = "At Risk (High Value)"
        elif value <= -0.3 and engagement <= -0.3 and health <= -0.3:
            name = "Low Engagement"
        elif health <= -0.3:
            name = "At Risk"
        elif engagement > 0.3 and health > 0:
            name = "Growth"
        else:
            name = "Stable"
        names[cluster_id] = name
    return names


def run():
    df = load_customer_features()
    logger.info("Loaded %d customers from ANALYTICS.VW_CUSTOMER_360", len(df))

    features = prepare_features(df)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(features)

    k_eval = evaluate_k(scaled)
    selected_k, silhouette = select_k(k_eval)
    logger.info("Selected K=%d (silhouette=%.4f) from candidates %s", selected_k, silhouette, K_CANDIDATES)

    kmeans = KMeans(n_clusters=selected_k, random_state=RANDOM_STATE, n_init=10)
    labels = kmeans.fit_predict(scaled)
    distances = kmeans.transform(scaled)
    distance_to_own_centroid = distances[np.arange(len(labels)), labels]

    centers_scaled = pd.DataFrame(kmeans.cluster_centers_, columns=FEATURE_COLUMNS)
    segment_names = name_segments(centers_scaled, features.mean())

    generated_at = run_timestamp()

    segments_df = pd.DataFrame({
        "CUSTOMER_ID": df["CUSTOMER_ID"].values,
        "CLUSTER_ID": labels,
        "SEGMENT_NAME": [segment_names[c] for c in labels],
        "DISTANCE_FROM_CENTROID": distance_to_own_centroid,
        "GENERATED_AT": generated_at,
    })

    raw_features_with_cluster = features.copy()
    raw_features_with_cluster["CLUSTER_ID"] = labels
    profile = raw_features_with_cluster.groupby("CLUSTER_ID").mean()
    counts = raw_features_with_cluster.groupby("CLUSTER_ID").size()

    profile_df = pd.DataFrame({
        "CLUSTER_ID": profile.index,
        "SEGMENT_NAME": [segment_names[c] for c in profile.index],
        "CUSTOMER_COUNT": counts.values,
        "AVG_TOTAL_REVENUE": profile["TOTAL_REVENUE"].values,
        "AVG_ARR": profile["ARR"].values,
        "AVG_ACTIVE_SUBSCRIPTIONS": profile["ACTIVE_SUBSCRIPTIONS"].values,
        "AVG_USAGE_SCORE": profile["AVERAGE_USAGE_SCORE"].values,
        "AVG_SUPPORT_TICKET_COUNT": profile["SUPPORT_TICKET_COUNT"].values,
        "AVG_SLA_BREACHES": profile["SLA_BREACHES"].values,
        "AVG_SUPPORT_SATISFACTION": profile["AVERAGE_SUPPORT_SATISFACTION"].values,
        "AVG_PAYMENT_DELAY": profile["AVERAGE_PAYMENT_DELAY"].values,
        "AVG_OUTSTANDING_AMOUNT": profile["OUTSTANDING_AMOUNT"].values,
        "AVG_PROJECT_RISK": profile["PROJECT_RISK"].values,
        "AVG_CUSTOMER_HEALTH_SCORE": profile["CUSTOMER_HEALTH_SCORE"].values,
        "SELECTED_K": selected_k,
        "SILHOUETTE_SCORE": silhouette,
        "GENERATED_AT": generated_at,
    })

    write_table(segments_df, "DM_CUSTOMER_SEGMENTS")
    write_table(profile_df, "DM_CUSTOMER_CLUSTER_PROFILE")

    logger.info("Segment sizes: %s", segments_df["SEGMENT_NAME"].value_counts().to_dict())
    return {
        "eligible_customers": len(df),
        "clustered_customers": len(segments_df),
        "selected_k": selected_k,
        "silhouette_score": silhouette,
        "k_eval": k_eval,
        "profile_df": profile_df,
    }


if __name__ == "__main__":
    try:
        run()
    except Exception:
        logger.exception("customer_segmentation pipeline failed")
        sys.exit(1)
