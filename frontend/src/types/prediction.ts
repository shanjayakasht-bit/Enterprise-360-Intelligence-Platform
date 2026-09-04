/** Matches backend/models/prediction.py */

export interface CustomerRiskPredictionRow {
  customer_id: string
  risk_probability: number | null
  predicted_class: number | null
  risk_level: string | null
  model_version: string
  generated_at: string
}

export interface ProjectRiskPredictionRow {
  project_id: string
  risk_probability: number | null
  predicted_risk_class: number | null
  risk_level: string | null
  model_version: string
  generated_at: string
}

export interface PaymentDelayPredictionRow {
  invoice_id: string
  customer_id: string
  delay_probability: number | null
  predicted_delay: number | null
  risk_level: string | null
  model_version: string
  generated_at: string
}
