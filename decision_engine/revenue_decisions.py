"""Generates REVENUE_OPPORTUNITY decisions -- four distinct strategic
signal subtypes, each capped to a small number of genuinely material
findings (never one decision per raw data row, to avoid inflating the
decision count -- see docs/decision_engine.md).

Confidence scoring here is deliberately DIFFERENT from the classifier-
backed domains: these are descriptive/statistical findings computed
directly from observed transactional data, not probability estimates from
a trained classifier, so confidence_score reflects data-groundedness (a
fixed, documented 70 for descriptive findings) or, for the forecast
subtype specifically, the Phase 4 forecast's own backtested accuracy
(100 - MAPE), never fabricated certainty about the future.
"""

from decision_engine.common import (
    fetch_dataframe, get_logger, load_model_metrics, make_decision_id,
    normalize, run_timestamp, strategic_importance,
)
from decision_engine.priority_scoring import compute_priority
from decision_engine.recommendations import revenue_recommendations

logger = get_logger("revenue_decisions")

DESCRIPTIVE_CONFIDENCE = 70.0  # data-grounded (not model-predicted) -- see file header

FORECAST_WIDTH_THRESHOLD = 0.40  # (upper-lower)/predicted -- flag when forecast uncertainty exceeds 40% of the point estimate
CROSS_SELL_MIN_LIFT = 1.3
CROSS_SELL_MAX_DECISIONS = 3
CONCENTRATION_TOP_N = 10
CONCENTRATION_THRESHOLD_PCT = 30.0  # flag when the top N customers hold > 30% of total ARR


def _forecast_downside():
    forecast = fetch_dataframe("SELECT forecast_date, predicted_revenue, lower_bound, upper_bound FROM ANALYTICS.ML_REVENUE_FORECAST ORDER BY forecast_date")
    if forecast.empty:
        return []
    last = forecast.iloc[-1]
    predicted, lower, upper = float(last["PREDICTED_REVENUE"]), float(last["LOWER_BOUND"]), float(last["UPPER_BOUND"])
    width_pct = (upper - lower) / predicted if predicted else 0.0
    if width_pct < FORECAST_WIDTH_THRESHOLD:
        return []

    metrics = load_model_metrics("revenue_forecast")
    mape = metrics["methods_compared"][metrics["selected_method"]]["mape_pct"] if metrics else None
    confidence = round(max(0.0, 100.0 - mape), 1) if mape is not None else DESCRIPTIVE_CONFIDENCE
    downside_value = predicted - lower

    risk_component = normalize(width_pct, FORECAST_WIDTH_THRESHOLD, 1.0)
    impact_component = normalize(downside_value, 0, predicted)
    urgency_component = 80.0  # nearest forecasted month
    strategic_component = 90.0  # enterprise-wide revenue signal

    priority_score = compute_priority("REVENUE_OPPORTUNITY", risk_component, impact_component, urgency_component, strategic_component)
    actions = revenue_recommendations("FORECAST_DOWNSIDE")

    return [{
        "DECISION_ID": make_decision_id("REVENUE_OPPORTUNITY", "ENTERPRISE", f"FORECAST_{last['FORECAST_DATE']}"),
        "DECISION_TYPE": "REVENUE_OPPORTUNITY",
        "ENTITY_TYPE": "ENTERPRISE",
        "ENTITY_ID": f"FORECAST_{last['FORECAST_DATE']}",
        "TITLE": f"Revenue forecast uncertainty for {last['FORECAST_DATE']}",
        "SUMMARY": f"The {last['FORECAST_DATE']} revenue forecast carries a wide confidence interval (${lower:,.0f}-${upper:,.0f}); the downside scenario is ${downside_value:,.0f} below the point estimate.",
        "SEVERITY": None,
        "PRIORITY_SCORE": priority_score,
        "WHAT_HAPPENED": f"The Phase 4 revenue forecast for {last['FORECAST_DATE']} has a {width_pct:.0%}-wide confidence interval relative to its point estimate.",
        "WHY_IT_HAPPENED": f"Primary contributing signal (not claimed as a definitive cause): the underlying monthly revenue series has grown ~800x over 3 years with a backtested forecast MAPE of {mape:.1f}%, so near-term forecasts carry genuine, quantified uncertainty." if mape is not None else "Primary contributing signal: forecast confidence interval width exceeds the documented threshold.",
        "PREDICTED_OUTCOME": f"Point estimate ${predicted:,.0f}; plausible range ${lower:,.0f} to ${upper:,.0f}",
        "BUSINESS_IMPACT_TYPE": "REVENUE_DOWNSIDE_RISK",
        "BUSINESS_IMPACT_VALUE": downside_value,
        "CONFIDENCE_SCORE": confidence,
        "RECOMMENDED_ACTION_1": actions[0] if len(actions) > 0 else None,
        "RECOMMENDED_ACTION_2": actions[1] if len(actions) > 1 else None,
        "RECOMMENDED_ACTION_3": actions[2] if len(actions) > 2 else None,
        "RECOMMENDED_ACTION_4": None,
        "RECOMMENDED_ACTION_5": None,
        "STATUS": "NEW",
        "GENERATED_AT": run_timestamp(),
    }]


