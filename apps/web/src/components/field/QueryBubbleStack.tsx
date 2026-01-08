import { useState, useEffect } from 'react'
import { ChevronDown, ChevronUp, MessageCircle } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import type { QueryWithPages } from '../../types'

interface QueryBubbleStackProps {
  queries: QueryWithPages[]
  activeQueryId: string | null
  onSelectQuery: (queryId: string) => void
  // Streaming state for the currently processing query
  isStreaming: boolean
  thinkingText: string
  streamingDisplayTitle: string | null
  streamingFinalAnswer: string
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
 * QueryBubbleStack - Unified vertical list of all query bubbles.
 *
 * - All queries stay in fixed positions (sorted by sequenceOrder)
 * - Active query gets visual highlight but doesn't move
 * - Click once to select (becomes active), click again to expand
 * - Streaming query appears at the bottom as a new bubble
 */
export function QueryBubbleStack({
  queries,
  activeQueryId,
  onSelectQuery,
  isStreaming,
  thinkingText,
  streamingDisplayTitle,
  streamingFinalAnswer,
}: QueryBubbleStackProps) {
  const [expandedQueryId, setExpandedQueryId] = useState<string | null>(null)
  const [isHistoryExpanded, setIsHistoryExpanded] = useState(false)

  // Auto-collapse expanded bubble when a new query starts streaming
  useEffect(() => {
    if (isStreaming) {
      setExpandedQueryId(null)
    }
  }, [isStreaming])

  // Sort by sequence order (oldest first, newest at bottom)
  const sortedQueries = [...queries].sort(
    (a, b) => (a.sequenceOrder ?? 0) - (b.sequenceOrder ?? 0)
  )

  // When collapsed, show: previous to active, active, most recent
  // This ensures the active query is always visible with context
  const getCollapsedQueries = () => {
    if (sortedQueries.length <= 3) return sortedQueries

    const activeIndex = sortedQueries.findIndex(q => q.id === activeQueryId)

    // If no active or active is most recent, just show last 3
    if (activeIndex === -1 || activeIndex === sortedQueries.length - 1) {
      return sortedQueries.slice(-3)
    }

    const result: typeof sortedQueries = []

    // 1. Previous to active (if exists)
    if (activeIndex > 0) {
      result.push(sortedQueries[activeIndex - 1])
    }

    // 2. Active query
    result.push(sortedQueries[activeIndex])

    // 3. Most recent (if different from active)
    const mostRecent = sortedQueries[sortedQueries.length - 1]
    if (mostRecent.id !== activeQueryId) {
      result.push(mostRecent)
    }

    return result
  }

  const collapsedQueries = getCollapsedQueries()
  const visibleQueries = isHistoryExpanded ? sortedQueries : collapsedQueries

  // Show expand/collapse toggle when there are more queries than the collapsed view shows
  const hasMoreHistory = sortedQueries.length > collapsedQueries.length

  // Handle click on a query bubble
  const handleBubbleClick = (queryId: string) => {
    console.log('[QueryBubbleStack] Click:', queryId, 'activeQueryId:', activeQueryId, 'expandedQueryId:', expandedQueryId)
    if (activeQueryId === queryId) {
      // Already active - toggle expand
      const newExpanded = expandedQueryId === queryId ? null : queryId
      console.log('[QueryBubbleStack] Setting expandedQueryId to:', newExpanded)
      setExpandedQueryId(newExpanded)
    } else {
      // Not active - select it (collapse any expanded)
      setExpandedQueryId(null)
      onSelectQuery(queryId)
    }
  }

  // Don't render if no queries and not streaming
  if (sortedQueries.length === 0 && !isStreaming) {
    return null
  }

  return (
    <div className="flex flex-col items-start gap-1.5 animate-in fade-in slide-in-from-bottom-2 duration-200">
      {/* "See all" toggle at top when collapsed with hidden items */}
      {!isHistoryExpanded && hasMoreHistory && (
        <button
          onClick={() => setIsHistoryExpanded(true)}
          className="
            w-fit flex items-center gap-1.5 px-3 py-1.5
            rounded-lg bg-slate-100/80 backdrop-blur-sm
            border border-slate-200/50
            hover:bg-slate-200/80 hover:border-slate-300
            transition-all duration-200
            text-slate-500 hover:text-slate-700
            text-xs font-medium
          "
        >
          <ChevronUp size={12} />
          See all ({sortedQueries.length})
        </button>
      )}

      {/* Collapse toggle when expanded */}
      {isHistoryExpanded && hasMoreHistory && (
        <button
          onClick={() => setIsHistoryExpanded(false)}
          className="
            w-fit flex items-center gap-1.5 px-3 py-1.5
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

      {/* Query bubbles - all in fixed positions */}
      {visibleQueries.map((query) => {
        const isActive = query.id === activeQueryId
        const isExpanded = query.id === expandedQueryId
        // For active query, prefer streamingFinalAnswer (set by restore) over stored responseText
        const responseText = isActive ? (streamingFinalAnswer || query.responseText) : query.responseText
        if (isActive) {
          console.log('[QueryBubbleStack] Active query render:', query.id, 'isExpanded:', isExpanded, 'streamingFinalAnswer:', streamingFinalAnswer?.slice(0, 50), 'query.responseText:', query.responseText?.slice(0, 50), 'responseText:', responseText?.slice(0, 50))
        }

        // Non-active: small compact style
        if (!isActive) {
          return (
            <button
              key={query.id}
              onClick={() => handleBubbleClick(query.id)}
              className="
                w-fit flex items-center gap-2 px-3 py-1.5
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
          )
        }

        // Active: large expandable style
        return (
          <div
            key={query.id}
            className={`
              bg-white/95 backdrop-blur-md border border-cyan-400 ring-2 ring-cyan-200/50
              rounded-2xl rounded-bl-sm shadow-lg
              transition-all duration-200
              ${isExpanded ? 'max-w-lg' : 'max-w-xs'}
            `}
          >
            {/* Header - clickable to expand/collapse */}
            <button
              onClick={() => handleBubbleClick(query.id)}
              className="
                w-full flex items-center gap-2 px-3 py-2
                hover:bg-slate-50/50 rounded-2xl
                transition-colors duration-200
              "
            >
              <div className="w-6 h-6 rounded-full bg-gradient-to-br from-cyan-500 to-blue-500 flex items-center justify-center shadow-sm flex-shrink-0">
                <MessageCircle size={12} className="text-white" />
              </div>
              <span className="flex-1 text-sm font-medium text-slate-700 text-left truncate">
                {getDisplayTitle(query)}
              </span>
              <ChevronDown
                size={16}
                className={`
                  text-slate-400 transition-transform duration-200 flex-shrink-0
                  ${isExpanded ? 'rotate-180' : ''}
                `}
              />
            </button>

            {/* Expanded response content */}
            {isExpanded && responseText && (
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
                    {responseText}
                  </ReactMarkdown>
                </div>
              </div>
            )}
          </div>
        )
      })}

      {/* Streaming bubble - appears at bottom when processing */}
      {isStreaming && (
        <div
          className="
            max-w-lg w-auto
            bg-white/95 backdrop-blur-md border border-cyan-400 ring-2 ring-cyan-200/50
            rounded-2xl rounded-bl-sm px-4 py-3 shadow-lg
            animate-in fade-in slide-in-from-bottom-2 duration-200
          "
        >
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-full bg-gradient-to-br from-cyan-500 to-blue-500 flex items-center justify-center shadow-sm flex-shrink-0">
              <MessageCircle size={12} className="text-white" />
            </div>
            <span className="text-sm text-slate-600">{thinkingText || 'Thinking...'}</span>
            <div className="flex items-center gap-0.5 flex-shrink-0">
              <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
