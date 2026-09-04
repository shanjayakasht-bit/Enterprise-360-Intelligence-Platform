# NEXORA Phase 2D — ANALYTICS and Business Intelligence Layer

Source: `NEXORA_DB.CORE` only. Every view in `09_analytics_views.sql` and `10_analytics_kpis.sql` reads exclusively from CORE dimensions and facts — nothing here touches RAW or STAGING, and nothing here writes anywhere (all ten objects are plain `CREATE OR REPLACE VIEW ... SELECT`, no DML).

## The revenue definition (read this first)

The word **"revenue"** (unqualified) means one specific thing everywhere in this layer: **won deal value**, `SUM(FACT_DEALS.net_deal_value) WHERE is_won = TRUE`. It is the sales-bookings figure — what was actually sold and closed.

Three other numbers are related but **not the same thing, and never added to `total_revenue`**:

| Term | Definition | What it represents |
|---|---|---|
| `total_revenue` / `revenue` | `SUM(net_deal_value)` WHERE `is_won` | Sold / booked (sales) |
| `total_invoice_amount` / `invoice_amount` / `invoice_total` | `SUM(FACT_INVOICES.total_amount)` | Billed (accounting) |
| `total_payments_received` / `payments_received` | `SUM(FACT_PAYMENTS.amount_paid)` | Collected (cash) |
| `mrr` / `arr` | `SUM(FACT_SUBSCRIPTIONS.mrr)` / `.arr` | Recurring commitment (forward-looking) |

These are four different lifecycle stages of the same underlying business activity, sourced from four different fact tables. `VW_REVENUE_TRENDS` deliberately exposes all four as **separate columns** rather than blending them into one number, specifically so nobody downstream can accidentally sum two of them and double the revenue.

## Double-counting prevention (the pattern used everywhere)

Every view that touches more than one fact table pre-aggregates each fact to the target grain in its own CTE **before** joining anything. This matters because Snowflake joins are relational, not additive: joining two "many" tables directly on a shared key (e.g. `FACT_INVOICES` straight to `FACT_PAYMENTS` on `invoice_id`, when an invoice can have several payment rows) produces a fan-out — one invoice row multiplied by N payment rows — and a naive `SUM(invoice.total_amount)` over that join silently multiplies the invoice total by N. Every view below avoids this by aggregating first, joining second. `VW_FINANCE_SUMMARY` and `VW_CUSTOMER_360` are the clearest examples (see their SQL comments); `etl/validate_analytics.py` checks 6 and 7 verify this holds by comparing view-level sums against independently-computed CORE sums.

## Views

| View | Grain | Rows (live) | Purpose |
|---|---|---|---|
| `VW_EXECUTIVE_OVERVIEW` | 1 row (whole enterprise) | 1 | Dashboard-ready top-line KPIs + Enterprise Health Score |
| `VW_CUSTOMER_360` | 1 row per current customer | 5,000 | Comprehensive cross-functional customer profile |
| `VW_REVENUE_TRENDS` | 1 row per (date, region, segment) | 13,019 | Revenue over time, four lenses, no forced service dimension |
| `VW_CUSTOMER_HEALTH` | 1 row per current customer | 5,000 | Focused health/risk view (usage, support, payment, renewal indicators) |
| `VW_PROJECT_RISK` | 1 row per project | 8,000 | Budget, cost, schedule, and risk per project |
| `VW_SUPPORT_HEALTH` | 1 row per support ticket | 40,000 | Ticket-level SLA and satisfaction detail |
| `VW_FINANCE_SUMMARY` | 1 row per invoice | 30,000 | Invoice, payment, and outstanding-balance detail |
| `VW_REGION_PERFORMANCE` | 1 row per region | 5 | Cross-process rollup by region |
| `VW_SERVICE_PERFORMANCE` | 1 row per service | 15 | Cross-process rollup by NEXORA product/plan/project type |
| `VW_AT_RISK_CUSTOMERS` | 1 row per High/Critical-risk customer, ranked | 1,195 | Executive watchlist, most-at-risk first |

