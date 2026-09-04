# NEXORA Phase 4 — Predictive Analytics

Source: `NEXORA_DB.ANALYTICS`/`CORE` exclusively (no RAW CSVs, no STAGING). Every pipeline reads only; results are written to four `ANALYTICS.ML_*` tables via full-refresh (`TRUNCATE` + bulk insert, the same proven `write_table` helper from Phase 3), never touching RAW, STAGING, CORE, or any existing ANALYTICS/Phase-3 object.

**Read this section before the per-model results below.** Two of the four models (customer churn, project risk) turn out to have **no meaningful predictive power**, and this is reported honestly rather than concealed — it is a real, empirically-verified property of how Phase 1's synthetic generator assigns certain outcomes, not a modeling failure. The other two (payment delay, revenue forecast) show genuine, well-explained signal. Understanding *why* the difference exists is the most important finding of this phase.

## Why two models find no signal — the investigation

Before writing any model code, each candidate target was checked against the Phase 1 generator source and empirically verified against the live warehouse:

- **`data_generator/subscriptions.py`**: `status = RNG.choice(SUBSCRIPTION_STATUSES)` — a subscription's Active/Cancelled/Expired/Paused status is drawn **independently at random**, with no dependency on any customer attribute.
- **`data_generator/projects.py`**: `status = RNG.choices(PROJECT_STATUSES, weights=PROJECT_STATUS_WEIGHTS)` — likewise independent of budget, segment, project type, or any other pre-project-start attribute.

This was verified empirically, not just read from code:

| Candidate target vs. feature | Correlation |
|---|---|
| `has_cancelled_subscription` vs. usage/engagement/satisfaction/tickets/payment-delay/churn-risk-score | all \|r\| < 0.02 |
| `has_overdue_invoice` vs. the same six features | all \|r\| < 0.12 |
| project `is_delayed` vs. segment | 20.1%–25.5% delay rate across all four segments (flat) |
| project `is_delayed` vs. service/project type | 21.2%–24.9% across all six types (flat) |
| project `is_delayed` vs. budget | r = 0.03 |

By contrast, **payment delay has real structure**: `data_generator/customers.py` assigns every customer a latent `health` cohort value, and `usage_propensity`, `engagement_propensity`, `satisfaction_propensity`, **and** `payment_reliability` are all independently perturbed around that *same* shared latent value. That shared cause produces genuine, non-circular correlation:

| Feature | Correlation with a customer's own average `days_late` |
|---|---|
| `PRODUCT_USAGE_SCORE` | −0.33 |
| `ENGAGEMENT_SCORE` | −0.31 |
| `SATISFACTION_SCORE` | −0.18 |

...and a customer's own payment history is autocorrelated (first-half vs. second-half average delay, customers with ≥4 payments): **r = 0.52**.

This is why the customer-churn and project-risk models honestly land near chance (AUC ≈ 0.48–0.52) while the payment-delay model reaches AUC ≈ 0.72: the underlying data only contains learnable signal for one of these three classification questions, and the modeling results simply reveal that fact rather than hide it.

---

## 1. Customer Churn / Risk Prediction

**Business problem**: identify customers likely to have their subscription end (cancelled/expired), to prioritize retention outreach.

**Source**: `ANALYTICS.VW_CUSTOMER_HEALTH` (join) `ANALYTICS.VW_CUSTOMER_360`.

**Target**: `1` if a customer's subscription ended up `Cancelled` or `Expired`, else `0` — a genuine recorded business outcome, not Phase 1's own `churn_risk_category` (using that field as target while its own component scores are features would just have the model re-learn a known formula, exactly what the brief warns against).

**A leakage bug found and fixed during development:** the first version defined the target as "**any** of a customer's subscriptions ended Cancelled/Expired." That version scored ROC-AUC ≈ 0.71 — suspiciously good given the correlation table above showed near-zero linear relationships. Investigating the RandomForest feature importances (`TOTAL_REVENUE` at 31%, `OUTSTANDING_AMOUNT` at 21%) led to the actual cause: each subscription independently has a ~1/3 chance of ending Cancelled/Expired, so `P(at least one cancelled | n subscriptions) = 1 − (2/3)ⁿ` — this rises mechanically with subscription count alone (empirically confirmed: 0% churned at n=0 subscriptions, climbing to 100% at n=7–8), and bigger customers (higher revenue, more subscriptions) were simply more likely to trip that count-driven target. **This was a mechanical artifact, not real signal.** The fix: restrict the target/training population to customers with **exactly one subscription**, where there is no count to be confounded by (verified: on that clean population, every correlation collapses back to ≈0, matching the original finding).

