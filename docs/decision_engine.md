# NEXORA Phase 5 — Decision Intelligence Engine

## Why this exists

Phases 2D–4 built three increasingly sophisticated but fundamentally *descriptive* or *predictive* layers: ANALYTICS answers "what does the data show right now" (KPIs, views), Phase 3 mining answers "what patterns exist in the data" (segments, associations, anomalies), and Phase 4 answers "what is likely to happen" (risk probabilities, a revenue forecast). None of them answer the question an executive actually asks: **"given all of this, what should we do, in what order, and why?"** That synthesis — reading across BI, mining, and prediction outputs simultaneously, ranking the results by genuine business urgency, and turning them into a specific, traceable, advisory recommendation — is what the Decision Engine adds. It is the layer where NEXORA stops being a reporting tool and becomes a decision-support tool.

## BI vs. prediction vs. decision intelligence

| Layer | Answers | Example |
|---|---|---|
| Business Intelligence (Phase 2D) | What happened? | "Total outstanding amount is $827M" |
| Data Mining (Phase 3) | What patterns exist? | "Customers cluster into 3 behavioral segments" |
| Predictive Analytics (Phase 4) | What's likely next? | "This invoice has a 72%-AUC-validated 83% probability of late payment" |
| **Decision Intelligence (Phase 5)** | **What should we do about it, and how urgently?** | "Invoice INV028101: $1.06M outstanding, 83% delay probability, CRITICAL priority (92.5/100) — send a reminder, escalate to finance leadership" |

Every `DI_DECISIONS` row exists to answer, in one place, the five questions the brief poses: **what happened** (`what_happened`), **why** (`why_it_happened`), **what's likely next** (`predicted_outcome`), **what's the cost** (`business_impact_type`/`business_impact_value`), and **what to do** (`recommended_action_1..5`).

## Decision data model

`ANALYTICS.DI_DECISIONS` — one row per `(decision_type, entity_type, entity_id)`, which is literally what `decision_id` is built from (`decision_engine/common.py::make_decision_id`), making the "no duplicate active decision for the same triple" rule a structural primary-key guarantee rather than an after-the-fact check. See `snowflake/sql/13_decision_engine_tables.sql` for the full column list and types.

