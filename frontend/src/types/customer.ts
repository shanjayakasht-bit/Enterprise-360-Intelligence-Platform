/** Matches backend/models/customer.py */

export interface CustomerCard {
  customer_id: string
  company_name: string
  segment: string | null
  region: string | null
  industry: string | null
  total_revenue: number | null
  arr: number | null
  customer_health_score: number | null
  customer_status: string | null
  risk_probability: number | null
  risk_level: string | null
  cluster_segment_name: string | null
}

export interface CustomerProfile {
  customer_id: string
  company_name: string
  segment: string | null
  region: string | null
  industry: string | null
  customer_status: string | null
  customer_health_score: number | null
  renewal_date: string | null
  days_to_renewal: number | null
}

export interface CustomerRevenue {
  total_deal_value: number | null
  won_deal_value: number | null
  total_revenue: number | null
  arr: number | null
  mrr: number | null
}

export interface CustomerSubscriptions {
  active_subscriptions: number | null
  arr: number | null
  mrr: number | null
}

export interface CustomerProjects {
  project_count: number | null
  delayed_projects: number | null
  project_risk: number | null
}

export interface CustomerFinance {
  invoice_total: number | null
  payments_received: number | null
  outstanding_amount: number | null
  average_payment_delay: number | null
}

export interface CustomerSupport {
  support_ticket_count: number | null
  open_ticket_count: number | null
  sla_breaches: number | null
  average_support_satisfaction: number | null
}

export interface CustomerActivity {
  activity_count: number | null
  average_usage_score: number | null
  recent_activity_date: string | null
}

export interface CustomerSegmentInfo {
  churn_risk_score: number | null
  churn_risk_category: string | null
  cluster_id: number | null
  cluster_segment_name: string | null
  distance_from_centroid: number | null
}

export interface CustomerRiskPrediction {
  risk_probability: number | null
  predicted_class: number | null
  risk_level: string | null
  model_version: string | null
}

export interface DecisionRef {
  decision_id: string
  decision_type: string
  title: string
  severity: string
  priority_score: number
  status: string
  generated_at: string
}

export interface CustomerSegmentCount {
  segment_name: string
  customer_count: number
}

export interface CustomerSegmentSummaryResponse {
  total_customers: number
  segments: CustomerSegmentCount[]
}

export interface CustomerDetail {
  profile: CustomerProfile
  revenue: CustomerRevenue
  subscriptions: CustomerSubscriptions
  projects: CustomerProjects
  finance: CustomerFinance
  support: CustomerSupport
  activity: CustomerActivity
  segment: CustomerSegmentInfo
  risk_prediction: CustomerRiskPrediction
  active_decisions: DecisionRef[]
}