def _regional_growth():
    regions = fetch_dataframe("SELECT region_name, customer_count, revenue, average_health_score FROM ANALYTICS.VW_REGION_PERFORMANCE WHERE customer_count > 0")
    if regions.empty:
        return []
    regions["REVENUE_PER_CUSTOMER"] = regions["REVENUE"].astype(float) / regions["CUSTOMER_COUNT"].astype(float)
    top = regions.sort_values("REVENUE_PER_CUSTOMER", ascending=False).head(1).iloc[0]

    revenue = float(top["REVENUE"])
    risk_component = 60.0  # "signal strength": a real, above-peer efficiency signal, moderate by nature (not a risk)
    impact_component = normalize(revenue, 0, float(regions["REVENUE"].astype(float).max()))
    urgency_component = 30.0  # strategic/planning-horizon, not immediate
    strategic_component = 80.0

    priority_score = compute_priority("REVENUE_OPPORTUNITY", risk_component, impact_component, urgency_component, strategic_component)
    actions = revenue_recommendations("REGIONAL_GROWTH")

    return [{
        "DECISION_ID": make_decision_id("REVENUE_OPPORTUNITY", "REGION", top["REGION_NAME"]),
        "DECISION_TYPE": "REVENUE_OPPORTUNITY",
        "ENTITY_TYPE": "REGION",
        "ENTITY_ID": top["REGION_NAME"],
        "TITLE": f"Growth opportunity: {top['REGION_NAME']}",
        "SUMMARY": f"{top['REGION_NAME']} generates the highest revenue-per-customer (${top['REVENUE_PER_CUSTOMER']:,.0f}) of any region, with {int(top['CUSTOMER_COUNT'])} customers and ${revenue:,.0f} total revenue.",
        "SEVERITY": None,
        "PRIORITY_SCORE": priority_score,
        "WHAT_HAPPENED": f"{top['REGION_NAME']} shows the highest revenue-per-customer efficiency across all regions.",
        "WHY_IT_HAPPENED": f"Primary contributing signal (not claimed as a definitive cause): revenue-per-customer of ${top['REVENUE_PER_CUSTOMER']:,.0f}, above every other region.",
        "PREDICTED_OUTCOME": None,
        "BUSINESS_IMPACT_TYPE": "REVENUE_OPPORTUNITY",
        "BUSINESS_IMPACT_VALUE": revenue,
        "CONFIDENCE_SCORE": DESCRIPTIVE_CONFIDENCE,
        "RECOMMENDED_ACTION_1": actions[0] if len(actions) > 0 else None,
        "RECOMMENDED_ACTION_2": actions[1] if len(actions) > 1 else None,
        "RECOMMENDED_ACTION_3": actions[2] if len(actions) > 2 else None,
        "RECOMMENDED_ACTION_4": None,
        "RECOMMENDED_ACTION_5": None,
        "STATUS": "NEW",
        "GENERATED_AT": run_timestamp(),
    }]


