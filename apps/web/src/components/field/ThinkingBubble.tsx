interface ThinkingBubbleProps {
  thinkingText: string
  isStreaming: boolean
}

export function ThinkingBubble({ thinkingText, isStreaming }: ThinkingBubbleProps) {
  // Don't render if no thinking text
  if (!thinkingText) {
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
      <div className="flex items-center gap-2">
        <span className="text-sm text-slate-600">{thinkingText}</span>
        {isStreaming && (
          <div className="flex items-center gap-0.5">
            <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
            <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
            <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
        )}
      </div>
    </div>
  )
}
