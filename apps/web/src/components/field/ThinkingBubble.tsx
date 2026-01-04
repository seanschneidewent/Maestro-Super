import { useState, useEffect, useRef } from 'react'
import { MessageCircle } from 'lucide-react'
import ReactMarkdown from 'react-markdown'

interface ThinkingBubbleProps {
  thinkingText: string
  finalAnswer: string
  isStreaming: boolean
  hasQueryStack?: boolean
}

export function ThinkingBubble({ thinkingText, finalAnswer, isStreaming, hasQueryStack = false }: ThinkingBubbleProps) {
  const [isCollapsed, setIsCollapsed] = useState(false)
  const hasScheduledCollapse = useRef(false)

  // During streaming: show thinking text
  // After streaming: show full final answer
  const displayText = isStreaming ? thinkingText : finalAnswer

  // Auto-collapse 6 seconds after streaming completes
  useEffect(() => {
    if (!isStreaming && finalAnswer && !hasScheduledCollapse.current) {
      hasScheduledCollapse.current = true
      const timer = setTimeout(() => {
        setIsCollapsed(true)
      }, 6000)
      return () => clearTimeout(timer)
    }
  }, [isStreaming, finalAnswer])

  // Reset collapse state when a new query starts (streaming begins)
  useEffect(() => {
    if (isStreaming) {
      setIsCollapsed(false)
      hasScheduledCollapse.current = false
    }
  }, [isStreaming])

  // Don't render if nothing to show
  if (!displayText) {
    return null
  }

  // Position class - higher when QueryStack is visible
  const positionClass = hasQueryStack ? 'bottom-36' : 'bottom-20'

  // Collapsed state - show small pill with robot chat icon
  if (isCollapsed && !isStreaming) {
    return (
      <button
        onClick={() => setIsCollapsed(false)}
        className={`
          absolute ${positionClass} left-4 z-30
          flex items-center gap-2 px-3 py-2
          rounded-full bg-gradient-to-r from-cyan-50 to-slate-50
          border border-cyan-200/50 shadow-sm
          hover:shadow-md hover:border-cyan-300
          transition-all duration-200 group
          animate-in fade-in slide-in-from-bottom-2 duration-200
        `}
        title="Click to expand response"
      >
        <div className="w-6 h-6 rounded-full bg-gradient-to-br from-cyan-500 to-blue-500 flex items-center justify-center shadow-glow-cyan-sm">
          <MessageCircle size={12} className="text-white" />
        </div>
        <span className="text-xs text-slate-500 group-hover:text-cyan-600 transition-colors">
          View response
        </span>
      </button>
    )
  }

  return (
    <div
      onClick={!isStreaming ? () => setIsCollapsed(true) : undefined}
      className={`
        absolute ${positionClass} left-4 z-30
        max-w-lg w-auto
        bg-white/95 backdrop-blur-md border border-slate-200/50
        rounded-2xl rounded-bl-sm px-4 py-3 shadow-lg
        animate-in fade-in slide-in-from-bottom-2 duration-200
        ${!isStreaming ? 'cursor-pointer hover:bg-slate-50/95 transition-colors' : ''}
      `}
      title={!isStreaming ? 'Click to collapse' : undefined}
    >
      {isStreaming ? (
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-600">{displayText}</span>
          <div className="flex items-center gap-0.5">
            <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
            <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
            <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
        </div>
      ) : (
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
            {displayText}
          </ReactMarkdown>
        </div>
      )}
    </div>
  )
}
