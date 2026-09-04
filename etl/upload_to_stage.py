"""Uploads the validated data/raw/ CSVs to the NEXORA_RAW_STAGE internal stage.
Run as:

    python -m etl.upload_to_stage

Does not read or modify the local CSVs beyond uploading them; data/raw/ is
left untouched. Re-running is safe: OVERWRITE=TRUE replaces the same
deterministic staged filenames rather than piling up duplicates.
"""

import logging
import sys
from pathlib import Path

from etl.snowflake_connection import DATABASE, RAW_SCHEMA, RAW_TABLES, STAGE_NAME, get_connection

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data" / "raw"
STAGE_PATH = f"@{DATABASE}.{RAW_SCHEMA}.{STAGE_NAME}"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nexora.upload_to_stage")


def upload_all():
    conn = get_connection()
    results = []
    try:
        cur = conn.cursor()
        for _, filename in RAW_TABLES:
            local_path = DATA_DIR / filename
            if not local_path.exists():
                logger.error("MISSING local file, skipping: %s", local_path)
                results.append((filename, False))
                continue

            # AUTO_COMPRESS + OVERWRITE keeps the staged filename deterministic
            # (<name>.csv.gz) across reruns instead of accumulating copies.
            put_sql = (
                f"PUT 'file://{local_path.as_posix()}' {STAGE_PATH} "
                "AUTO_COMPRESS=TRUE OVERWRITE=TRUE"
            )
            logger.info("Uploading %s -> %s", local_path.name, STAGE_PATH)
            cur.execute(put_sql)
            row = cur.fetchone()
            status = row[6] if row else "UNKNOWN"
            target = row[1] if row else "?"
            ok = status in ("UPLOADED", "SKIPPED")
            logger.info("  %s: status=%s target=%s", local_path.name, status, target)
            results.append((filename, ok))
    finally:
        conn.close()

    succeeded = sum(1 for _, ok in results if ok)
    failed = [f for f, ok in results if not ok]
    logger.info("Upload complete: %d/%d files uploaded to %s", succeeded, len(results), STAGE_PATH)
    if failed:
        logger.error("Failed uploads: %s", ", ".join(failed))
        return False
    return True


if __name__ == "__main__":
    ok = upload_all()
    sys.exit(0 if ok else 1)
