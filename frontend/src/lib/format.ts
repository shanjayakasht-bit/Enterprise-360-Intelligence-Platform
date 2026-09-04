const numberCompact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 })
const numberFull = new Intl.NumberFormat('en-US')

/** NEXORA's single monetary unit, used everywhere on the dashboard: Indian
 * Rupees, formatted with the lakh/crore convention rather than Western
 * thousand/million grouping. This is presentation-only -- Snowflake stores
 * plain numeric amounts with no currency unit attached, so relabeling the
 * unit here changes no stored value. Every currency display in the app
 * must go through one of these two functions so the ₹ unit and
 * lakh/crore breakpoints never drift or get mixed with $. */
const LAKH = 100_000
const CRORE = 1_00_00_000

function splitSign(value: number): { sign: string; abs: number } {
  return value < 0 ? { sign: '-', abs: -value } : { sign: '', abs: value }
}

/** e.g. ₹12.4L, ₹3.8Cr, ₹300.3Cr, ₹8.2K, ₹450 */
export function formatCurrencyCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const { sign, abs } = splitSign(value)
  if (abs >= CRORE) return `${sign}₹${(abs / CRORE).toFixed(1)}Cr`
  if (abs >= LAKH) return `${sign}₹${(abs / LAKH).toFixed(1)}L`
  if (abs >= 1_000) return `${sign}₹${(abs / 1_000).toFixed(1)}K`
  return `${sign}₹${abs.toFixed(0)}`
}

const inrFullFormatter = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })

/** Full-precision INR with Indian digit grouping, e.g. ₹1,23,45,678 */
export function formatCurrencyFull(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const { sign, abs } = splitSign(value)
  return `${sign}₹${inrFullFormatter.format(abs)}`
}

export function formatNumberCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return numberCompact.format(value)
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return numberFull.format(value)
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${value.toFixed(digits)}%`
}

/** Some backend fields (e.g. risk_probability, confidence/100) arrive as a
 * 0-1 fraction rather than an already-scaled percentage -- this makes that
 * distinction explicit at every call site instead of guessing. */
export function formatFractionAsPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('en-US', { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

export function formatMonthLabel(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short' })
}