def _service_cross_sell():
    rules = fetch_dataframe(f"""
        SELECT antecedent, consequent, support, confidence, lift, transaction_count
        FROM ANALYTICS.DM_SERVICE_ASSOCIATIONS
        WHERE lift >= {CROSS_SELL_MIN_LIFT}
        ORDER BY lift DESC
        LIMIT {CROSS_SELL_MAX_DECISIONS}
    """)
    if rules.empty:
        return []

    service_perf = fetch_dataframe("SELECT service_name, revenue, deal_count, arr, subscriptions FROM ANALYTICS.VW_SERVICE_PERFORMANCE")
    service_perf = service_perf.set_index(service_perf["SERVICE_NAME"].str.strip())

    decisions = []
    max_lift = float(rules["LIFT"].max())
    for _, r in rules.iterrows():
        consequent_name = r["CONSEQUENT"].split(":", 1)[-1].strip()
        avg_value = 0.0
        if consequent_name in service_perf.index:
            perf = service_perf.loc[consequent_name]
            if float(perf.get("SUBSCRIPTIONS", 0) or 0) > 0:
                avg_value = float(perf["ARR"]) / float(perf["SUBSCRIPTIONS"])
            elif float(perf.get("DEAL_COUNT", 0) or 0) > 0:
                avg_value = float(perf["REVENUE"]) / float(perf["DEAL_COUNT"])

        opportunity_value = avg_value * float(r["TRANSACTION_COUNT"])

        risk_component = normalize(float(r["LIFT"]), CROSS_SELL_MIN_LIFT, max_lift)
        impact_component = normalize(opportunity_value, 0, opportunity_value if opportunity_value > 0 else 1)
        urgency_component = 30.0
        strategic_component = 70.0
        priority_score = compute_priority("REVENUE_OPPORTUNITY", risk_component, impact_component, urgency_component, strategic_component)

        actions = revenue_recommendations("SERVICE_CROSS_SELL")
        entity_id = f"{r['ANTECEDENT']}_TO_{r['CONSEQUENT']}"

        decisions.append({
            "DECISION_ID": make_decision_id("REVENUE_OPPORTUNITY", "SERVICE", entity_id),
            "DECISION_TYPE": "REVENUE_OPPORTUNITY",
            "ENTITY_TYPE": "SERVICE",
            "ENTITY_ID": entity_id,
            "TITLE": f"Cross-sell opportunity: {r['ANTECEDENT']} -> {r['CONSEQUENT']}",
            "SUMMARY": f"Customers with {r['ANTECEDENT']} are {r['LIFT']:.2f}x more likely to also have {r['CONSEQUENT']} ({r['CONFIDENCE']:.0%} confidence, {int(r['TRANSACTION_COUNT'])} customers).",
            "SEVERITY": None,
            "PRIORITY_SCORE": priority_score,
            "WHAT_HAPPENED": f"Association mining (Phase 3) found {r['ANTECEDENT']} and {r['CONSEQUENT']} co-occur {r['LIFT']:.2f}x more than chance.",
            "WHY_IT_HAPPENED": f"Primary contributing signal (not claimed as a definitive cause): support={r['SUPPORT']:.3f}, confidence={r['CONFIDENCE']:.0%}, lift={r['LIFT']:.2f} across {int(r['TRANSACTION_COUNT'])} customers.",
            "PREDICTED_OUTCOME": None,
            "BUSINESS_IMPACT_TYPE": "REVENUE_OPPORTUNITY",
            "BUSINESS_IMPACT_VALUE": max(0.0, opportunity_value),
            "CONFIDENCE_SCORE": DESCRIPTIVE_CONFIDENCE,
            "RECOMMENDED_ACTION_1": actions[0] if len(actions) > 0 else None,
            "RECOMMENDED_ACTION_2": actions[1] if len(actions) > 1 else None,
            "RECOMMENDED_ACTION_3": actions[2] if len(actions) > 2 else None,
            "RECOMMENDED_ACTION_4": None,
            "RECOMMENDED_ACTION_5": None,
            "STATUS": "NEW",
            "GENERATED_AT": run_timestamp(),
        })
    return decisions


