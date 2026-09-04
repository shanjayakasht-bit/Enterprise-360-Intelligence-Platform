"""Deterministic, feature-based contributing-signal explanations.

No generative/LLM text anywhere in this module -- every explanation is a
templated sentence built from an actual observed feature value compared
against a fixed, documented threshold (see the *_SIGNAL_RULES lists below).
Signals are always phrased as "primary contributing signals", never as a
definitive or causal explanation -- correlation is not claimed to be
causation anywhere in this engine.

Each rule is a dict: {column, direction, threshold, label, unit}.
  - direction 'high' fires when row[column] > threshold (worse-when-higher)
  - direction 'low'  fires when row[column] < threshold (worse-when-lower)
The magnitude of the breach (how far past the threshold, as a fraction of
the threshold) ranks which signals are surfaced first when there are more
triggered signals than the cap.
"""

CUSTOMER_SIGNAL_RULES = [
    {"column": "PRODUCT_USAGE_SCORE", "direction": "low", "threshold": 40, "label": "Product usage score is low"},
    {"column": "ENGAGEMENT_SCORE", "direction": "low", "threshold": 40, "label": "Engagement score is low"},
    {"column": "SATISFACTION_SCORE", "direction": "low", "threshold": 60, "label": "Customer satisfaction is below acceptable range"},
    {"column": "OPEN_TICKET_COUNT", "direction": "high", "threshold": 3, "label": "Unresolved support tickets are elevated"},
    {"column": "AVG_PAYMENT_DELAY_DAYS", "direction": "high", "threshold": 5, "label": "Recent payments are trending late"},
    {"column": "OUTSTANDING_AMOUNT", "direction": "high", "threshold": 1, "label": "Outstanding balance is present"},
    {"column": "DAYS_TO_RENEWAL", "direction": "low", "threshold": 90, "label": "Renewal date is approaching soon"},
]

PROJECT_SIGNAL_RULES = [
    {"column": "COMPLETION_PCT", "direction": "low", "threshold": 40, "label": "Completion percentage is behind expectation"},
    {"column": "BUDGET_UTILIZATION_PCT", "direction": "high", "threshold": 85, "label": "Budget utilization is high"},
    {"column": "COST_OVERRUN_PCT", "direction": "high", "threshold": 10, "label": "Project is running over cost"},
    {"column": "COST_VARIANCE", "direction": "high", "threshold": 1, "label": "Actual cost exceeds budget"},
    {"column": "DAYS_TO_DEADLINE", "direction": "low", "threshold": 14, "label": "Planned deadline is imminent or passed"},
]

PAYMENT_SIGNAL_RULES = [
    {"column": "AVG_PAYMENT_DELAY_DAYS", "direction": "high", "threshold": 5, "label": "Customer's recent average payment delay is elevated"},
    {"column": "OUTSTANDING_AMOUNT", "direction": "high", "threshold": 1, "label": "Customer carries an existing outstanding balance"},
    {"column": "TOTAL_AMOUNT", "direction": "high", "threshold": 50000, "label": "Invoice value is large"},
]


def _breach_magnitude(value, rule):
    threshold = rule["threshold"]
    if rule["direction"] == "low":
        return max(0.0, (threshold - value) / threshold) if threshold else 0.0
    return max(0.0, (value - threshold) / threshold) if threshold else 0.0


def evaluate_signals(row, rules, max_signals=4):
    """Returns an ordered (most-severe-breach-first) list of (label, detail)
    tuples for every rule that fires against this row. row is a dict-like
    (pandas Series or dict) of feature values; missing/NaN values are
    treated as not triggering (never fabricated)."""
    triggered = []
    for rule in rules:
        value = row.get(rule["column"])
        if value is None:
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        fires = (value < rule["threshold"]) if rule["direction"] == "low" else (value > rule["threshold"])
        if fires:
            detail = f"{rule['label']} (observed {value:.1f} vs. threshold {rule['threshold']})"
            triggered.append((_breach_magnitude(value, rule), rule["label"], detail))

    triggered.sort(key=lambda t: -t[0])
    return [(label, detail) for _, label, detail in triggered[:max_signals]]


def summarize_signals(signals):
    """Builds the why_it_happened sentence from a list of (label, detail)
    tuples -- explicitly hedged language, never a causal claim."""
    if not signals:
        return "No individual feature crossed a concerning threshold; this decision is driven primarily by the model-predicted probability itself."
    details = "; ".join(detail for _, detail in signals)
    return f"Primary contributing signals (not claimed as definitive causes): {details}."