### Why `VW_REVENUE_TRENDS` has no service dimension

Only `FACT_DEALS` and `FACT_SUBSCRIPTIONS` carry a real `service_key`. `FACT_INVOICES`/`FACT_PAYMENTS` reference `subscription_id`/`project_id` as optional degenerate identifiers, not a service dimension — forcing a `service_category` column onto invoice/payment rows would mean inventing a join path that doesn't exist in CORE. Service-level revenue lives in `VW_SERVICE_PERFORMANCE` instead, using only the two fact tables that genuinely have a service link.

### Why `VW_SERVICE_PERFORMANCE` has no support-activity column

`FACT_SUPPORT` has no `service_key` and no product/category linkage anywhere in STAGING or CORE — tickets aren't tied to a specific NEXORA product. The task allowed for "support activity if available"; it isn't, so the column is omitted rather than populated with a fabricated join.

## KPI definitions (`VW_EXECUTIVE_OVERVIEW`)

| KPI | Definition |
|---|---|
| `total_revenue` | `SUM(net_deal_value)` WHERE `is_won` (see revenue definition above) |
| `active_customers` | `COUNT(DISTINCT customer_key)` with at least one `Active` subscription — a real "currently engaged" definition, not just "exists in the dimension" (which would trivially equal the full customer count) |
| `active_subscriptions` | `COUNT(*)` WHERE `status = 'Active'` |
| `active_projects` | `COUNT(*)` WHERE `status NOT IN ('Completed', 'Cancelled')` |
| `projects_at_risk` | `active_projects` AND `project_risk_category IN ('High', 'Critical')` — only ongoing projects; a completed project's historical risk score isn't actionable |
| `open_support_tickets` | `COUNT(*)` WHERE `status IN ('Open', 'In Progress', 'Escalated')` |
| `support_sla_percentage` | % of **resolved** tickets whose `resolution_time_hours` met their priority's SLA target (see SLA policy below) |
| `average_customer_health` | `AVG(100 - churn_risk_score)` over current customers |
| `total_invoice_amount` | `SUM(FACT_INVOICES.total_amount)` |
| `total_payments_received` | `SUM(FACT_PAYMENTS.amount_paid)` |
| `outstanding_amount` | `total_invoice_amount - total_payments_received` |

## SLA policy — an explicit ANALYTICS-layer assumption

