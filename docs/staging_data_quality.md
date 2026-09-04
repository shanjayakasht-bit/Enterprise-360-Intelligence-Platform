# NEXORA Phase 2B — STAGING Data Quality

## RAW vs. STAGING purpose

**RAW** (`snowflake/sql/03_raw_tables.sql`) is a 1:1 copy of the source CSVs: same column names, same order, minimal typing, no cleaning. It exists as immutable ingestion history — a permanent record of exactly what was loaded, so any later layer can always be rebuilt from scratch without re-extracting from source.

**STAGING** (`snowflake/sql/04_staging_tables.sql`, populated by `05_staging_transformations.sql`) is the same business data cleaned, consistently typed, deduplicated on primary key, and flagged for quality — the first layer safe to build real logic on top of. It contains **no business transformations**: no Phase 1 formulas, no derived metrics, no renamed semantics. It only cleans and flags what RAW already contains. CORE dimensional modeling (Phase 2C, not started) is where STAGING gets reshaped into facts/dimensions.

Every STAGING table carries a `STG_` prefix and four pipeline-metadata columns not present in RAW: `_source_loaded_at`, `_staged_at`, `_data_quality_status`, `_data_quality_issue`.

## Cleaning rules (string cleaning)

- Every ID column (`customer_id`, `employee_id`, `lead_id`, `deal_id`, `subscription_id`, `project_id`, `invoice_id`, `payment_id`, `ticket_id`, `activity_id`, and FK columns like `account_manager_id`, `sales_rep_id`, `assigned_salesperson_id`, `project_manager_id`, `agent_id`) is `TRIM`-ed and `UPPER`-cased. Optional FK IDs that clean to an empty string are converted to `NULL`.
- Free-text/proper-noun fields (`company_name`, `first_name`, `last_name`, `full_name`, `product`) are `TRIM`-ed only — casing is never changed, since these are names, not categories.
- `email` is `TRIM`-ed and lower-cased (standard practice, and case-insensitive by protocol).

## Normalization rules (category standardization)

Categorical/enum fields (`region`, `industry`, `segment`, `country`, `department`, `subscription_plan`/`plan`, `status` fields, `priority`, `channel`, `category`, `deal_stage`, `project_type`, `billing_cycle`, `lead_source`, `churn_risk_category`, `project_risk_category`, `payment_method`, `activity_type`, `job_title`) are `TRIM`-ed and `INITCAP`-ed for consistent casing.

**Acronym exception, applied deliberately:** the source data (see `data_generator/master_data.py`) intentionally uses three all-caps acronyms inside otherwise Title Case values — `payment_method = "ACH"`, `activity_type = "API Call"`, and `job_title` values starting with `"HR "`. Plain `INITCAP` would corrupt these to `"Ach"`, `"Api Call"`, `"Hr Specialist"` — a real semantic change, not just casing. Each of those three columns gets a targeted `REPLACE(...)` fix-up immediately after `INITCAP` to restore the acronym. This was caught by checking the actual generator constants before writing the SQL, not assumed.

`product` is deliberately **excluded** from standardization (kept `TRIM`-only) because its values are proper product names (`"NEXORA Insights API"`, etc.) where `INITCAP` would similarly mangle `NEXORA`/`API`.

## Date handling

All date columns are re-derived with `TRY_TO_DATE(TO_VARCHAR(raw_column))` rather than assigned directly. Since RAW already stores native `DATE` values (validated at COPY INTO time in Phase 2A), this is a defensive, belt-and-suspenders re-validation at the STAGING boundary: a bad value produces `NULL` instead of aborting the whole table's load, so one row's problem can't take down 30,000 others. It also means the pipeline degrades gracefully if a future RAW schema change ever loads dates as loosely-typed text.

## Numeric and boolean normalization

Numeric business fields (`deal_value`, `mrr`, `budget`, `actual_cost`, invoice/payment amounts, `completion_pct`, all `*_score` fields, `resolution_time_hours`, etc.) go through `TRY_TO_DECIMAL`/`TRY_TO_NUMBER` with the same precision/scale as their RAW column, for the same defensive reason as dates. Boolean-like fields (`is_active`, `converted_to_deal`, `is_won`, `auto_renew`) go through `TRY_TO_BOOLEAN(TO_VARCHAR(...))`; `is_won`'s legitimate three-state nature (`TRUE` / `FALSE` / `NULL` for an undecided deal) is preserved, not coerced to two-valued.

## Duplicate handling

