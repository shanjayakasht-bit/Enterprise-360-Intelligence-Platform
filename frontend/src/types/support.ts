/** Matches backend/models/support.py::SupportMetricsResponse */
export interface SupportMetricsResponse {
  total_tickets: number
  open_tickets: number
  high_priority_tickets: number
  sla_breaches: number
  avg_resolution_time_hours: number | null
  avg_satisfaction_rating: number | null
}