def _revenue_concentration():
    customers = fetch_dataframe("SELECT customer_id, company_name, segment, arr FROM ANALYTICS.VW_CUSTOMER_360 WHERE arr > 0 ORDER BY arr DESC")
    if customers.empty:
        return []
    total_arr = float(customers["ARR"].astype(float).sum())
    top_n = customers.head(CONCENTRATION_TOP_N)
    top_arr = float(top_n["ARR"].astype(float).sum())
    concentration_pct = (top_arr / total_arr * 100.0) if total_arr else 0.0
    if concentration_pct < CONCENTRATION_THRESHOLD_PCT:
        return []

    risk_component = normalize(concentration_pct, CONCENTRATION_THRESHOLD_PCT, 100.0)
    impact_component = normalize(top_arr, 0, total_arr)
    urgency_component = 40.0
    strategic_component = 90.0
    priority_score = compute_priority("REVENUE_OPPORTUNITY", risk_component, impact_component, urgency_component, strategic_component)
    actions = revenue_recommendations("REVENUE_CONCENTRATION")

    return [{
        "DECISION_ID": make_decision_id("REVENUE_OPPORTUNITY", "ENTERPRISE", "REVENUE_CONCENTRATION"),
        "DECISION_TYPE": "REVENUE_OPPORTUNITY",
        "ENTITY_TYPE": "ENTERPRISE",
        "ENTITY_ID": "REVENUE_CONCENTRATION",
        "TITLE": f"Revenue concentration risk: top {CONCENTRATION_TOP_N} customers",
        "SUMMARY": f"The top {CONCENTRATION_TOP_N} customers by ARR represent {concentration_pct:.1f}% of total ARR (${top_arr:,.0f} of ${total_arr:,.0f}).",
        "SEVERITY": None,
        "PRIORITY_SCORE": priority_score,
        "WHAT_HAPPENED": f"The top {CONCENTRATION_TOP_N} customers by ARR account for {concentration_pct:.1f}% of total recurring revenue.",
        "WHY_IT_HAPPENED": f"Primary contributing signal (not claimed as a definitive cause): revenue concentration of {concentration_pct:.1f}% among the top {CONCENTRATION_TOP_N} of {len(customers)} ARR-bearing customers exceeds the {CONCENTRATION_THRESHOLD_PCT:.0f}% documented threshold.",
        "PREDICTED_OUTCOME": None,
        "BUSINESS_IMPACT_TYPE": "REVENUE_CONCENTRATION_EXPOSURE",
        "BUSINESS_IMPACT_VALUE": top_arr,
        "CONFIDENCE_SCORE": DESCRIPTIVE_CONFIDENCE,
        "RECOMMENDED_ACTION_1": actions[0] if len(actions) > 0 else None,
        "RECOMMENDED_ACTION_2": actions[1] if len(actions) > 1 else None,
        "RECOMMENDED_ACTION_3": actions[2] if len(actions) > 2 else None,
        "RECOMMENDED_ACTION_4": None,
        "RECOMMENDED_ACTION_5": None,
        "STATUS": "NEW",
        "GENERATED_AT": run_timestamp(),
    }]


def generate():
    decisions = []
    decisions += _forecast_downside()
    decisions += _regional_growth()
    decisions += _service_cross_sell()
    decisions += _revenue_concentration()
    logger.info("Generated %d revenue opportunity decisions", len(decisions))
    return decisions
