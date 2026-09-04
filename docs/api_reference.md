# NEXORA Phase 6 — FastAPI Backend Reference

## Architecture

```
React (future, Phase 7+)
      │  HTTP/JSON only -- never connects to Snowflake directly
      ▼
FastAPI app (backend/main.py)
      │
      ├─ routers/      thin: parse query params, call a service, return a Pydantic model
      ├─ services/      orchestration: build SQL via db/queries.py, call db/snowflake.py, shape the response
      ├─ db/queries.py   centralized, reviewable SQL -- every filter VALUE is parameterized (%s), never
      │                  string-interpolated; the one caller-influenced non-value token (revenue "period"
      │                  grain) is resolved through a fixed allowlist dict, never a raw expression
      ├─ db/snowflake.py  connection + execute_query() -- opens one connection per call, converts every
      │                  Decimal/date/datetime/numpy value to a JSON-safe type, logs operation+duration,
      │                  never lets a raw Snowflake exception reach the client
      ├─ models/         typed Pydantic response schemas -- nothing returns a bare cursor tuple
      └─ core/           settings (pydantic-settings, reads the project's existing root .env),
                         structured logging, and the NexoraAPIError hierarchy + handlers
      │
      ▼
Snowflake NEXORA_DB (ANALYTICS/CORE -- read-only from this API's perspective)
```

Every route is **read-only**: nothing in `backend/` issues `INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`/`MERGE` against Snowflake, retrains or re-scores a Phase 4 model, or executes a Phase 5 recommended action. The API's entire job is to serve what Phases 2D-5 already computed.

## Configuration

`backend/core/config.py` loads the **same** root `.env` every other part of this project already uses (`SNOWFLAKE_ACCOUNT/USER/PASSWORD/WAREHOUSE/DATABASE/ROLE`) via `pydantic-settings`, plus non-secret application defaults (`APP_NAME=NEXORA API`, `APP_VERSION=1.0.0`, `API_PREFIX=/api/v1`, `CORS_ORIGINS=["http://localhost:5173"]`). `SNOWFLAKE_PASSWORD` is typed `SecretStr`, so it renders as `**********` in any accidental `repr()`/log/exception — verified by `tests/backend/test_health.py::test_health_never_exposes_credentials` and manual check #13 in `backend/validate_api.py`.

## Running the server

