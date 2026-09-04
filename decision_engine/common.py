"""Shared infrastructure for the Phase 5 Decision Intelligence Engine:
Snowflake I/O (reused, unchanged, from mining/common.py's proven, bug-fixed
write path), decision-ID scheme, severity banding, and the confidence-score
formula that ties every decision's stated confidence back to its backing
model's OWN validated accuracy rather than an assumed number.
"""

import json
from pathlib import Path

from mining.common import fetch_dataframe, get_logger, run_timestamp, write_table  # noqa: F401 (re-exported)

ROOT_DIR = Path(__file__).resolve().parent.parent
METRICS_DIR = ROOT_DIR / "artifacts" / "metrics"

ENGINE_VERSION = "phase5-v1"

# ============================================================
# Decision identity
# ============================================================


def make_decision_id(decision_type, entity_type, entity_id):
    """decision_id IS the (decision_type, entity_type, entity_id) triple --
    this is what makes 'no duplicate active decision for identical
    decision_type+entity_type+entity_id' a structural guarantee (the
    DI_DECISIONS primary key) rather than a rule enforced after the fact."""
    return f"{decision_type}_{entity_type}_{entity_id}"


# ============================================================
# Severity bands -- fixed, documented thresholds (see docs/decision_engine.md)
# ============================================================
SEVERITY_BANDS = [(80, "CRITICAL"), (60, "HIGH"), (40, "MEDIUM"), (0, "LOW")]


def severity_from_score(priority_score):
    for threshold, label in SEVERITY_BANDS:
        if priority_score >= threshold:
            return label
    return "LOW"


# ============================================================
# Normalization helpers -- every priority-scoring component is normalized
# to [0, 100] BEFORE being weighted and combined, per the brief.
# ============================================================


def normalize(value, low, high):
    """Linearly maps value from [low, high] to [0, 100], clipped at both
    ends. high < low is treated as an inverted scale (e.g. "fewer days
    remaining = more urgent")."""
    if value is None:
        return 0.0
    if high == low:
        return 0.0
    pct = (value - low) / (high - low)
    return max(0.0, min(100.0, pct * 100.0))


# Segment tiers used as a "strategic importance" signal wherever a decision
# is tied to a specific customer -- a fixed, documented business ranking
# (largest accounts first), independent of any single transaction's dollar
# value (which is already captured separately as the impact component).
SEGMENT_STRATEGIC_WEIGHT = {"Enterprise": 100.0, "Mid-Market": 66.0, "Smb": 33.0, "SMB": 33.0, "Startup": 15.0}


def strategic_importance(segment):
    return SEGMENT_STRATEGIC_WEIGHT.get(segment, 40.0)  # unknown segment: neutral default


# ============================================================
# Confidence score -- tied to the backing model's OWN validated accuracy,
# never an assumed/flat number. An ROC-AUC of 0.5 (chance level, no better
# than a coin flip) maps to confidence 0; an ROC-AUC of 1.0 (perfect) maps
# to confidence 100; linear in between. This is deliberately harsh on the
# two Phase 4 models that validated at chance level (customer churn 0.481,
# project risk 0.520) -- their decisions carry LOW confidence_score by
# construction, honestly reflecting docs/predictive_analytics.md's findings
# rather than presenting every ML-backed decision as equally trustworthy.
# ============================================================


def confidence_from_auc(auc):
    if auc is None:
        return 0.0
    return max(0.0, min(100.0, (auc - 0.5) / 0.5 * 100.0))


_metrics_cache = {}


def load_model_metrics(name):
    """Loads artifacts/metrics/<name>.json (written by the Phase 4 model
    pipelines). Cached per process since every decision of a given type
    reads the same file."""
    if name in _metrics_cache:
        return _metrics_cache[name]
    path = METRICS_DIR / f"{name}.json"
    if not path.exists():
        _metrics_cache[name] = None
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    _metrics_cache[name] = data
    return data


def model_confidence(model_metrics_name):
    """Confidence score for decisions backed by a given Phase 4 model,
    derived from that model's own selected-algorithm ROC-AUC."""
    metrics = load_model_metrics(model_metrics_name)
    if not metrics:
        return 0.0
    selected = metrics["selected_algorithm"]
    auc = metrics["algorithms_compared"][selected]["roc_auc"]
    return round(confidence_from_auc(auc), 1)
