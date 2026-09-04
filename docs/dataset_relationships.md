# Dataset Relationships

All ten datasets are relationally consistent: every foreign key below references a real,
existing row in the parent table (enforced during generation and re-checked by
`validation/validate_relationships.py`).

## Entity relationship map

```
customers (hub)
  |-- account_manager_id       -> employees   (department = Account Management)
  |
  |-- leads.customer_id        -> customers
  |     `-- assigned_salesperson_id -> employees (department = Sales)
  |
  |-- deals.customer_id        -> customers
  |     |-- lead_id            -> leads          (nullable; set when the deal came from a converted lead)
  |     `-- sales_rep_id       -> employees       (department = Sales)
  |
  |-- subscriptions.customer_id -> customers
  |     `-- deal_id            -> deals           (nullable; set when a Closed Won deal originated it)
  |
  |-- projects.customer_id     -> customers
  |     |-- deal_id            -> deals           (nullable; set when a Closed Won deal originated it)
  |     `-- project_manager_id -> employees       (department = Project Management)
  |
  |-- invoices.customer_id     -> customers
  |     |-- subscription_id    -> subscriptions   (nullable; mutually exclusive-ish with project_id)
  |     `-- project_id         -> projects        (nullable)
  |
  |-- payments.invoice_id      -> invoices
  |     `-- customer_id        -> customers       (denormalized from the invoice, always consistent with it)
  |
  |-- support_tickets.customer_id -> customers
  |     `-- agent_id           -> employees       (department = Customer Support)
  |
  `-- customer_activity.customer_id -> customers

employees (hub)
  `-- manager_id -> employees (self-referential; null only for the CEO)
```

## Table -> table cardinality

| From | To | Relationship |
|---|---|---|
| customers | employees (account_manager_id) | many-to-one |
| leads | customers | many-to-one |
| leads | employees (salesperson) | many-to-one |
| deals | customers | many-to-one |
| deals | leads | many-to-one, optional (only converted leads) |
| deals | employees (sales rep) | many-to-one |
| subscriptions | customers | many-to-one |
| subscriptions | deals | many-to-one, optional (only Closed Won deals) |
| projects | customers | many-to-one |
| projects | deals | many-to-one, optional (only Closed Won deals) |
| projects | employees (project manager) | many-to-one |
| invoices | customers | many-to-one |
| invoices | subscriptions | many-to-one, optional |
| invoices | projects | many-to-one, optional |
| payments | invoices | many-to-one |
| support_tickets | customers | many-to-one |
| support_tickets | employees (support agent) | many-to-one |
| customer_activity | customers | many-to-one |

## Notes on optional links

- `deals.lead_id` is only set for the share of deals that originated from a lead whose
  `converted_to_deal` is true; the rest are direct opportunities.
- `subscriptions.deal_id` and `projects.deal_id` are only set for the share sourced from a
  `deals` row where `is_won = True`; the rest are treated as pre-existing/direct relationships
  tied straight to the customer.
- `invoices.subscription_id` and `invoices.project_id` are each optional and not both required --
  roughly 65% of invoices bill a subscription, 25% bill a project, and the remainder are
  standalone invoices billed directly to the customer.
- `payments` only exist for invoices whose `status` is `Paid` or `Partially Paid`; `Unpaid`,
  `Overdue`, and `Cancelled` invoices intentionally have zero payment rows.

## Derived fields that depend on other tables

`customers.product_usage_score`, `engagement_score`, `satisfaction_score`,
`support_ticket_count_recent`, `avg_payment_delay_days`, `churn_risk_score`, and
`churn_risk_category` are computed *after* `customer_activity`, `support_tickets`, and
`payments` are generated, by aggregating those tables back onto each customer
(see `data_generator/customers.py::finalize` and `docs/business_rules.md`).
