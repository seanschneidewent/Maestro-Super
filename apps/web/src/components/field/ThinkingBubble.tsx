interface ThinkingBubbleProps {
  thinkingText: string
  finalAnswer: string
  isStreaming: boolean
}

/**
 * ThinkingBubble - Shows streaming status during agent response.
 * Only displayed during streaming. QueryStack handles completed responses.
 */
export function ThinkingBubble({ thinkingText, isStreaming }: ThinkingBubbleProps) {
  // Only show during streaming with thinking text
  if (!isStreaming || !thinkingText) {
    return null
  }

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
        <span className="text-sm text-slate-600">{thinkingText}</span>
        <div className="flex items-center gap-0.5">
          <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
          <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
          <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
      </div>
    </div>
  )
}
