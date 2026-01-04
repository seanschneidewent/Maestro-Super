import { useState } from 'react'
import { ChevronUp, ChevronDown, MessageCircle } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
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

export function QueryStack({ queries, activeQueryId, onSelectQuery }: QueryStackProps) {
  const [isHistoryExpanded, setIsHistoryExpanded] = useState(false)
  const [isResponseExpanded, setIsResponseExpanded] = useState(false)

  // Don't render if no queries
  if (queries.length === 0) {
    return null
  }

  // Sort by sequence order (oldest first)
  const sortedQueries = [...queries].sort(
    (a, b) => (a.sequenceOrder ?? 0) - (b.sequenceOrder ?? 0)
  )

  // Find active query, default to most recent if none selected
  const activeQuery = activeQueryId
    ? sortedQueries.find(q => q.id === activeQueryId) ?? sortedQueries[sortedQueries.length - 1]
    : sortedQueries[sortedQueries.length - 1]

  // History queries = all except active
  const historyQueries = sortedQueries.filter(q => q.id !== activeQuery.id)

  // In collapsed mode, show only last 2 history items
  const maxCollapsedHistory = 2
  const visibleHistory = isHistoryExpanded
    ? historyQueries
    : historyQueries.slice(-maxCollapsedHistory)
  const hasMoreHistory = historyQueries.length > maxCollapsedHistory

  return (
    <div className="absolute bottom-20 left-4 z-30 flex flex-col gap-2 animate-in fade-in slide-in-from-bottom-2 duration-200">
      {/* === UPPER SECTION: Query History === */}
      {historyQueries.length > 0 && (
        <div className="flex flex-col gap-1">
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
              onClick={() => {
                onSelectQuery(query.id)
                setIsResponseExpanded(false) // Collapse response when switching
              }}
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
                  {query.sequenceOrder ?? '?'}
                </span>
              </div>
              <span className="text-xs font-medium text-slate-600 truncate max-w-[200px]">
                {getDisplayTitle(query)}
              </span>
            </button>
          ))}
        </div>
      )}

      {/* === LOWER SECTION: Active Query Bubble === */}
      {/* This is always visible and shows the currently selected query */}
      <div
        className={`
          bg-white/95 backdrop-blur-md border border-slate-200/50
          rounded-2xl rounded-bl-sm shadow-lg
          transition-all duration-200
          ${isResponseExpanded ? 'max-w-lg' : 'max-w-xs'}
        `}
      >
        {/* Header - always visible, clickable to expand/collapse */}
        <button
          onClick={() => setIsResponseExpanded(!isResponseExpanded)}
          className="
            w-full flex items-center gap-2 px-3 py-2
            hover:bg-slate-50/50 rounded-2xl
            transition-colors duration-200
          "
        >
          <div className="w-6 h-6 rounded-full bg-gradient-to-br from-cyan-500 to-blue-500 flex items-center justify-center shadow-sm">
            <MessageCircle size={12} className="text-white" />
          </div>
          <span className="flex-1 text-sm font-medium text-slate-700 text-left truncate">
            {getDisplayTitle(activeQuery)}
          </span>
          <ChevronDown
            size={16}
            className={`
              text-slate-400 transition-transform duration-200
              ${isResponseExpanded ? 'rotate-180' : ''}
            `}
          />
        </button>

        {/* Expanded response content */}
        {isResponseExpanded && activeQuery.responseText && (
          <div className="px-4 pb-3 pt-1 border-t border-slate-100">
            <div className="text-sm text-slate-700 leading-relaxed max-h-64 overflow-y-auto">
              <ReactMarkdown
                components={{
                  p: ({ children }) => <p className="my-1 first:mt-0 last:mb-0">{children}</p>,
                  ul: ({ children }) => <ul className="my-1 ml-4 list-disc">{children}</ul>,
                  ol: ({ children }) => <ol className="my-1 ml-4 list-decimal">{children}</ol>,
                  li: ({ children }) => <li className="my-0.5">{children}</li>,
                  strong: ({ children }) => <strong className="font-semibold text-slate-800">{children}</strong>,
                  code: ({ children }) => <code className="bg-slate-100 px-1 py-0.5 rounded text-xs font-mono">{children}</code>,
                }}
              >
                {activeQuery.responseText}
              </ReactMarkdown>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
