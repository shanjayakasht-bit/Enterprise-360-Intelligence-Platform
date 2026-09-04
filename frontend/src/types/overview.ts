/** Matches backend/models/overview.py::OverviewResponse */
export interface OverviewResponse {
  total_revenue: number | null
  active_customers: number | null
  active_subscriptions: number | null
  active_projects: number | null
  projects_at_risk: number | null
  open_support_tickets: number | null
  support_sla_percentage: number | null
  average_customer_health: number | null
  total_invoice_amount: number | null
  total_payments_received: number | null
  outstanding_amount: number | null
  enterprise_health_score: number | null

  critical_decisions: number | null
  high_priority_decisions: number | null
  customers_at_risk: number | null
  revenue_at_risk: number | null
  payment_value_at_risk: number | null
  revenue_opportunity_value: number | null
}
