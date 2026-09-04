"""Generates the payments dataset. Every payment references a real invoice that is
Paid or Partially Paid, and per-invoice payment totals never exceed the invoice
total. Payment timing is biased by each customer's payment-reliability propensity."""

import pandas as pd
from dateutil.relativedelta import relativedelta

from .master_data import NP_RNG, PAYMENT_METHODS, REFERENCE_DATE, RNG, make_id


def _payment_row(counter, invoice, customer_id, payment_date, amount_paid, due_date):
    return {
        "payment_id": make_id("PAY", counter),
        "invoice_id": invoice["invoice_id"],
        "customer_id": customer_id,
        "payment_date": payment_date.isoformat(),
        "amount_paid": round(amount_paid, 2),
        "payment_method": RNG.choice(PAYMENT_METHODS),
        "payment_status": "Completed",
        "days_late": (payment_date - due_date).days,
    }


def generate(invoices_df, customers_df):
    reliability_lookup = customers_df.set_index("customer_id")["_payment_reliability"]

    rows = []
    counter = 1
    payable = invoices_df[invoices_df["status"].isin(["Paid", "Partially Paid"])].to_dict("records")

    for invoice in payable:
        customer_id = invoice["customer_id"]
        reliability = float(reliability_lookup.loc[customer_id])

        due_date = pd.Timestamp(invoice["due_date"]).date()
        invoice_date = pd.Timestamp(invoice["invoice_date"]).date()

        delay_days = int(round(NP_RNG.normal((1 - reliability) * 20 - 5, 7)))
        payment_date = due_date + relativedelta(days=delay_days)
        payment_date = max(invoice_date, min(payment_date, REFERENCE_DATE))

        if invoice["status"] == "Partially Paid":
            amount_paid = invoice["total_amount"] * RNG.uniform(0.25, 0.75)
            rows.append(_payment_row(counter, invoice, customer_id, payment_date, amount_paid, due_date))
            counter += 1
            continue

        if RNG.random() < 0.08:
            first_amount = invoice["total_amount"] * RNG.uniform(0.3, 0.6)
            rows.append(_payment_row(counter, invoice, customer_id, payment_date, first_amount, due_date))
            counter += 1
            second_date = min(payment_date + relativedelta(days=RNG.randint(1, 20)), REFERENCE_DATE)
            rows.append(_payment_row(
                counter, invoice, customer_id, second_date, invoice["total_amount"] - first_amount, due_date,
            ))
            counter += 1
        else:
            rows.append(_payment_row(counter, invoice, customer_id, payment_date, invoice["total_amount"], due_date))
            counter += 1

    return pd.DataFrame(rows)
