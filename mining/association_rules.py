"""Phase 3 data mining: service association mining via FP-Growth over
customer-service "baskets" built from CORE.FACT_DEALS / FACT_SUBSCRIPTIONS /
FACT_PROJECTS. Run as:

    python -m mining.association_rules

Writes ANALYTICS.DM_SERVICE_ASSOCIATIONS. Full detail and rationale for
every threshold is in docs/data_mining.md.
"""

import sys

import pandas as pd
from mlxtend.frequent_patterns import association_rules, fpgrowth
from mlxtend.preprocessing import TransactionEncoder

from mining.common import fetch_dataframe, get_logger, run_timestamp, write_table

logger = get_logger("association_rules")

# Basket definition -- what counts as a "purchased/active" service:
#   FACT_DEALS         only is_won = TRUE ("Closed Won"). A lost or still-open
#                       deal never became a real transaction, so it is excluded
#                       -- exactly the "don't treat lost deals as purchased"
#                       instruction.
#   FACT_SUBSCRIPTIONS ALL statuses (Active/Cancelled/Expired/Paused). A
#                       subscription row means a sale happened and billing
#                       started at some point; its CURRENT status doesn't
#                       change the fact that it was purchased (unlike a deal
#                       that never closed). Excluding Cancelled/Expired here
#                       would understate real historical purchase co-occurrence.
#   FACT_PROJECTS       every status except 'Cancelled'. A project record means
#                       a service engagement was contracted; only a genuinely
#                       cancelled (never delivered) engagement is excluded, by
#                       the same "don't count what never materialized" logic
#                       applied to deals.
#
# Items are namespaced by category ("Product: X" / "Plan: Y" / "Engagement: Z")
# since DIM_SERVICE's three categories are different label spaces (a product
# name, a subscription tier, a project-engagement type) and collapsing them
# into bare names would risk an accidental collision and would blur what
# kind of relationship a rule expresses.
BASKET_SQL = """
WITH items AS (
    SELECT d.customer_key, 'Product: ' || sv.service_name AS item
    FROM CORE.FACT_DEALS d
    JOIN CORE.DIM_SERVICE sv ON sv.service_key = d.service_key
    WHERE d.is_won = TRUE

    UNION

    SELECT s.customer_key, 'Plan: ' || sv.service_name AS item
    FROM CORE.FACT_SUBSCRIPTIONS s
    JOIN CORE.DIM_SERVICE sv ON sv.service_key = s.service_key

    UNION

    SELECT p.customer_key, 'Engagement: ' || sv.service_name AS item
    FROM CORE.FACT_PROJECTS p
    JOIN CORE.DIM_SERVICE sv ON sv.service_key = p.service_key
    WHERE p.status <> 'Cancelled'
)
SELECT customer_key, item FROM items
"""

# Thresholds -- see docs/data_mining.md for the empirical tuning behind
# these exact numbers (chosen by running FP-Growth across a range of
# candidates and picking the smallest thresholds that still produce a
# manageable, non-trivial rule set on this dataset's ~4,500 baskets).
MIN_SUPPORT = 0.03    # an item(set) must appear in >=3% of customer baskets (~136 of ~4,522)
MIN_CONFIDENCE = 0.30  # antecedent -> consequent must hold >=30% of the time
MIN_LIFT = 1.1         # consequent must be >=10% more likely given the antecedent than at random


def build_baskets():
    df = fetch_dataframe(BASKET_SQL)
    baskets = df.groupby("CUSTOMER_KEY")["ITEM"].apply(list).tolist()
    return baskets


def mine_rules(baskets):
    te = TransactionEncoder()
    te_array = te.fit(baskets).transform(baskets)
    basket_df = pd.DataFrame(te_array, columns=te.columns_)

    frequent_itemsets = fpgrowth(basket_df, min_support=MIN_SUPPORT, use_colnames=True)
    logger.info("FP-Growth found %d frequent itemsets at min_support=%.3f", len(frequent_itemsets), MIN_SUPPORT)
    if frequent_itemsets.empty:
        return pd.DataFrame(), len(baskets)

    rules = association_rules(
        frequent_itemsets, metric="confidence", min_threshold=MIN_CONFIDENCE, num_itemsets=len(basket_df),
    )
    rules = rules[rules["lift"] >= MIN_LIFT]

    # Keep only single-item -> single-item rules: with 15 possible items and
    # ~4,500 baskets, multi-item antecedents/consequents are both rarer and
    # harder for a business reader to act on than clean 1:1 relationships.
    rules = rules[(rules["antecedents"].apply(len) == 1) & (rules["consequents"].apply(len) == 1)]

    rules["antecedent"] = rules["antecedents"].apply(lambda s: next(iter(s)))
    rules["consequent"] = rules["consequents"].apply(lambda s: next(iter(s)))

    # An item never implies itself -- structurally impossible here since
    # mlxtend's frequent_itemsets never pairs an item with itself, but
    # checked explicitly (and re-checked in etl/validate_mining.py) since
    # it's an explicit validation requirement.
    rules = rules[rules["antecedent"] != rules["consequent"]]

    rules["transaction_count"] = (rules["support"] * len(basket_df)).round().astype(int)

    logger.info("%d rules survived confidence>=%.2f and lift>=%.2f", len(rules), MIN_CONFIDENCE, MIN_LIFT)
    return rules[["antecedent", "consequent", "support", "confidence", "lift", "transaction_count"]], len(baskets)


def run():
    baskets = build_baskets()
    logger.info("Built %d customer baskets (customers with >=1 eligible transaction)", len(baskets))

    rules, n_baskets = mine_rules(baskets)
    generated_at = run_timestamp()

    if rules.empty:
        logger.warning("No rules survived the configured thresholds -- writing an empty result set")
        output = pd.DataFrame(columns=[
            "ANTECEDENT", "CONSEQUENT", "SUPPORT", "CONFIDENCE", "LIFT", "TRANSACTION_COUNT", "GENERATED_AT",
        ])
    else:
        output = rules.rename(columns={
            "antecedent": "ANTECEDENT", "consequent": "CONSEQUENT", "support": "SUPPORT",
            "confidence": "CONFIDENCE", "lift": "LIFT", "transaction_count": "TRANSACTION_COUNT",
        }).sort_values("LIFT", ascending=False).reset_index(drop=True)
        output["GENERATED_AT"] = generated_at

    write_table(output, "DM_SERVICE_ASSOCIATIONS")

    if not output.empty:
        logger.info("Top rules by lift:\n%s", output.head(10).to_string(index=False))

    return {"n_baskets": n_baskets, "n_rules": len(output), "rules_df": output}


if __name__ == "__main__":
    try:
        run()
    except Exception:
        logger.exception("association_rules pipeline failed")
        sys.exit(1)
