import ReactMarkdown from 'react-markdown'

interface ThinkingBubbleProps {
  thinkingText: string
  finalAnswer: string
  isStreaming: boolean
}

export function ThinkingBubble({ thinkingText, finalAnswer, isStreaming }: ThinkingBubbleProps) {
  // During streaming: show thinking text
  // After streaming: show full final answer
  const displayText = isStreaming ? thinkingText : finalAnswer

  // Don't render if nothing to show
  if (!displayText) {
    return null
  }

  return (
    <div
      className="
        absolute bottom-20 left-4 z-30
        max-w-lg w-auto
        bg-white/95 backdrop-blur-md border border-slate-200/50
        rounded-2xl rounded-bl-sm px-4 py-3 shadow-lg
        animate-in fade-in slide-in-from-bottom-2 duration-200
      "
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
