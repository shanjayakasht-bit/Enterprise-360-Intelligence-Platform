"""Application settings, loaded once at import time from the project's
existing root .env (the same file etl/, mining/, models/, and
decision_engine/ already use -- no separate/duplicated credential file).

SNOWFLAKE_PASSWORD is loaded as a pydantic SecretStr specifically so it can
never leak through an accidental repr(), log statement, or exception
message -- str(settings) and settings.model_dump() both show
"**********" for it. Use settings.snowflake_password.get_secret_value()
only at the one point a connection is actually opened
(backend/db/snowflake.py).
"""

from pathlib import Path
from typing import List

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT_DIR / ".env"), env_file_encoding="utf-8", extra="ignore")

    # -- Snowflake credentials (required, no defaults -- fails fast if missing) --
    snowflake_account: str
    snowflake_user: str
    snowflake_password: SecretStr
    snowflake_warehouse: str
    snowflake_database: str
    snowflake_role: str

    # -- Application settings (safe, non-secret development defaults) --
    app_name: str = "NEXORA API"
    app_version: str = "1.0.0"
    api_prefix: str = "/api/v1"
    environment: str = "development"

    # CORS: explicit allowlist, never a wildcard -- Phase 6 only needs the
    # local Vite dev server; a real deployment would set this via env var,
    # never by adding "*".
    cors_origins: List[str] = ["http://localhost:5173"]

    # -- Pagination defaults, applied across every paginated endpoint --
    default_page_size: int = 25
    max_page_size: int = 200


settings = Settings()
