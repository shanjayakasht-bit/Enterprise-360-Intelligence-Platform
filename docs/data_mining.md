# NEXORA Phase 3 — Data Mining

Source: `NEXORA_DB.ANALYTICS`/`CORE` exclusively (no RAW CSVs, no STAGING) via `mining/common.py`'s `fetch_dataframe()`. Every pipeline reads only; results are written to four new `ANALYTICS.DM_*` tables via a full-refresh (`TRUNCATE` + bulk insert), never touching RAW, STAGING, CORE, or any existing ANALYTICS view/KPI definition.

This phase implements **descriptive and unsupervised** data mining — clustering, association mining, and outlier detection. None of it predicts a future outcome, and none of it is presented as one. Segment membership describes present behavior, not a forecast; anomaly flags describe statistical unusualness, not a diagnosis; association rules describe historical co-occurrence, not causation.

---

## 1. Customer Segmentation

### Objective
Group NEXORA's 5,000 current customers into a small number of behaviorally distinct, business-interpretable segments, using only measurements the warehouse already validated — no new business logic, no manually-assigned labels used as inputs.

### Selected features (11, from `ANALYTICS.VW_CUSTOMER_360`)

| Feature | Category |
|---|---|
| `TOTAL_REVENUE` | Revenue |
| `ARR` | Recurring revenue |
| `ACTIVE_SUBSCRIPTIONS` | Engagement breadth |
| `AVERAGE_USAGE_SCORE` | Usage/engagement |
| `SUPPORT_TICKET_COUNT` | Support volume |
| `SLA_BREACHES` | Support quality |
| `AVERAGE_SUPPORT_SATISFACTION` | Support quality |
| `AVERAGE_PAYMENT_DELAY` | Payment behavior |
| `OUTSTANDING_AMOUNT` | Financial risk |
| `PROJECT_RISK` | Delivery risk |
| `CUSTOMER_HEALTH_SCORE` | Composite health |

