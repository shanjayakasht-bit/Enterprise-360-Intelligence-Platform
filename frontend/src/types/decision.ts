/** Matches backend/models/decision.py */

export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
export type DecisionStatus = 'NEW' | 'ACKNOWLEDGED' | 'IN_PROGRESS' | 'RESOLVED' | 'DISMISSED'
export type DecisionType =
  | 'CUSTOMER_RETENTION'
  | 'PROJECT_DELIVERY'
  | 'PAYMENT_COLLECTION'
  | 'REVENUE_OPPORTUNITY'
  | 'BUSINESS_ANOMALY'

export interface BusinessImpact {
  type: string | null
  value: number | null
}

export interface DecisionCard {
  decision_id: string
  decision_type: string
  entity_type: string
  entity_id: string
  title: string
  summary: string | null
  severity: string
  priority_score: number
  what_happened: string
  why_it_happened: string
  predicted_outcome: string | null
  business_impact: BusinessImpact
  confidence: number | null
  recommended_actions: string[]
  status: string
  generated_at: string
}

export interface DecisionSummaryResponse {
  critical_decisions: number
  high_priority_decisions: number
  customers_at_risk: number
  revenue_at_risk: number
  projects_at_risk: number
  payment_value_at_risk: number
  revenue_opportunity_value: number
  generated_at: string
}