Each table's transformation computes `ROW_NUMBER() OVER (PARTITION BY <cleaned primary key> ORDER BY _source_loaded_at DESC)` and keeps only `rn = 1` — the most recently loaded record per key. A primary-key duplicate can structurally never reach STAGING. `etl/validate_staging.py` independently re-checks this (`no duplicate <pk> among VALID rows`) rather than trusting the transformation blindly. In the current dataset this never fires, because Phase 1/2A already validated zero duplicate keys in RAW — the mechanism exists for when RAW load history changes (e.g. a future re-ingest) rather than because today's data needs it.

**Known limitation:** if a primary key were `NULL` for more than one row, `ROW_NUMBER() PARTITION BY NULL` would group them together and keep only one, silently dropping the rest. This can't happen today (primary keys are validated non-null all the way from CSV generation through RAW), but it's a real edge case worth knowing about before this pipeline is pointed at a different data source.

## Data quality flags — VALID / WARNING / INVALID

Every row is inserted into STAGING regardless of what rules it fails — **nothing is silently dropped**. Two rule tiers are evaluated per table (see `snowflake/sql/05_staging_transformations.sql` for the exact per-table conditions):

- **INVALID** — the row is logically broken: a mandatory field is missing (reusing Phase 1's own `MANDATORY_FIELDS` definitions), a score/percentage is outside its validated range (reusing Phase 1's `RANGE_CONSTRAINTS`), or a business-consistency check fails (`close_date < created_date`, `planned_end_date`/`actual_end_date < start_date`, `due_date < invoice_date`, `payment_date < invoice_date`, or a negative invoice/payment amount).
- **WARNING** — the row is usable but has a soft issue: an optional-but-expected field is missing (e.g. a converted lead with no `converted_date`, a Completed project with no `actual_end_date` — this mirrors a Phase 1 business-rule check, not a new one), a negative `budget`/`mrr`/`deal_value`, an unrecognized risk-category value, or a standalone invoice with neither a subscription nor project link (allowed under Phase 1 rules, flagged here for visibility).
- **VALID** — neither tier fired.

`_data_quality_issue` holds a semicolon-joined list of every rule that fired (built via `ARRAY_CONSTRUCT_COMPACT` + `ARRAY_TO_STRING`, `NULL` when no issue), so a downstream consumer can see exactly why a row was flagged, not just that it was.

## Null handling

Nulls are never silently coerced away. Where COPY INTO's `NULL_IF` already converted blank/`NULL`/`null` source strings to true `NULL` in RAW (Phase 2A), STAGING preserves that. Optional FK columns get one extra `NULLIF(..., '')` pass in case a cleaned value became an empty string. Null mandatory fields drive the `INVALID` status; null optional fields drive `WARNING` only where the business context suggests they shouldn't be null (converted lead, completed project, closed ticket).

## Invalid-record strategy

INVALID rows are **flagged, never deleted or excluded**. This is a deliberate choice: dropping rows at the staging boundary destroys information a future consumer might need (to fix the source, to understand data completeness, to audit what changed) and makes STAGING row counts silently diverge from RAW without explanation. Anyone consuming STAGING can filter `WHERE _data_quality_status = 'VALID'` (or `IN ('VALID','WARNING')`) explicitly instead.

## Why RAW stays immutable

RAW is the one artifact that lets the entire pipeline — STAGING today, CORE and ANALYTICS later — be rebuilt from scratch if a transformation rule turns out to be wrong. `etl/transform_staging.py` only ever issues `SELECT`/`COUNT(*)` against `RAW.*`; every write goes to `STAGING.*`. `etl/validate_staging.py` checks this isn't just a coding convention but an observed fact, by comparing RAW's current row counts against the exact counts recorded at the end of the validated Phase 2A load (5,000 / 1,000 / 15,000 / 20,000 / 10,000 / 8,000 / 30,000 / 22,777 / 40,000 / 50,000 — 201,777 total) — any drift means something outside this pipeline touched RAW.

## Observed results (full dataset, live run)

```
Tables checked: 10
Passed: 10
Failed: 0

Total VALID rows: 198,756
Total WARNING rows: 3,021
Total INVALID rows: 0
```

The only WARNING population is in `STG_INVOICES` (3,021 rows — invoices with neither a `subscription_id` nor a `project_id`), matching Phase 1/2A's own already-validated "standalone invoices allowed" count exactly. No INVALID rows were produced by the full, deterministic-seed dataset — expected, since Phase 1 already validated 60/60 business-rule and schema checks on this same data before it ever reached Snowflake.