`ANALYTICS.DI_EXECUTIVE_SUMMARY` — one row, refreshed every run, aggregating the current decision backlog. Every `*_at_risk`/`*_value` metric is computed from **distinct entities**, not summed across decisions: a customer with both a `CUSTOMER_RETENTION` decision and a `BUSINESS_ANOMALY` decision contributes its ARR once (via `MAX` across that entity's decisions, grouped by `entity_id`, then summed) — see `decision_engine/generate_decisions.py::build_executive_summary`.

## Decision types

`CUSTOMER_RETENTION`, `PROJECT_DELIVERY`, `PAYMENT_COLLECTION`, `REVENUE_OPPORTUNITY` (covers forecast downside, regional growth, cross-sell, and concentration risk as four subtypes), `BUSINESS_ANOMALY`. `SUPPORT_ESCALATION` was listed as a possible type in the brief but was not implemented as its own generator: support-ticket signals (`open_ticket_count`, `SLA breaches`) are already surfaced as contributing signals *within* `CUSTOMER_RETENTION` decisions (see `root_cause.py::CUSTOMER_SIGNAL_RULES`) rather than duplicated as a separate decision — a customer with an escalating ticket count already gets a decision card with "Escalate unresolved support tickets" as a recommended action, so a second, overlapping `SUPPORT_ESCALATION` card for the same underlying signal would inflate the count without adding new information.

## Why the candidate populations were narrowed (materiality filtering)

The first version of this engine used only a risk-category filter (e.g., `churn_risk_category IN ('High','Critical')`) and produced **4,249 decisions** — because Phase 1's own risk formulas classify a genuinely large share of the synthetic population as High risk (1,195 of 5,000 customers; 1,188 of ~3,670 open projects). Generating a decision card for every one of them would technically be correct but would violate the brief's explicit "do not inflate decision counts for visual effect" instruction in spirit: a backlog a human can't triage isn't a decision engine, it's a re-export of the risk tables.

The fix: every classifier-backed domain (customer, project, finance) adds a **materiality filter** on top of the risk filter — restricting to the **top decile (90th percentile) of dollar exposure, computed live within the already-risky population** (never a guessed constant; see each domain module's `RISKY_POPULATION_SQL`/`MATERIALITY_PERCENTILE`). This is a legitimate, common triage principle (focus finite attention on the highest-exposure risky accounts/projects/invoices first) and brought the total to a genuinely reviewable **439 decisions**. Lower-exposure risky entities are not hidden or deleted — they remain fully visible in `VW_CUSTOMER_HEALTH`, `VW_PROJECT_RISK`, `ML_PAYMENT_DELAY`, etc. — they are simply not promoted to a top-level executive decision card this run.

## Priority scoring — domain-specific formulas

Every formula follows `Priority = w₁·Risk + w₂·Impact + w₃·Urgency + w₄·Strategic`, all four components pre-normalized to [0, 100] (via `decision_engine/common.py::normalize`) before weighting, so the result is always in [0, 100] directly. Weights differ by domain because the four domains genuinely don't share the same balance of what matters (see `decision_engine/priority_scoring.py` for the full rationale comments):

| Domain | Risk | Impact | Urgency | Strategic | Why this balance |
|---|---|---|---|---|---|
| `CUSTOMER_RETENTION` | 40% | 30% | 15% | 15% | "Is this customer unhealthy" is the central question |
| `PROJECT_DELIVERY` | 35% | 30% | 20% | 15% | Time truly remaining matters more (no renewal-date cushion) |
| `PAYMENT_COLLECTION` | 35% | 35% | 20% | 10% | Fundamentally about dollars at stake and how overdue |
| `REVENUE_OPPORTUNITY` | 35% | 35% | 15% | 15% | Inherently strategic and dollar-driven |
| `BUSINESS_ANOMALY` | 40% | 30% | 15% | 15% | Leads with statistical extremity |

Every weight set is asserted (at import time) to sum to exactly 1.0.

**Component definitions by domain** (all normalized 0–100 before weighting):
- **Risk** — Customer/Project: a 60/40 blend of Phase 1's business-rule risk category (mapped Low=10/Medium=40/High=75/Critical=95) and the Phase 4 ML probability, weighted toward the business rule since those two models validated at chance-level accuracy (see below). Payment: the ML probability directly (100%) — that model validated with real signal (AUC 0.721). Revenue/Anomaly: signal magnitude (forecast interval width, region efficiency, association lift, or `|anomaly_score|`).
- **Impact** — the relevant dollar exposure (ARR, budget, outstanding amount, or opportunity value), normalized against the 99th-percentile of that metric across the full population (so a handful of extreme values can't blow out the scale for everyone else).
- **Urgency** — time-based where a real date exists (days to renewal, days to deadline, days overdue); a documented moderate default (30–80) where no natural clock applies (anomalies, most revenue subtypes).
- **Strategic** — `decision_engine/common.py::strategic_importance`, a fixed segment-tier ranking (Enterprise=100, Mid-Market=66, SMB=33, Startup=15), or a flat enterprise-level value (70–90) for region/service/enterprise-scoped decisions.

## Severity thresholds

`decision_engine/common.py::SEVERITY_BANDS`, applied via `severity_from_score()`: **0–39 LOW, 40–59 MEDIUM, 60–79 HIGH, 80–100 CRITICAL** — exactly the brief's scheme, unmodified (it needed no refinement).

## Confidence score — tied to actual validated model accuracy, never assumed

`confidence_score` is **not** the risk/delay probability itself — it's a separate, honest measure of *how much to trust that probability*, derived from the backing model's own Phase 4 ROC-AUC (`decision_engine/common.py::confidence_from_auc`): `confidence = max(0, (AUC − 0.5) / 0.5 × 100)`. An AUC of 0.5 (chance level) maps to confidence 0; an AUC of 1.0 maps to 100; linear in between.

This is deliberately harsh on two of the three ML-backed domains, and it should be: Phase 4 documented that the customer-churn (AUC 0.481) and project-risk (AUC 0.520) models validated at or below chance level, while the payment-delay model (AUC 0.721) found genuine signal. Rather than presenting every ML-backed decision as equally trustworthy, `CUSTOMER_RETENTION` and `PROJECT_DELIVERY` decisions carry `confidence_score` values of roughly 0–4 (observed live), while `PAYMENT_COLLECTION` decisions carry ~44. Descriptive (non-model) findings — regional growth, cross-sell, concentration — use a fixed `DESCRIPTIVE_CONFIDENCE = 70`, documented as reflecting data-groundedness rather than model validation, since they're direct observations, not probability estimates.

## Root-cause / contributing-signal logic

`decision_engine/root_cause.py` — **fully deterministic, no generative text**. Each domain has a fixed, documented rule list (`CUSTOMER_SIGNAL_RULES`, `PROJECT_SIGNAL_RULES`, `PAYMENT_SIGNAL_RULES`): `{column, direction, threshold, label}`. A rule fires when the entity's actual feature value crosses its threshold; firing rules are ranked by breach magnitude (how far past the threshold, as a fraction of it) and the top few are surfaced. Every resulting sentence is prefixed **"Primary contributing signals (not claimed as definitive causes)"** — this exact hedge appears in every `why_it_happened` value in the database, never "the cause was..." Business-anomaly decisions reuse Phase 3's own deterministic, feature-deviation-based `observed_value`/`expected_context` text (also never LLM-generated) rather than re-deriving anything.

## Recommendation engine

`decision_engine/recommendations.py` — deterministic `if`/`elif` mappings from triggered signal labels (+ segment/risk-level context) to a fixed action string, exactly the pattern the brief specifies (e.g., "elevated unresolved tickets" → "Escalate unresolved support tickets"; "Enterprise/Mid-Market segment" → "Assign senior account manager"). The same inputs always produce the same outputs — fully traceable, no randomness, no LLM. Every list is capped and deduplicated at 5 actions (`MAX_ACTIONS`), matching `recommended_action_1..5`.

## Deduplication strategy

Two layers: (1) **structural** — `decision_id` is the `(decision_type, entity_type, entity_id)` composite key itself, so `DI_DECISIONS`' primary key makes a true duplicate impossible to persist; (2) **defensive** — `generate_decisions.py::deduplicate()` still checks for and logs (rather than silently allowing) any duplicate `decision_id` produced within a single run, before the write. An entity can legitimately have **multiple different** decision types (e.g., a customer can have both a `CUSTOMER_RETENTION` and a `BUSINESS_ANOMALY` decision) — that's not a duplicate, it's two distinct findings about the same entity, and the executive-summary aggregation (above) already accounts for not double-counting that entity's dollar exposure across them.

## Limitations

- Two of the three ML-backed domains (customer, project) inherit Phase 4's honestly-reported finding that those specific models carry no real predictive power on this synthetic dataset — their decisions are still generated (using the real business-rule risk category as the primary signal) but explicitly carry low `confidence_score` and hedged `predicted_outcome` text.
- The materiality filter (top decile by exposure) means some genuinely risky but lower-dollar-value entities won't get a decision card this run — a deliberate focus trade-off, not an oversight (see above).
- `REVENUE_OPPORTUNITY`'s four subtypes use heterogeneous, domain-appropriate impact/confidence definitions rather than one uniform formula — documented per subtype in `revenue_decisions.py`, since a forecast-uncertainty dollar figure and a cross-sell opportunity estimate are not directly comparable quantities.
- This engine computes decisions from a single point-in-time snapshot of the warehouse; it has no concept of a decision's history, no trend-over-time view of priority scores, and (per the brief) no status-transition workflow — every run's decisions start at `status = 'NEW'`.

## Why recommendations are advisory, not automatically executed

Nothing in `decision_engine/` sends an email, opens a ticket, contacts an account manager, or modifies any CORE/STAGING/RAW/ML/DM table — every `recommended_action_N` is plain text describing what a human should consider doing next. This is a deliberate scope boundary, not a missing feature: recommending "assign a senior account manager" requires organizational judgment (who, when, with what authority) this engine has no basis to exercise, and automatically executing business actions from a system whose own two weakest models validated at chance-level accuracy would be actively irresponsible. A future Decision Engine execution layer (explicitly out of scope for Phase 5) would need its own approval workflow, audit trail, and — for the customer/project domains specifically — materially better predictive models before automation would be defensible at all.

## Example decision cards (live output)

**Customer** — `CUSTOMER_RETENTION_CUSTOMER_CUST000572`, priority 83.79 (CRITICAL): Molina Inc (Enterprise), $1,392,660 ARR exposure. Signals: outstanding balance present, renewal in 2 days, engagement score 8.4 (threshold 40), usage score 17.1 (threshold 40). Confidence 0.0 (model validated at chance level). Actions: assign senior account manager; schedule retention review; review commercial terms; schedule success check-in.

**Project** — `PROJECT_DELIVERY_PROJECT_PROJ003449`, priority 90.19 (CRITICAL): $1,048,545 budget exposure, 0% complete, planned deadline 85 days passed. Confidence 4.0. Actions: revise milestone plan; escalate blockers; reallocate resources.

**Finance** — `PAYMENT_COLLECTION_INVOICE_INV028101`, priority 92.51 (CRITICAL): $1,063,790 outstanding, 83% predicted delay probability, 287 days overdue. Confidence 44.3 (real model signal). Actions: send reminder; contact account manager; escalate as strategic overdue account.

**Revenue** — `REVENUE_OPPORTUNITY_SERVICE_...`, priority 85.00 (CRITICAL): cross-sell opportunity, Implementation engagements → NEXORA Managed Services, lift 1.46x across 370 customers, estimated $5,537,523 opportunity value. Confidence 70 (descriptive).

## Commands

```
python -m decision_engine.generate_decisions
python -m etl.validate_decision_engine
```