**Deliberately excluded, and why:**
- `CUSTOMER_ID` / `COMPANY_NAME` — identifiers, not behavior.
- `SEGMENT` / `REGION` / `INDUSTRY` — categorical business attributes, used only for post-hoc profiling, never as clustering inputs.
- `CUSTOMER_STATUS` — this is a **manually-assigned business label** (a relabeling of Phase 1's `churn_risk_category`). Including it as a feature would let clustering trivially reproduce that label instead of discovering independent structure — exactly the leakage the brief warned against.
- `WON_DEAL_VALUE`, `MRR` — near-duplicates of `TOTAL_REVENUE` and `ARR` respectively (`MRR = ARR / 12` exactly); including both would double-weight the same signal.
- `ACTIVITY_COUNT`, `DELAYED_PROJECTS`, `OPEN_TICKET_COUNT`, `PROJECT_COUNT`, `RECENT_ACTIVITY_DATE` — lower-resolution proxies of signals already captured above; dropped to keep the feature set compact and non-redundant.

### Preprocessing

- **Null handling (explicit, per column, not blanket-filled):**
  - `AVERAGE_PAYMENT_DELAY` NULL (549 customers with zero recorded payments) → **0**. There is no observed delay; 0 is the honest "no evidence of delay" value, not a guess.
  - `PROJECT_RISK` NULL (1,019 customers with zero projects) → **0**. There is no project to carry risk.
  - `AVERAGE_SUPPORT_SATISFACTION` NULL (51 customers with zero rated tickets) → **population median**. This genuinely is unknown (not "zero satisfaction"), so an assumed extreme would misrepresent it.
- **Outlier capping:** `TOTAL_REVENUE`, `ARR`, and `OUTSTANDING_AMOUNT` are heavily right-skewed (e.g. `OUTSTANDING_AMOUNT`'s max is ~9× its own 95th percentile). Each is winsorized (capped) at the **99th percentile**, affecting exactly 50 of 5,000 customers per column — enough to stop a handful of very large accounts from single-handedly dragging cluster centroids toward them, without discarding any customer or distorting the bulk of the distribution.
- **Scaling:** `StandardScaler` (zero mean, unit variance) — required because K-Means uses Euclidean distance, and these 11 features live on wildly different scales (dollars in the millions vs. scores 0–100 vs. small integer counts). Without scaling, revenue alone would dominate every distance calculation.

### K selection (evidence-based, not assumed)

K-Means was fit for every K from 2 to 8 (`random_state=42`, `n_init=10`), and both inertia and silhouette score were recorded — **K was not forced to 5**:

| K | Inertia | Silhouette |
|---|---|---|
| 2 | 44,590.8 | 0.2152 |
| **3** | **36,203.9** | **0.2321** |
| 4 | 32,495.5 | 0.2009 |
| 5 | 29,459.7 | 0.1895 |
| 6 | 27,146.2 | 0.1814 |
| 7 | 25,667.8 | 0.1761 |
| 8 | 24,467.0 | 0.1662 |

Silhouette peaks at **K=3** and declines monotonically afterward; K=2's silhouette (0.2152) is also lower than K=3's. **K=3 was selected purely on this evidence** — it isn't a business-usability tie-breaker overriding the metric; the metric and the business preference for ≥3 segments happened to agree.

**Honest caveat:** a silhouette of 0.23 is, on the standard interpretation scale, "weak — no strong structure found" (>0.5 would be "reasonable," >0.7 "strong"). This is reported as-is, not oversold. It reflects that these 11 behavioral features vary fairly continuously across NEXORA's customer base rather than falling into sharply separated archetypes — expected for independently-generated synthetic behavioral data, and still useful: even soft/overlapping clusters produce a real, actionable summary of where the customer base's behavior actually concentrates.

### Cluster profiles (raw, unscaled feature means)

| | Cluster 0 | Cluster 1 | Cluster 2 |
|---|---|---|---|
| **Customers** | 326 | 1,654 | 3,020 |
| Avg total revenue | $438,367 | $32,221 | $31,432 |
| Avg ARR | $389,336 | $30,230 | $33,228 |
| Avg active subscriptions | 1.83 | 0.92 | 0.95 |
| Avg usage score | 53.3 | 25.4 | 70.2 |
| Avg support tickets | 8.1 | 11.2 | 6.2 |
| Avg SLA breaches | 0.09 | 0.28 | 0.02 |
| Avg support satisfaction | 4.00 | 3.42 | 4.39 |
| Avg payment delay (days) | −8.5 | −1.9 | −9.7 |
| Avg outstanding amount | $1,388,847 | $61,632 | $66,554 |
| Avg project risk | 40.7 | 33.2 | 31.9 |
| Avg customer health score | 60.6 | 45.0 | 70.5 |

### Business segment interpretation (derived from the table above, not assumed)

- **Cluster 0 → "At Risk (High Value)"** (326 customers, 6.5%). By far the highest revenue and ARR, but also by far the highest outstanding balance and project risk, with only mid-pack health. These are NEXORA's biggest accounts, carrying disproportionate financial and delivery exposure — the clearest "protect this revenue" watchlist.
- **Cluster 1 → "At Risk"** (1,654 customers, 33.1%). The lowest usage score, highest support ticket volume, highest SLA breach rate, lowest satisfaction, and lowest health score of the three — the least healthy segment on every support/engagement dimension, though not a high-value one.
- **Cluster 2 → "Stable"** (3,020 customers, 60.4%). The highest usage, highest health score, highest satisfaction, and lowest project risk — clearly the healthiest segment — but at similar (modest) revenue to Cluster 1. Named "Stable" rather than "Strategic" specifically because it's healthy *without* being high-value; "Strategic" is reserved for a cluster that is both, which did not emerge at K=3.

**Naming methodology:** implemented as a transparent rule (`mining/customer_segmentation.py::name_segments`), not a one-off manual choice — each cluster's centroid (already in z-score units, since K-Means fit on standardized features) is summarized into three axes (value, health, engagement) and classified against fixed thresholds (±0.3 std). This makes the naming reproducible and auditable, while still being "reviewed after clustering" in spirit: the thresholds and axis definitions were chosen by inspecting what the real cluster centroids looked like, not decided blind beforehand. No cluster was forced into a preset name list — at this K, "Strategic," "Growth," and "Low Engagement" simply didn't match any actual cluster's profile, so they don't appear, and that absence is itself reported as a finding (see above) rather than papered over.

### Output tables
- `ANALYTICS.DM_CUSTOMER_SEGMENTS` — 5,000 rows, one per customer: `customer_id`, `cluster_id`, `segment_name`, `distance_from_centroid` (Euclidean, in scaled-feature space), `generated_at`.
- `ANALYTICS.DM_CUSTOMER_CLUSTER_PROFILE` — 3 rows, one per cluster: every raw feature's cluster mean, `customer_count`, `selected_k`, `silhouette_score`, `generated_at`.

---

## 2. Service Association Mining

### Transaction ("basket") definition
One basket per customer = the set of distinct services that customer has a **successful/active** relationship with, drawn from three CORE fact tables:

| Source | Included | Excluded, and why |
|---|---|---|
| `FACT_DEALS` | `is_won = TRUE` only | Lost or still-open deals never became a real transaction — explicitly the brief's own caution against treating lost deals as purchases. |
| `FACT_SUBSCRIPTIONS` | **all** statuses (Active/Cancelled/Expired/Paused) | A subscription row proves a sale happened and billing started at some point; unlike a lost deal, a since-cancelled subscription still represents a real historical purchase, so excluding it would understate genuine co-occurrence. |
| `FACT_PROJECTS` | every status **except** `Cancelled` | A project record means a service engagement was contracted; only a genuinely cancelled (never-delivered) engagement is excluded, for the same "don't count what never materialized" reasoning applied to deals. |

Items are namespaced by source category — `"Product: <name>"`, `"Plan: <name>"`, `"Engagement: <name>"` — since `DIM_SERVICE`'s three categories are different label spaces (a product name, a subscription tier, a project-engagement type); collapsing them into bare names would risk an accidental collision and blur what kind of relationship a rule expresses.

This produced **4,522 non-empty baskets** (of 5,000 customers — 478 have no won deal, subscription, or non-cancelled project and are excluded, correctly, from association mining). Basket sizes range 1–12 items (median 4), giving genuine co-occurrence signal to mine.

### Algorithm
**FP-Growth** (via `mlxtend.frequent_patterns.fpgrowth`), preferred over Apriori as instructed — FP-Growth builds a compact FP-tree in two database passes instead of Apriori's repeated full-database candidate-generation scans, which matters here since the basket-encoded matrix has 15 possible items × 4,522 baskets.

### Thresholds — chosen empirically, not guessed

| Threshold | Value | Rationale |
|---|---|---|
| Minimum support | **0.03** (≥3% of baskets, ~136 of 4,522) | Below this, FP-Growth on this dataset surfaces itemsets appearing in only a handful of customers — too thin to generalize into a business recommendation. 0.03 was the smallest value tested that kept the frequent-itemset count in a reviewable range (307 itemsets) rather than exploding into noise. |
| Minimum confidence | **0.30** | A rule "given A, 30%+ buy B" is a real, actionable lift over base rates for a 15-item catalog (base rate for any single item is roughly 1/15 ≈ 7%); below 0.30 the signal-to-noise ratio dropped sharply in testing. |
| Minimum lift | **1.1** | Lift > 1 is the mathematical minimum for a rule to mean "more likely together than by chance" at all; 1.1 was set as a small but real margin above that floor, filtering out rules that technically clear 1.0 but are statistically indistinguishable from independence. |

These three thresholds were tuned by running FP-Growth across a range of candidates and observing the resulting rule count and quality — not picked in the abstract before looking at the data.

### Result
**90 rules** survived all three filters, restricted to clean 1-antecedent → 1-consequent pairs (multi-item antecedents/consequents were both rarer and harder to act on with only 15 possible items). Reverse pairs (A→B and B→A) are **intentionally both kept** — their confidence values genuinely differ by direction (e.g. "given Product A, 35% also have Engagement B" vs. "given Engagement B, 34% also have Product A" are different, both-useful statements), which is exactly the brief's own carve-out ("avoid duplicate reverse rules **unless useful**").

**Top rules by lift** (all cross NEXORA's flagship products with related project-engagement types):

| Antecedent | Consequent | Support | Confidence | Lift |
|---|---|---|---|---|
| Product: NEXORA Managed Services | Engagement: Implementation | 0.082 | 0.348 | 1.46 |
| Product: NEXORA CRM Suite | Engagement: Platform Upgrade | 0.081 | 0.343 | 1.44 |
| Product: NEXORA CRM Suite | Engagement: Implementation | 0.081 | 0.340 | 1.43 |
| Product: NEXORA Analytics Cloud | Engagement: Data Migration | 0.083 | 0.355 | 1.42 |
| Product: NEXORA Managed Services | Engagement: Data Migration | 0.083 | 0.354 | 1.41 |

**Reading these correctly:** a customer who bought Managed Services is ~46% more likely than average to also have an Implementation-type project engagement. This is a co-occurrence pattern useful for cross-sell targeting and delivery-capacity planning — **not** a causal claim that buying one causes the other.

### Output table
`ANALYTICS.DM_SERVICE_ASSOCIATIONS` — 90 rows: `antecedent`, `consequent`, `support`, `confidence`, `lift`, `transaction_count`, `generated_at`.

---

## 3. Business Anomaly Detection

### Input datasets (two, deliberately distinct)

1. **`entity_type='CUSTOMER'`**, from `ANALYTICS.VW_CUSTOMER_360`: `TOTAL_REVENUE`, `OUTSTANDING_AMOUNT`, `AVERAGE_PAYMENT_DELAY`, `SUPPORT_TICKET_COUNT`, `AVERAGE_USAGE_SCORE` — covers the brief's "abnormal revenue," "unusual outstanding amount," "unusual payment delays," and "abnormal support-ticket volume" examples directly.
2. **`entity_type='PROJECT'`**, from `ANALYTICS.VW_PROJECT_RISK`: `BUDGET`, `ACTUAL_COST`, `COST_VARIANCE`, `BUDGET_UTILIZATION_PCT`, `COST_OVERRUN_PCT` — covers "unusual project-cost patterns."

These are genuinely complementary, not redundant with clustering: clustering groups the *typical* population into structure, while Isolation Forest looks for individual records that don't fit *any* group well — a different question, on a partially different feature set (project cost data has no equivalent in the customer-level clustering features).

### Isolation Forest configuration
- `contamination=0.05` — a conventional starting point when there's no labeled ground truth to tune a contamination rate against (this is genuinely unsupervised; there's no "known anomaly" set in this dataset to validate a different rate).
- `n_estimators=200`, `random_state=42`.
- **Scaling before fitting**: every feature set is passed through `StandardScaler` first, per the explicit instruction not to mix incomparable data without scaling — `BUDGET`/`ACTUAL_COST` (dollars, six figures) and `BUDGET_UTILIZATION_PCT`/`COST_OVERRUN_PCT` (percentages) would otherwise be on wildly different scales.
- Null handling: any null feature value is filled with that column's own median (explicit, logged) before scaling.

### Anomaly score interpretation
`anomaly_score` is Isolation Forest's raw `decision_function()` output: **more negative = more anomalous**, positive = solidly normal. `is_anomaly` is `predict() == -1`. At `contamination=0.05`, this flags **exactly 5%** of each entity population by construction (250/5,000 customers, 400/8,000 projects) — this is the parameter's designed behavior, not a discovered rate; a different `contamination` value would flag a different count without the underlying data changing.

### Explainability, not causation
For every scored record, the two features with the largest absolute z-score are surfaced as `observed_value` (the actual value and its z-score) and `expected_context` (the population median for that same feature) — a transparent, re-derivable "what stood out," computed directly from the input features. **This is not Isolation Forest explaining itself** (the model has no built-in explanation mechanism) — it's a separate, simple post-hoc calculation over the same standardized features the model saw, and it's presented as exactly that: which measurements were unusual, never why they were unusual or what caused it.

**Most anomalous customers** (all driven by extreme revenue + outstanding-amount combinations, e.g. CUST003241 at `TOTAL_REVENUE=$1,391,548 (z=+9.6)`, `OUTSTANDING_AMOUNT=$3,717,069 (z=+6.6)`) — these are NEXORA's largest accounts carrying proportionally large unpaid balances, a legitimate finance/collections signal.

**Most anomalous project** (PROJ007543, `ACTUAL_COST=$1,406,162 (z=+5.9)`, `COST_OVERRUN_PCT=31.7% (z=+4.0)`) — a project running dramatically over cost and over budget, a legitimate delivery-escalation signal.

### Limitations (stated plainly)
- Isolation Forest identifies **statistical rarity in the chosen feature space**, not "problems" in a business sense — an unusually *good* outlier (e.g. an exceptionally low-cost, high-value project) scores the same way as a concerning one; a human still has to interpret which flagged records matter and why.
- The 5% contamination rate is a modeling choice, not a discovered fact about how much anomalous behavior actually exists in NEXORA's business.
- Two independent passes were run rather than one combined model — customer financial/support behavior and project cost behavior are different questions on different entities, and forcing them into one feature space would either drop meaningful signal or produce an uninterpretable blended score.

### Output table
`ANALYTICS.DM_BUSINESS_ANOMALIES` — 13,000 rows (5,000 customers + 8,000 projects): `entity_type`, `entity_id`, `anomaly_type`, `anomaly_score`, `is_anomaly`, `observed_value`, `expected_context`, `generated_at`.

---

## How Phase 3 satisfies the Data Mining requirement

Three of the canonical, syllabus-standard data mining task families are implemented, each against real warehouse data, each validated end-to-end:

1. **Clustering** (unsupervised grouping) — K-Means with proper evidence-based model selection (elbow/inertia + silhouette across multiple K), standardized features, explicit outlier and null handling, and human-interpretable cluster profiling — not a predictive model, and not presented as one.
2. **Association rule mining** — FP-Growth over business-defined transactions, with support/confidence/lift computed and justified thresholds applied, producing genuinely interpretable cross-sell/bundling insight.
3. **Anomaly/outlier detection** — Isolation Forest over two distinct, scaled, meaningful business feature sets, with transparent (not model-derived) explanations for every flagged record.

None of the three constitutes predictive modeling (no train/test split against a future-outcome label, no forecasting, no classification of a business outcome that hasn't happened yet) — consistent with the explicit instruction to defer predictive ML, revenue forecasting, and churn/risk prediction to a later phase.

---

## Commands

```
python -m mining.customer_segmentation
python -m mining.association_rules
python -m mining.anomaly_detection
python -m etl.validate_mining
```

## Validation results (live run)

```
Customer Segmentation
Eligible customers: 5000
Clustered customers: 5000
Selected K: 3
Silhouette Score: 0.2321
PASS

Association Rules
Rules generated: 90
PASS

Anomaly Detection
Records scored: 13000
Anomalies detected: 650
Anomaly rate: 5.0%
PASS

Mining tables checked: 4
Passed: 57
Failed: 0
```
