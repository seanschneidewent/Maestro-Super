import { useState } from 'react'
import { ChevronUp, MessageSquare } from 'lucide-react'
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
  const [isExpanded, setIsExpanded] = useState(false)

  // Don't render if no queries
  if (queries.length === 0) {
    return null
  }

  // Sort by sequence order (most recent last for bottom-up display)
  const sortedQueries = [...queries].sort(
    (a, b) => (a.sequenceOrder ?? 0) - (b.sequenceOrder ?? 0)
  )

  // In collapsed mode, only show the most recent query (last in sorted list)
  const visibleQueries = isExpanded ? sortedQueries : [sortedQueries[sortedQueries.length - 1]]
  const hasMore = queries.length > 3
  const hiddenCount = queries.length - 1

  // Single query - show simple pill
  if (queries.length === 1) {
    const query = queries[0]
    const isActive = query.id === activeQueryId

    return (
      <div className="absolute bottom-20 left-4 z-30 animate-in fade-in slide-in-from-bottom-2 duration-200">
        <button
          onClick={() => onSelectQuery(query.id)}
          className={`
            flex items-center gap-2 px-3 py-2
            rounded-full shadow-sm
            transition-all duration-200
            ${isActive
              ? 'bg-gradient-to-r from-cyan-500 to-blue-500 text-white shadow-glow-cyan-sm'
              : 'bg-white/95 backdrop-blur-md border border-slate-200/50 hover:border-cyan-300 hover:shadow-md'
            }
          `}
        >
          <MessageSquare size={14} className={isActive ? 'text-white' : 'text-cyan-500'} />
          <span className={`text-sm font-medium ${isActive ? 'text-white' : 'text-slate-700'}`}>
            {getDisplayTitle(query)}
          </span>
        </button>
      </div>
    )
  }

  return (
    <div className="absolute bottom-20 left-4 z-30 animate-in fade-in slide-in-from-bottom-2 duration-200">
      <div className="flex flex-col-reverse gap-1.5">
        {/* Query items - displayed in reverse order so newest is at bottom visually */}
        {visibleQueries.map((query, index) => {
          const isActive = query.id === activeQueryId
          const isNewest = index === visibleQueries.length - 1

          return (
            <button
              key={query.id}
              onClick={() => onSelectQuery(query.id)}
              className={`
                flex items-center gap-2 px-3 py-2
                rounded-xl shadow-sm
                transition-all duration-200
                ${isActive
                  ? 'bg-gradient-to-r from-cyan-500 to-blue-500 text-white shadow-glow-cyan-sm'
                  : 'bg-white/95 backdrop-blur-md border border-slate-200/50 hover:border-cyan-300 hover:shadow-md'
                }
                ${!isNewest && !isExpanded ? 'scale-95 opacity-80' : ''}
              `}
            >
              <div className={`
                w-5 h-5 rounded-full flex items-center justify-center text-xs font-medium
                ${isActive ? 'bg-white/20' : 'bg-slate-100'}
              `}>
                <span className={isActive ? 'text-white' : 'text-slate-500'}>
                  {query.sequenceOrder ?? index + 1}
                </span>
              </div>
              <span className={`text-sm font-medium ${isActive ? 'text-white' : 'text-slate-700'}`}>
                {getDisplayTitle(query)}
              </span>
            </button>
          )
        })}

        {/* "See all" / collapse toggle - shown at top when collapsed with >1 query */}
        {!isExpanded && hiddenCount > 0 && (
          <button
            onClick={() => setIsExpanded(true)}
            className="
              flex items-center gap-1.5 px-3 py-1.5
              rounded-xl bg-slate-100/90 backdrop-blur-md
              border border-slate-200/50
              hover:bg-slate-200/90 hover:border-slate-300
              transition-all duration-200
              text-slate-500 hover:text-slate-700
            "
          >
            <ChevronUp size={14} />
            <span className="text-xs font-medium">
              {hiddenCount} more {hiddenCount === 1 ? 'query' : 'queries'}
            </span>
          </button>
        )}

        {/* Collapse button when expanded */}
        {isExpanded && hasMore && (
          <button
            onClick={() => setIsExpanded(false)}
            className="
              flex items-center gap-1.5 px-3 py-1.5
              rounded-xl bg-slate-100/90 backdrop-blur-md
              border border-slate-200/50
              hover:bg-slate-200/90 hover:border-slate-300
              transition-all duration-200
              text-slate-500 hover:text-slate-700
            "
          >
            <ChevronUp size={14} className="rotate-180" />
            <span className="text-xs font-medium">Show less</span>
          </button>
        )}
      </div>
    </div>
  )
}
