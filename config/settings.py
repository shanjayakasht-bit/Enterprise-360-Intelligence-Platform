from datetime import date

PROJECT_NAME = "NEXORA"
RANDOM_SEED = 42
SAMPLE_MODE = True

# Fixed "today" used for every date-relative calculation in generation and validation
# (renewal proximity, deadline proximity, "not in the future" checks, etc.), so both
# sides of the pipeline agree on a single deterministic point in time.
REFERENCE_DATE = date(2026, 9, 4)
