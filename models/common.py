"""Shared helpers for the Phase 4 predictive analytics pipelines: Snowflake
I/O (reused from mining/common.py's proven, bug-fixed write path), model
artifact persistence, and metrics persistence.
"""

import json
from pathlib import Path

import joblib

from mining.common import fetch_dataframe, get_logger, run_timestamp, write_table  # noqa: F401 (re-exported)

ROOT_DIR = Path(__file__).resolve().parent.parent
ARTIFACTS_MODELS_DIR = ROOT_DIR / "artifacts" / "models"
ARTIFACTS_METRICS_DIR = ROOT_DIR / "artifacts" / "metrics"

MODEL_VERSION = "phase4-v1"
RANDOM_STATE = 42


def save_model(model, name):
    """Persists a fitted model/scaler/pipeline object to artifacts/models/
    as a .joblib file, gitignored (may be large). Returns the path."""
    ARTIFACTS_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS_MODELS_DIR / f"{name}.joblib"
    joblib.dump(model, path)
    return path


def save_metrics(metrics, name):
    """Persists a JSON-serializable metrics dict to artifacts/metrics/ --
    small, human-readable, and tracked in git (unlike the model binaries)."""
    ARTIFACTS_METRICS_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS_METRICS_DIR / f"{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, default=str)
    return path