**No SLA target field exists anywhere in Phase 1's source data** (confirmed when Phase 2C's `FACT_SUPPORT` was designed, and confirmed again here). Rather than silently omitting SLA metrics the task explicitly asks for three times, this layer defines one transparent, clearly-labeled policy, used identically everywhere SLA is computed (`VW_SUPPORT_HEALTH`, `VW_CUSTOMER_360`'s ticket rollup, `VW_EXECUTIVE_OVERVIEW`):

| Priority | SLA target |
|---|---|
| Critical | 12 hours |
| High | 48 hours |
| Medium | 120 hours (5 days) |
| Low | 240 hours (10 days) |

**These thresholds were calibrated against this dataset's own observed resolution-time distribution**, not picked blind. The first attempt used generic "textbook" SLA numbers (4h/24h/48h/72h) and produced a 20.9% compliance rate — because the actual median resolution times in this dataset (Critical: 8.4h, High: 25h, Medium: 71h, Low: 116h) already exceed those thresholds, which would make the metric uniformly "failing" rather than a useful discriminator. The thresholds above sit near the P90 of each priority's actual resolution-time distribution, producing a 98.1% compliance rate that behaves like a real SLA metric: mostly met, with a meaningful minority of breaches to investigate. **This is still a placeholder, not a real captured policy** — replace it with NEXORA's actual support SLA commitments when available; it's defined in exactly one place in each file's header comment, so it's a one-line change everywhere it's used.

Open (unresolved) tickets are separately flagged as already-breached if the time elapsed since `created_date` already exceeds their priority's SLA window — visible on `VW_SUPPORT_HEALTH.sla_breach`, but `support_sla_percentage` itself is computed over resolved tickets only (there's no fair way to judge a still-open ticket's eventual compliance).

## REFERENCE_DATE — the "as of today" anchor

`VW_PROJECT_RISK.days_to_deadline` uses the literal date `2026-09-04`, matching `config.settings.REFERENCE_DATE` from Phase 1, rather than live `CURRENT_DATE()`. Phase 1 already computed `DIM_CUSTOMER.days_to_renewal` against that same fixed anchor; using a different "today" for a new ANALYTICS-layer calculation would make two numbers in the same warehouse silently disagree about what day it is, and would make `days_to_deadline` return a different answer every day even though nothing in the warehouse changed. A future phase that moves to live, continuously-refreshed data would switch this to `CURRENT_DATE()` at the same time it retires the fixed reference date elsewhere.

## Enterprise Health Score

A single transparent number, computed as a weighted average of five components — **weights sum to 100%, and no component is invented**:

| Weight | Component | Formula | Source |
|---|---|---|---|
| 25% | Customer health | `AVG(100 - churn_risk_score)`, current customers | Phase 1's own validated churn formula, inverted |
| 25% | Financial health | `LEAST(100, 100 * payments_received / invoice_total)` | `FACT_INVOICES` + `FACT_PAYMENTS` |
| 20% | Project health | `AVG(100 - project_risk_score)`, all projects | Phase 1's own validated project-risk formula, inverted |
| 20% | Support SLA | `support_sla_percentage` (resolved tickets) | `FACT_SUPPORT` + the SLA policy above |
| 10% | Revenue trend | 50 (flat) ± 100 × QoQ%% change in invoiced revenue, capped to [0, 100] | `FACT_INVOICES`, most recent 90 vs. prior 90 days of **data actually present** (anchored to `MAX(invoice_date)`, not live `CURRENT_DATE`, so the trend window always sits inside the dataset's real coverage) |

**Rationale for the weights:** customer retention and cash collection are the two most directly business-critical signals, so they carry the most weight (25% each, 50% combined). Delivery quality — projects and support — matters operationally but is one step removed from revenue risk (20% each, 40% combined). Revenue trend is a genuinely useful but noisier, more volatile leading indicator, so it carries the smallest weight (10%).

**Missing-component handling, implemented, not just promised:** the SQL computes both a weighted numerator (`COALESCE(component, 0) * weight`) and a weight denominator (`0` if that component is `NULL`, else its nominal weight) for every component, then divides one by the other. A component that can't be computed (e.g. no prior-90-day revenue to compare against) contributes `0` to *both* sides, so the remaining components' weights are automatically rescaled to still sum to 100% of what's left — exactly the "redistribute weights transparently" requirement, not a documentation-only promise. `VW_EXECUTIVE_OVERVIEW` also exposes each of the five component scores as its own column (`customer_health_component`, `financial_health_component`, `project_health_component`, `support_sla_component`, `revenue_trend_component`) so the final number is always auditable back to its parts.

**Observed live result:** 73.0 (component scores: customer 61.4, financial 65.3, project 58.6, support SLA 98.1, revenue trend 100.0 — none currently missing, so no redistribution is active today).

## `customer_health_score` and `customer_status` (per-customer, not enterprise-wide)

This is a **different, simpler score** from the Enterprise Health Score above — it's the per-customer number shown in `VW_CUSTOMER_360`, `VW_CUSTOMER_HEALTH`, and `VW_AT_RISK_CUSTOMERS`. Per the task's explicit instruction not to invent an arbitrary score, it is exactly `100 - churn_risk_score` — Phase 1's own already-validated, already-documented weighted formula (usage, engagement, satisfaction, support tickets, payment delay, renewal proximity — see `data_generator/business_rules.py`), just reframed as "health" instead of "risk." `customer_status` is a direct relabeling of `churn_risk_category`: Low→Healthy, Medium→Watch, High→At Risk, Critical→Critical. Nothing new is computed at the per-customer grain; this view only exposes what Phase 1 already validated, plus (separately, as their own columns, never blended into the score) live indicators pulled from the fact tables — open ticket count, outstanding amount, SLA breaches — so a reader can see *why* a customer's score looks the way it does, without those live indicators secretly changing the score itself.

## Measures explicitly not modeled

Consistent with Phase 2C's "do not invent measures" stance:
- **Deal win `probability`** — no such column or formula exists anywhere in Phase 1.
- **Per-service support activity** — `FACT_SUPPORT` has no service linkage (see above).
- **Login/feature-usage/session-count as per-row measures** — `FACT_CUSTOMER_ACTIVITY`'s grain is one row per event; those would be aggregates across rows, which any consumer can compute themselves by filtering `activity_type`, not something a single-row measure should pre-bake.

## Dashboard KPI → View → Column mapping

| Dashboard KPI | Analytics View | Column |
|---|---|---|
| Total Revenue | `VW_EXECUTIVE_OVERVIEW` | `total_revenue` |
| Active Customers | `VW_EXECUTIVE_OVERVIEW` | `active_customers` |
| Active Subscriptions | `VW_EXECUTIVE_OVERVIEW` | `active_subscriptions` |
| Active Projects | `VW_EXECUTIVE_OVERVIEW` | `active_projects` |
| Projects at Risk | `VW_EXECUTIVE_OVERVIEW` / `VW_PROJECT_RISK` | `projects_at_risk` / filter `project_risk_category IN ('High','Critical')` |
| Open Support Tickets | `VW_EXECUTIVE_OVERVIEW` | `open_support_tickets` |
| Support SLA % | `VW_EXECUTIVE_OVERVIEW` / `VW_SUPPORT_HEALTH` | `support_sla_percentage` / `sla_breach` |
| Average Customer Health | `VW_EXECUTIVE_OVERVIEW` | `average_customer_health` |
| Enterprise Health Score | `VW_EXECUTIVE_OVERVIEW` | `enterprise_health_score` (+ 5 `*_component` columns) |
| Outstanding Amount | `VW_EXECUTIVE_OVERVIEW` / `VW_FINANCE_SUMMARY` | `outstanding_amount` |
| Customer Profile page | `VW_CUSTOMER_360` | every column, keyed by `customer_id` |
| Revenue-over-time chart | `VW_REVENUE_TRENDS` | `deal_revenue` / `invoice_amount` / `payments_received` by `full_date`/`month`/`quarter`/`year` |
| At-risk customer watchlist | `VW_AT_RISK_CUSTOMERS` | ordered by `risk_rank` |
| Region leaderboard | `VW_REGION_PERFORMANCE` | all columns, keyed by `region_name` |
| Service/product leaderboard | `VW_SERVICE_PERFORMANCE` | all columns, keyed by `service_name` |
| Project risk board | `VW_PROJECT_RISK` | all columns, filterable by `project_risk_category`/`status` |
| Finance / AR aging | `VW_FINANCE_SUMMARY` | `outstanding_amount`, `avg_payment_delay_days` |

This mapping is intentionally direct — a future NEXORA dashboard (out of scope for Phase 2D) can bind each widget straight to one of these views/columns without any further transformation, exactly the point of having an ANALYTICS layer sit between CORE and the presentation tier.

## Validation results (live run)

```
Views checked: 10
Passed: 69
Failed: 0
```

All ten views exist and execute; `VW_CUSTOMER_360`/`VW_CUSTOMER_HEALTH`/`VW_AT_RISK_CUSTOMERS` have zero customer duplication; `VW_FINANCE_SUMMARY`'s invoice and payment sums match `CORE.FACT_INVOICES`/`FACT_PAYMENTS` exactly (proving no fan-out); region and service revenue totals reconcile exactly to the overall `total_revenue`; the at-risk ranking is byte-for-byte identical across two consecutive runs; no DML against CORE appears anywhere in the view SQL; and RAW/STAGING/CORE row counts are all unchanged from their Phase 2A/2B/2C baselines.
