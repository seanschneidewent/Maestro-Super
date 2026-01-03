import ReactMarkdown from 'react-markdown'

interface ThinkingBubbleProps {
  isThinking: boolean
  thinkingText: string
  finalAnswer: string
}

export function ThinkingBubble({ isThinking, thinkingText, finalAnswer }: ThinkingBubbleProps) {
  // Determine what to display
  const displayText = isThinking
    ? (thinkingText || 'Let me look at that for you...')
    : finalAnswer

  // Don't render if nothing to show
  if (!displayText) {
    return null
  }

  return (
    <div
      className="
        absolute bottom-20 left-4 z-30
        max-w-md w-auto
        bg-white/95 backdrop-blur-md border border-slate-200/50
        rounded-2xl rounded-bl-sm px-4 py-3 shadow-lg
        animate-in fade-in slide-in-from-bottom-2 duration-200
      "
    >
      {isThinking ? (
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-600">{displayText}</span>
          <div className="flex items-center gap-0.5">
            <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
            <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
            <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
        </div>
      ) : (
        <div className="text-sm text-slate-700 leading-relaxed">
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
