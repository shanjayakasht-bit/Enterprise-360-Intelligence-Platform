/** Matches backend/models/project.py */
import type { DecisionRef } from './customer'

export interface ProjectRiskCard {
  project_id: string
  customer_id: string
  company_name: string
  department_name: string | null
  project_manager_name: string | null
  status: string
  budget: number | null
  actual_cost: number | null
  completion_pct: number | null
  project_risk_category: string | null
  days_to_deadline: number | null
  risk_probability: number | null
  risk_level: string | null
}

export interface ProjectRiskPrediction {
  risk_probability: number | null
  predicted_risk_class: number | null
  risk_level: string | null
  model_version: string | null
}

export interface ProjectDetail {
  project_id: string
  customer_id: string
  company_name: string
  department_name: string | null
  project_manager_id: string | null
  project_manager_name: string | null
  status: string
  budget: number | null
  actual_cost: number | null
  cost_variance: number | null
  budget_utilization_pct: number | null
  cost_overrun_pct: number | null
  completion_pct: number | null
  project_risk_score: number | null
  project_risk_category: string | null
  planned_end_date: string | null
  days_to_deadline: number | null
  risk_prediction: ProjectRiskPrediction
  active_decisions: DecisionRef[]
}
