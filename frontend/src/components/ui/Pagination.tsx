import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { PageInfo } from '@/types/common'

interface PaginationProps {
  pageInfo: PageInfo
  onPageChange: (page: number) => void
}

export function Pagination({ pageInfo, onPageChange }: PaginationProps) {
  const { page, total_pages, total_items, page_size } = pageInfo
  const start = total_items === 0 ? 0 : (page - 1) * page_size + 1
  const end = Math.min(page * page_size, total_items)

  return (
    <div className="flex items-center justify-between border-t border-border px-1 py-3 text-xs text-slate-500">
      <span>
        Showing <span className="font-medium text-slate-700">{start}</span>–
        <span className="font-medium text-slate-700">{end}</span> of{' '}
        <span className="font-medium text-slate-700">{total_items.toLocaleString()}</span>
      </span>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className="flex items-center gap-1 rounded-lg border border-border bg-surface px-2 py-1.5 font-medium text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          Prev
        </button>
        <span className="px-2 font-medium text-slate-700">
          Page {page} of {Math.max(total_pages, 1)}
        </span>
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= total_pages}
          className="flex items-center gap-1 rounded-lg border border-border bg-surface px-2 py-1.5 font-medium text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Next
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}
