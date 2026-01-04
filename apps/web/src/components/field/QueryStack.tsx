import { useState } from 'react'
import { ChevronUp, ChevronDown } from 'lucide-react'
import type { QueryWithPages } from '../../types'

interface QueryStackProps {
  queries: QueryWithPages[]
  activeQueryId: string | null
  onSelectQuery: (queryId: string) => void
}

function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength - 3) + '...'
}

function getDisplayTitle(query: QueryWithPages): string {
  if (query.displayTitle) return query.displayTitle
  return truncateText(query.queryText, 40)
}

/**
 * QueryStack - Shows history of previous queries (not the active one).
 * The active query bubble is handled by ActiveQueryBubble component.
 */
export function QueryStack({ queries, activeQueryId, onSelectQuery }: QueryStackProps) {
  const [isHistoryExpanded, setIsHistoryExpanded] = useState(false)

  // Sort by sequence order (oldest first)
  const sortedQueries = [...queries].sort(
    (a, b) => (a.sequenceOrder ?? 0) - (b.sequenceOrder ?? 0)
  )

  // History queries = all except active (or all except most recent if no active)
  const activeId = activeQueryId ?? sortedQueries[sortedQueries.length - 1]?.id
  const historyQueries = sortedQueries.filter(q => q.id !== activeId)

  // Don't render if no history
  if (historyQueries.length === 0) {
    return null
  }

  // In collapsed mode, show only last 2 history items
  const maxCollapsedHistory = 2
  const visibleHistory = isHistoryExpanded
    ? historyQueries
    : historyQueries.slice(-maxCollapsedHistory)
  const hasMoreHistory = historyQueries.length > maxCollapsedHistory

  return (
    <div className="flex flex-col gap-1 animate-in fade-in slide-in-from-bottom-2 duration-200">
      {/* "See all" toggle at top when collapsed with hidden items */}
      {!isHistoryExpanded && hasMoreHistory && (
        <button
          onClick={() => setIsHistoryExpanded(true)}
          className="
            flex items-center gap-1.5 px-3 py-1.5
            rounded-lg bg-slate-100/80 backdrop-blur-sm
            border border-slate-200/50
            hover:bg-slate-200/80 hover:border-slate-300
            transition-all duration-200
            text-slate-500 hover:text-slate-700
            text-xs font-medium
          "
        >
          <ChevronUp size={12} />
          See all ({historyQueries.length})
        </button>
      )}

      {/* Collapse toggle when expanded */}
      {isHistoryExpanded && hasMoreHistory && (
        <button
          onClick={() => setIsHistoryExpanded(false)}
          className="
            flex items-center gap-1.5 px-3 py-1.5
            rounded-lg bg-slate-100/80 backdrop-blur-sm
            border border-slate-200/50
            hover:bg-slate-200/80 hover:border-slate-300
            transition-all duration-200
            text-slate-500 hover:text-slate-700
            text-xs font-medium
          "
        >
          <ChevronDown size={12} />
          Collapse
        </button>
      )}

      {/* History items - older queries */}
      {visibleHistory.map((query) => (
        <button
          key={query.id}
          onClick={() => onSelectQuery(query.id)}
          className="
            flex items-center gap-2 px-3 py-1.5
            rounded-lg bg-white/80 backdrop-blur-sm
            border border-slate-200/50
            hover:bg-slate-50 hover:border-cyan-300 hover:shadow-sm
            transition-all duration-200
            text-left
          "
        >
          <div className="w-4 h-4 rounded-full bg-slate-100 flex items-center justify-center">
            <span className="text-[10px] font-medium text-slate-500">
              {query.pages?.length ?? 0}
            </span>
          </div>
          <span className="text-xs font-medium text-slate-600 truncate max-w-[200px]">
            {getDisplayTitle(query)}
          </span>
        </button>
      ))}
    </div>
  )
}
