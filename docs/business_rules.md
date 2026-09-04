# NEXORA Business Rules

This document describes the business logic implemented in `data_generator/business_rules.py`
and applied during dataset generation. All formulas are deterministic functions of stored
columns, so `validation/validate_business_rules.py` can recompute and verify every score.

## Customer churn risk

`churn_risk_score` (0-100, on `customers.csv`) is a weighted blend of six risk components,
each also scaled 0-100 (higher = riskier):

| Component | Weight | Rises when... |
|---|---|---|
| Usage | 20% | `product_usage_score` falls |
| Engagement | 15% | `engagement_score` falls |
| Satisfaction | 20% | `satisfaction_score` falls |
| Support load | 15% | `support_ticket_count_recent` rises (capped at ~8+ tickets/year) |
| Payment delay | 15% | `avg_payment_delay_days` rises (capped at 25+ days late) |
| Renewal proximity | 15% | `days_to_renewal` shrinks toward 0 |

`churn_risk_category` buckets the score: **Low** (<25), **Medium** (25-49), **High** (50-74),
**Critical** (75+).

Inputs are not independent random draws: each customer has four latent propensity scores
(usage, engagement, satisfaction, payment reliability) sampled from a "health" cohort
(~16% of customers are drawn from a chronically at-risk cohort). Those propensities bias how
`customer_activity`, `support_tickets`, and `payments` are generated for that customer, and
`customers.finalize()` aggregates the real generated behavior back onto the customer record
before scoring -- so a customer's risk score reflects data that actually exists in the other
tables, not an independent random number.

## Project risk

`project_risk_score` (0-100, on `projects.csv`) blends four components:

| Component | Weight | Rises when... |
|---|---|---|
| Completion | 30% | `completion_pct` is low |
| Deadline proximity | 25% | days remaining to `planned_end_date` shrink (100 once overdue) |
| Budget utilization | 20% | `budget_utilization_pct` climbs above 50% |
| Cost overrun | 25% | `actual_cost` exceeds `budget` (`cost_overrun_pct` rises) |

Deadline proximity is measured against `actual_end_date` for finished/cancelled projects and
against today for projects still in flight, so a project that finished late is still penalized
even though `completion_pct` reached 100.

## Revenue shaping

Deal value, subscription MRR, project budgets, and standalone invoice amounts all run through
`business_rules.priced_amount()`, which applies three multiplicative factors to a base price:

- **Segment** -- Enterprise accounts are priced ~3.2x an SMB baseline, Mid-Market ~1.6x, Startup ~0.55x.
- **Region** -- North America and Europe price highest (1.15x / 1.05x); Latin America lowest (0.75x).
- **Seasonality** -- monthly multiplier peaking in Q4 (November 1.15x, December 1.25x) to reflect
  fiscal year-end budget flush, dipping in mid-summer (July/August 0.85x).

A final +/-jitter is applied per transaction so amounts aren't perfectly formulaic.

Deal discounts (`deals.discount_pct`) scale with segment (Enterprise negotiates the steepest
discounts) and deal size (larger deals earn a larger discount, up to a combined 35% cap).

## Cross-table consistency rules enforced during generation

- Every `leads`, `deals`, `subscriptions`, `projects`, `invoices`, `support_tickets`, and
  `customer_activity` row is generated against a real, pre-existing `customers.customer_id`.
- `deals.sales_rep_id`, `leads.assigned_salesperson_id`, `customers.account_manager_id`,
  `projects.project_manager_id`, and `support_tickets.agent_id` are only drawn from employees
  in the matching department (Sales, Account Management, Project Management, Customer Support).
- A share of `deals` originate from a converted `leads` row (`deals.lead_id`); a share of
  `subscriptions` and `projects` originate from a Closed Won `deals` row (`*.deal_id`).
- Every `invoices` row is billed against a subscription, a project, or (occasionally) stands
  alone against a customer directly -- never against unrelated/random entities.
- Every `payments` row references a real `invoices.invoice_id` whose status is Paid or
  Partially Paid; per-invoice payment totals never exceed `total_amount`.
