/** Matches backend/models/revenue.py */

export interface RevenueTrendPoint {
  period_start: string
  period_label: string | null
  deal_revenue: number | null
  subscription_mrr_booked: number | null
  subscription_arr_booked: number | null
  invoice_amount: number | null
  payments_received: number | null
}

export interface RevenueTrendsResponse {
  period: string
  points: RevenueTrendPoint[]
}

export interface RevenueForecastPoint {
  forecast_date: string
  predicted_revenue: number
  lower_bound: number
  upper_bound: number
  model_version: string
  generated_at: string
}

export interface RevenueHistoricalPoint {
  month: string
  invoice_amount: number
}

export interface RevenueForecastResponse {
  historical_context: RevenueHistoricalPoint[]
  forecast: RevenueForecastPoint[]
}

export interface RevenueByRegionRow {
  region_name: string
  deal_revenue: number | null
  invoice_amount: number | null
  payments_received: number | null
}

export interface RevenueByRegionResponse {
  rows: RevenueByRegionRow[]
}