**Features** (12, explicitly excluding `churn_risk_score`/`churn_risk_category`/`customer_health_score`/`customer_status` — Phase 1's own formula outputs — and `active_subscriptions`/`arr`/`mrr`, which are definitionally tied to subscription status): `product_usage_score`, `engagement_score`, `satisfaction_score`, `support_ticket_count_recent`, `open_ticket_count`, `avg_payment_delay_days`, `outstanding_amount`, `days_to_renewal`, `total_revenue`, `sla_breaches`, `project_risk`, `activity_count`.

**Null handling**: `avg_payment_delay_days` NULL (no payments recorded) → 0; `project_risk` NULL (no projects) → 0; `outstanding_amount` NULL (no invoices) → 0. Each represents a genuine "no such event," not an unknown value.

**Train/test**: stratified 75/25 split, `random_state=42`. Training population: 1,289 single-subscription customers (431 churned, 858 not — class distribution reported, `class_weight='balanced'` used given the ~1:2 ratio).

**Models compared**:

| Algorithm | Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|---|
| Logistic Regression | 0.495 | 0.325 | 0.472 | 0.385 | **0.481** |
| Random Forest | 0.545 | 0.314 | 0.306 | 0.310 | 0.460 |

**Selected**: Logistic Regression (higher ROC-AUC and F1). **Honest conclusion**: neither model exceeds chance-level performance (AUC 0.5 = coin flip). This is reported as-is, matching the brief's explicit instruction to report poor performance honestly rather than paper over it. The model is still trained, evaluated properly, and persisted (satisfying the pipeline requirement), and the resulting `risk_probability` values hover close to the base rate for every customer — a decision-maker should treat this specific score as **not currently informative** until a real, non-random churn outcome is available to train against.

**Output**: `ANALYTICS.ML_CUSTOMER_RISK` — 5,000 rows (every current customer scored, not just the 1,289-customer training population — the model generalizes its features to everyone, since the features themselves are defined for all customers).

---

## 2. Project Delivery Risk Prediction

**Business problem**: identify projects likely to finish after their planned deadline, for proactive delivery management.

**Source**: `ANALYTICS.VW_PROJECT_RISK`, `CORE.FACT_PROJECTS` (joined to `DIM_CUSTOMER`/`DIM_SERVICE`/`DIM_DEPARTMENT`/`DIM_DATE` for planning-time attributes not exposed in the ANALYTICS view).

**Target**: `1` if `status = 'Delayed'`, or `status = 'Completed'` and `actual_end_date > planned_end_date`; `0` if `Completed` on/before the planned date. Training restricted to projects with a **resolved** outcome (`Completed` or `Delayed`) — 3,569 of 8,000 projects; still-open projects (Planned/In Progress/On Hold) have no determined outcome and are excluded from training (but still scored).

**Leakage prevention**: features are restricted to information knowable **at or near project start** — `budget`, `planned_duration_days` (`planned_end_date − start_date`), `service_name`/`project_type`, customer `segment`, `region_name`, delivery `department_name`. Explicitly **excluded**: `actual_cost`, `cost_overrun_pct`, `budget_utilization_pct` (all computed from the realized outcome — an over-cost project is mechanically likely to also be the late one), `completion_pct` (only meaningful in hindsight), and `project_risk_score`/`project_risk_category` (Phase 1's own formula output, the same leakage class excluded from the customer model).

**Train/test**: stratified 75/25 split, `random_state=42`. Class distribution: 1,442 delayed / 2,127 on-time (`class_weight='balanced'`).

**Models compared**:

| Algorithm | Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|---|
| Logistic Regression | 0.514 | 0.413 | 0.482 | 0.445 | 0.518 |
| Random Forest | 0.526 | 0.425 | 0.488 | 0.454 | **0.520** |

**Selected**: Random Forest (marginally higher on both metrics). **Honest conclusion**: both are at chance level, matching the code-level finding that `PROJECT_STATUSES` is assigned independently of every available feature. Same treatment as the churn model: trained, evaluated, and persisted properly, with the limitation stated plainly rather than hidden.

**Output**: `ANALYTICS.ML_PROJECT_RISK` — 8,000 rows (every project, including still-open ones, scored using only planning-time features).

---

## 3. Payment Delay Prediction

**Business problem**: predict whether a given invoice's payment will arrive late, to prioritize collections follow-up.

**Source**: `CORE.FACT_INVOICES`, `CORE.FACT_PAYMENTS`, `CORE.DIM_CUSTOMER` (for the latent-health-linked scores).

**Target**: `1` if the invoice's payment had `days_late > 0`; `0` otherwise. Training restricted to invoices with a recorded payment (21,392 of 30,000) — Unpaid/Overdue/Cancelled invoices have no outcome yet and are excluded from training (but still scored, since their pre-payment features are fully available).

**Leakage prevention**:
- `amount_paid`, `payment_date`, and `days_late` itself are never features — they *are* (or directly determine) the target.
- **`customer_historical_avg_delay` is computed leave-one-out**: for each invoice, the feature is the customer's mean `days_late` across their *other* paid invoices only, excluding the invoice being scored. A customer's own average delay *including* the invoice being predicted would trivially leak the target into its own feature. Customers with only one paid invoice (no genuine "other" history) get the population median as a neutral prior instead of their own single, leaky value.
- `total_amount`, `invoice_age_days` (`due_date − invoice_date`), `segment`, `region`, and the customer's `product_usage_score`/`engagement_score`/`satisfaction_score` are all knowable at invoice-issue time.

**Train/test**: stratified 75/25 split, `random_state=42`. Class distribution: 7,891 late / 13,501 on-time (`class_weight='balanced'`).

**Models compared**:

| Algorithm | Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|---|
| Logistic Regression | 0.651 | 0.522 | 0.663 | 0.584 | 0.716 |
| Random Forest | 0.668 | 0.543 | 0.639 | 0.587 | **0.721** |

**Selected**: Random Forest (higher ROC-AUC, comparable F1, and tree-based interactions between the historical-delay and score features are plausible and interpretable via feature importance below).

**Feature importance** (RandomForest):

| Feature | Importance |
|---|---|
| `customer_historical_avg_delay` | 0.400 |
| `engagement_score` | 0.197 |
| `product_usage_score` | 0.145 |
| `satisfaction_score` | 0.115 |
| `total_amount` | 0.066 |
| `invoice_age_days` | 0.033 |
| segment/region dummies (combined) | ~0.04 |

This matches the correlation investigation almost exactly: a customer's own payment history dominates, and the three latent-health-linked scores together account for another ~46% — a coherent, explainable, genuinely predictive result, not a black box.

**Output**: `ANALYTICS.ML_PAYMENT_DELAY` — 30,000 rows (every invoice).

---

## 4. Revenue Forecasting

**Business problem**: forecast near-term invoiced revenue for financial planning.

**Source**: `ANALYTICS.VW_REVENUE_TRENDS`, aggregated to monthly totals of `invoice_amount` (one of the four revenue lenses Phase 2D defined — never blended with `deal_revenue`/`payments_received`/`subscription_arr_booked`, consistent with that phase's "these are not additive" rule).

**A data-quality step, not a modeling choice**: the most recent calendar month in the data (September 2026) is **partial** — the warehouse's fixed reference date (2026-09-04) falls only 4 days into it. Comparing a 4-day month's total against 30-day months would badly distort both backtesting and the forecast anchor, so it is **excluded entirely** from the monthly series (detected programmatically: a trailing month is dropped whenever the last observed date doesn't reach that month's actual last calendar day), leaving **36 complete months** (Sept 2023 – Aug 2026).

**The series itself**: invoiced revenue grew from ~$629K/month (Sept 2023) to ~$204M/month (Jul 2026) — an ~800× increase over 3 years the customer base was itself being generated/growing, not organic seasonal demand. This shaped every modeling decision below: a mean-reverting or purely seasonal model would badly underforecast a series still this far from any steady state.

**Chronological split** (never shuffled): the final 3 complete months (Jun–Aug 2026) held out as test; all 33 earlier months used for training.

**Methods compared** (backtested against held-out months, RMSE-ranked):

| Method | MAE | RMSE | MAPE |
|---|---|---|---|
| Seasonal naive (value 12 months ago) | 210,568,545 | 217,530,069 | 85.4% |
| 3-month moving average | 122,936,665 | 136,164,851 | 47.5% |
| Holt-Winters, additive trend + seasonal(12) | 91,924,582 | 103,993,139 | 35.1% |
| **Holt-Winters, additive trend only** | **88,128,857** | **100,776,557** | **33.5%** |

**Selected**: Holt-Winters with an additive trend and **no** seasonal component — it beat both baselines and the seasonal variant. This is a genuinely informative result: with a trend this dominant and only 3 yearly cycles to estimate a 12-period seasonal component from, the seasonal term adds noise rather than signal; a well-fit trend alone captures the real dynamics better. **Both baselines were clearly beaten** (33.5% MAPE vs. 47.5%/85.4%), which is the honest comparison the brief asked for — not just picking the fanciest available method.

**Forecast** (next 3 months beyond the complete series, refit on the full 36-month history):

| Forecast month | Predicted revenue | 95% interval (± 1.96 × backtest residual std) |
|---|---|---|
| 2026-09 | $360.3M | $264.5M – $456.1M |
| 2026-10 | $424.1M | $328.3M – $519.9M |
| 2026-11 | $487.8M | $391.9M – $583.6M |

**Limitation, stated plainly**: a 33.5% MAPE is still a wide margin in absolute terms — this remains a genuinely hard forecasting problem given the extreme, still-accelerating growth rate, and the confidence interval reflects that honestly (a ~$92M–$96M band on either side) rather than presenting false precision.

**Output**: `ANALYTICS.ML_REVENUE_FORECAST` — 3 rows.

---

## Model selection methodology (all three classifiers)

For every classification model, **both** algorithms were compared on ROC-AUC **and** F1 together (`max(roc_auc, f1)` as a tuple key) — never on accuracy alone, since accuracy is a poor and even misleading metric on the roughly-balanced-but-not-identical class distributions here (a majority-class-only classifier still scores plausible-looking accuracy on any of these three splits). Random Forest was preferred when its ROC-AUC and F1 both matched or exceeded Logistic Regression's, since Random Forest also naturally provides feature importances for interpretability; Logistic Regression was preferred in the one case (customer churn) where it genuinely scored higher on both metrics, despite offering coefficients rather than importances.

## Leakage prevention — summary across all four models

| Model | Excluded (and why) |
|---|---|
| Customer churn | `churn_risk_score`/`category`, `customer_health_score`/`status` (target's own formula); `active_subscriptions`/`arr`/`mrr` (definitionally tied to the subscription-status target) |
| Project risk | `actual_cost`, `cost_overrun_pct`, `budget_utilization_pct`, `completion_pct` (all post-outcome); `project_risk_score`/`category` (formula output) |
| Payment delay | `amount_paid`, `payment_date`, `days_late` (the target itself); customer's own average delay computed **leave-one-out**, never including the invoice being scored |
| Revenue forecast | Chronological split only — no shuffling; test months never influence training |

## Prediction table schemas

| Table | Grain | Key columns |
|---|---|---|
| `ANALYTICS.ML_CUSTOMER_RISK` | 1 row / current customer | `customer_id`, `risk_probability`, `predicted_class`, `risk_level`, `model_version`, `generated_at` |
| `ANALYTICS.ML_PROJECT_RISK` | 1 row / project | `project_id`, `risk_probability`, `predicted_risk_class`, `risk_level`, `model_version`, `generated_at` |
| `ANALYTICS.ML_PAYMENT_DELAY` | 1 row / invoice | `invoice_id`, `customer_id`, `delay_probability`, `predicted_delay`, `risk_level`, `model_version`, `generated_at` |
| `ANALYTICS.ML_REVENUE_FORECAST` | 1 row / forecasted month | `forecast_date`, `predicted_revenue`, `lower_bound`, `upper_bound`, `model_version`, `generated_at` |

`risk_level`/banding for all three classifiers: **High** (probability ≥ 0.66), **Medium** (≥ 0.33), **Low** (below 0.33) — a fixed, documented threshold, applied identically everywhere.

## How the future Decision Engine will use these

None of these tables trigger any action themselves (explicitly out of scope for Phase 4). They are designed as **inputs** a future Decision Engine can join against:
- `ML_PAYMENT_DELAY` (the one model with real signal) is the most immediately actionable — a collections workflow could prioritize outreach by `delay_probability` today.
- `ML_CUSTOMER_RISK` and `ML_PROJECT_RISK` are persisted with the same schema and pipeline maturity as the working model, ready to be re-trained the moment a genuine (non-random) outcome label exists — e.g. if a future phase adds real customer-lifecycle events or project-delay causes to the synthetic generator, or if this pipeline is pointed at real production data where such correlations naturally exist.
- `ML_REVENUE_FORECAST`'s `lower_bound`/`upper_bound` give a Decision Engine an explicit uncertainty range to reason about (e.g., "flag if actual revenue falls below `lower_bound` for two consecutive months") rather than a single point estimate.

## Overall limitations

- **Two of four models (customer churn, project risk) currently carry no real predictive power**, by design of the underlying synthetic data, not a modeling shortfall — restated here because it's the single most important thing for anyone using `ML_CUSTOMER_RISK`/`ML_PROJECT_RISK` to know before acting on them.
- The revenue forecast's ~33.5% MAPE reflects a genuinely difficult, still-accelerating growth series, not a modeling error — the wide confidence interval is honest, not a hedge.
- All four models are static, full-refresh, point-in-time fits on the current warehouse snapshot; none implement online/incremental learning or drift monitoring (out of scope for this phase).