```
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

- Swagger UI: **http://127.0.0.1:8000/docs**
- ReDoc: **http://127.0.0.1:8000/redoc**
- OpenAPI schema: **http://127.0.0.1:8000/openapi.json**

## Endpoint list

All paths are prefixed `/api/v1` (except `/docs`, `/redoc`, `/openapi.json`, and `/`).

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness + Snowflake connectivity probe |
| GET | `/overview` | Executive KPI snapshot |
| GET | `/customers` | Paginated, filterable customer list |
| GET | `/customers/{customer_id}` | Full Customer 360 detail |
| GET | `/revenue/trends` | Aggregated revenue over time |
| GET | `/revenue/forecast` | Forecast + recent historical context |
| GET | `/projects/risk` | Paginated, filterable project risk list |
| GET | `/projects/{project_id}` | Full project detail |
| GET | `/support` | Aggregated support metrics |
| GET | `/predictions/customers` | Raw `ML_CUSTOMER_RISK` rows, paginated |
| GET | `/predictions/projects` | Raw `ML_PROJECT_RISK` rows, paginated |
| GET | `/predictions/payments` | Raw `ML_PAYMENT_DELAY` rows, paginated |
| GET | `/predictions/revenue` | Raw `ML_REVENUE_FORECAST` rows |
| GET | `/decisions` | Paginated, filterable decision list (priority-sorted) |
| GET | `/decisions/summary` | Executive decision-backlog summary |
| GET | `/decisions/{decision_id}` | Full decision card |
| GET | `/metadata/regions` | Region names (filter dropdown) |
| GET | `/metadata/services` | Service name + category pairs |
| GET | `/metadata/segments` | Distinct customer segments |
| GET | `/metadata/departments` | Department names |

### Parameters and Snowflake sources, per endpoint

**`GET /health`** — no params. Source: a single `SELECT 1` (connectivity only, not a real table).

**`GET /overview`** — no params. Source: `ANALYTICS.VW_EXECUTIVE_OVERVIEW` cross-joined with `ANALYTICS.DI_EXECUTIVE_SUMMARY` (both single-row tables) in one query.

**`GET /customers`** — `page`, `page_size` (1-200), `region`, `segment` (business tier: Enterprise/Mid-Market/SMB/Startup), `risk_level` (Low/Medium/High), `search` (matches company name or customer_id). Source: `ANALYTICS.VW_CUSTOMER_360` LEFT JOIN `ANALYTICS.ML_CUSTOMER_RISK` LEFT JOIN `ANALYTICS.DM_CUSTOMER_SEGMENTS`.

**`GET /customers/{customer_id}`** — path param. 404 if not found. Source: `VW_CUSTOMER_360` + `VW_CUSTOMER_HEALTH` + `ML_CUSTOMER_RISK` + `DM_CUSTOMER_SEGMENTS` + `DI_DECISIONS` (active decisions for this customer).

**`GET /revenue/trends`** — `period` (daily/monthly/quarterly/yearly, default monthly), `region`, `segment`, `service` (accepted but currently a no-op — see Limitations). Source: `ANALYTICS.VW_REVENUE_TRENDS`, aggregated in Snowflake to the requested grain.

**`GET /revenue/forecast`** — no params. Source: `ANALYTICS.ML_REVENUE_FORECAST` (the 3-row forecast) plus the last 12 months from `VW_REVENUE_TRENDS` as historical context.

**`GET /projects/risk`** — `page`, `page_size`, `risk_level`, `department`, `customer_id`. Source: `ANALYTICS.VW_PROJECT_RISK` LEFT JOIN `ANALYTICS.ML_PROJECT_RISK`.

**`GET /projects/{project_id}`** — path param. 404 if not found. Source: `VW_PROJECT_RISK` + `ML_PROJECT_RISK` + `DI_DECISIONS`.

**`GET /support`** — `priority`, `status`, `customer_id` (all optional; applied as WHERE before aggregation, so the response is always the aggregate of the *filtered* ticket set). Source: `ANALYTICS.VW_SUPPORT_HEALTH`, aggregated in Snowflake (never pulls the 40,000 ticket rows into Python).

**`GET /predictions/customers|projects|payments`** — `page`, `page_size`, `risk_level`. Straight paginated reads of `ML_CUSTOMER_RISK` / `ML_PROJECT_RISK` / `ML_PAYMENT_DELAY`, ordered by probability descending.

**`GET /predictions/revenue`** — no params. All 3 rows of `ML_REVENUE_FORECAST` (small enough to return unpaginated).

**`GET /decisions`** — `page`, `page_size`, `severity` (LOW/MEDIUM/HIGH/CRITICAL), `decision_type`, `entity_type`, `status`. Default sort: `priority_score DESC, generated_at DESC` (matches the brief exactly). Source: `ANALYTICS.DI_DECISIONS`.

**`GET /decisions/summary`** — no params. Source: `ANALYTICS.DI_EXECUTIVE_SUMMARY`.

**`GET /decisions/{decision_id}`** — path param. 404 if not found. Source: `DI_DECISIONS`.

**`GET /metadata/*`** — no params. Sources: `CORE.DIM_REGION`, `CORE.DIM_SERVICE`, `ANALYTICS.VW_CUSTOMER_360` (distinct segments), `CORE.DIM_DEPARTMENT`.

## Response examples

`GET /api/v1/health`
```json
{"status": "healthy", "service": "NEXORA API", "snowflake": "connected", "version": "1.0.0"}
```

`GET /api/v1/customers?page=1&page_size=2` (truncated)
```json
{
  "items": [
    {"customer_id": "CUST000001", "company_name": "Odom PLC", "segment": "Mid-Market",
     "region": "Europe", "total_revenue": 12345.67, "risk_level": "Medium", "cluster_segment_name": "Stable"}
  ],
  "page_info": {"page": 1, "page_size": 2, "total_items": 5000, "total_pages": 2500}
}
```

`GET /api/v1/decisions?page_size=1`
```json
{
  "items": [{
    "decision_id": "PAYMENT_COLLECTION_INVOICE_INV028101",
    "decision_type": "PAYMENT_COLLECTION", "entity_type": "INVOICE", "entity_id": "INV028101",
    "title": "Collection priority: invoice INV028101 for Carr Group",
    "severity": "CRITICAL", "priority_score": 92.51,
    "what_happened": "Invoice INV028101 for Carr Group is unpaid with an outstanding balance, 287 days past due date.",
    "why_it_happened": "Primary contributing signals (not claimed as definitive causes): ...",
    "predicted_outcome": "Model-estimated probability this invoice is/becomes a late payment: 83%",
    "business_impact": {"type": "INVOICE_AT_RISK", "value": 1063790.21},
    "confidence": 44.3,
    "recommended_actions": ["Send payment reminder to customer", "Contact account manager before escalating", "..."],
    "status": "NEW", "generated_at": "2026-09-04T20:16:22.162376"
  }],
  "page_info": {"page": 1, "page_size": 1, "total_items": 439, "total_pages": 439}
}
```

## Error responses

Every error is `{"error": "<code>", "message": "<safe text>"}` — never a raw Snowflake exception, SQL fragment, or connection string.

| Status | `error` | When |
|---|---|---|
| 400 | `invalid_filter` | An unsupported filter value (e.g. `risk_level=Extreme`) |
| 404 | `resource_not_found` | Unknown `customer_id` / `project_id` / `decision_id` |
| 500 | `database_error` | A Snowflake query failed (logged server-side with detail; client sees only this generic message) |
| 500 | `internal_error` | Any other unhandled exception (caught by a catch-all handler, logged with full traceback server-side only) |

## Logging

Every request gets one summary line via `backend/main.py`'s middleware: `METHOD path -> status (duration_ms)`. Every Snowflake query gets one line via `backend/db/snowflake.py`: `[operation] N rows in duration_ms`. Neither ever logs the password, a connection string, or a full row payload — only counts, durations, and the named "operation" (e.g. `customers_list`), never the SQL text or the data itself.

## Pagination strategy

Every list endpoint uses `LIMIT`/`OFFSET` computed in `backend/utils/pagination.py`, with a matching `COUNT(*)` query (same filters) run in Snowflake for `total_items` — no endpoint ever loads a full table into Python to paginate in memory. Default page size 25, max 200 (`backend/core/config.py`).

## Pydantic models and type conversion

Every response is a typed Pydantic model (`backend/models/*.py`) — no route returns a bare cursor tuple or an untyped dict from Snowflake. `backend/utils/serialization.py::sanitize_value` converts every `Decimal` (whole → `int`, fractional → `float`), and defensively handles any numpy scalar (`.item()`) before a row ever reaches a Pydantic model; `date`/`datetime` pass through natively (both FastAPI and Pydantic serialize them to ISO 8601 automatically).

## Frontend component → API endpoint → Snowflake source

| Frontend Component | API Endpoint | Snowflake Source |
|---|---|---|
| Top KPI Cards | `/api/v1/overview` | `VW_EXECUTIVE_OVERVIEW` + `DI_EXECUTIVE_SUMMARY` |
| Customer List / Search | `/api/v1/customers` | `VW_CUSTOMER_360` + `ML_CUSTOMER_RISK` + `DM_CUSTOMER_SEGMENTS` |
| Customer 360 Page | `/api/v1/customers/{id}` | `VW_CUSTOMER_360` + `VW_CUSTOMER_HEALTH` + `ML_CUSTOMER_RISK` + `DM_CUSTOMER_SEGMENTS` + `DI_DECISIONS` |
| Revenue Trend Chart | `/api/v1/revenue/trends` | `VW_REVENUE_TRENDS` |
| Revenue Forecast Chart | `/api/v1/revenue/forecast` | `ML_REVENUE_FORECAST` + `VW_REVENUE_TRENDS` |
| Project Risk Board | `/api/v1/projects/risk` | `VW_PROJECT_RISK` + `ML_PROJECT_RISK` |
| Project Detail Page | `/api/v1/projects/{id}` | `VW_PROJECT_RISK` + `ML_PROJECT_RISK` + `DI_DECISIONS` |
| Support Health Widget | `/api/v1/support` | `VW_SUPPORT_HEALTH` |
| ML Risk Tables (raw) | `/api/v1/predictions/*` | `ML_CUSTOMER_RISK` / `ML_PROJECT_RISK` / `ML_PAYMENT_DELAY` / `ML_REVENUE_FORECAST` |
| **Decision Engine Panel** | `/api/v1/decisions` | `DI_DECISIONS` |
| Decision Detail Modal | `/api/v1/decisions/{id}` | `DI_DECISIONS` |
| Executive Decision Summary | `/api/v1/decisions/summary` | `DI_EXECUTIVE_SUMMARY` |
| Filter Dropdowns | `/api/v1/metadata/*` | `DIM_REGION` / `DIM_SERVICE` / `VW_CUSTOMER_360` / `DIM_DEPARTMENT` |

## Testing

```
python -m pytest tests/backend -v          # 20 tests, TestClient (in-process ASGI)
python -m backend.validate_api             # 13 manual checks against a REAL running server
```

## Limitations

- **No connection pooling**: every request opens and closes its own Snowflake connection (documented in `backend/db/snowflake.py`), matching this project's existing script-based pattern but adding real latency (~2.5-4s/request observed) and capping practical concurrency. A production deployment should add a pooled/persistent connection strategy before serving real dashboard traffic.
- **`revenue/trends`'s `service` filter is a documented no-op**: `VW_REVENUE_TRENDS` has no service dimension (a deliberate Phase 2D decision, since only deals/subscriptions carry a `service_key` — see `docs/analytics_layer.md`). The parameter is accepted for interface consistency with the brief rather than rejected, but currently filters nothing.
- **No authentication**: Phase 6 is explicitly read-only and scoped to local development against `http://localhost:5173`; no auth layer was requested or built. Do not expose this server beyond localhost without adding one.
- **Read-only, by design**: no endpoint updates `DI_DECISIONS.status`, retrains a model, or executes a recommended action — all explicitly out of scope for Phase 6.
