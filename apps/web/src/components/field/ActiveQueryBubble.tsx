import { useState, useEffect } from 'react'
import { ChevronDown, MessageCircle } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import type { QueryWithPages } from '../../types'

interface ActiveQueryBubbleProps {
  // Streaming state
  isStreaming: boolean
  thinkingText: string
  displayTitle: string | null
  finalAnswer: string
  // Completed query (when not streaming and query is in session)
  activeQuery: QueryWithPages | null
}

function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength - 3) + '...'
}

/**
 * ActiveQueryBubble - Shows the current/active query.
 *
 * During streaming: Shows thinking text with animated dots
 * After streaming: Shows query title, expandable to show full response
 */
export function ActiveQueryBubble({
  isStreaming,
  thinkingText,
  displayTitle,
  finalAnswer,
  activeQuery,
}: ActiveQueryBubbleProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  // Auto-collapse when a new query starts streaming
  useEffect(() => {
    if (isStreaming) {
      setIsExpanded(false)
    }
  }, [isStreaming])

  // === STREAMING STATE ===
  if (isStreaming) {
    return (
      <div
        className="
          max-w-lg w-auto
          bg-white/95 backdrop-blur-md border border-slate-200/50
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
    )
  }

  // === COMPLETED STATE ===
  // Use activeQuery if available, otherwise use streaming results
  const title = activeQuery?.displayTitle || displayTitle || (activeQuery ? truncateText(activeQuery.queryText, 40) : 'Response')
  const responseText = activeQuery?.responseText || finalAnswer

  // Don't render if no response to show
  if (!responseText && !activeQuery) {
    return null
  }

  return (
    <div
      className={`
        bg-white/95 backdrop-blur-md border border-slate-200/50
        rounded-2xl rounded-bl-sm shadow-lg
        transition-all duration-200
        animate-in fade-in slide-in-from-bottom-2 duration-200
        ${isExpanded ? 'max-w-lg' : 'max-w-xs'}
      `}
    >
      {/* Header - always visible, clickable to expand/collapse */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
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
          {title}
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
}
