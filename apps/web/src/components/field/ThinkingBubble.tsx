import { useState, useEffect } from 'react'

interface ThinkingBubbleProps {
  isThinking: boolean
  thinkingText: string
  summary: string
}

export function ThinkingBubble({ isThinking, thinkingText, summary }: ThinkingBubbleProps) {
  const [isHidden, setIsHidden] = useState(false)
  const [isFadingOut, setIsFadingOut] = useState(false)

  useEffect(() => {
    if (isThinking) {
      // Reset hidden state when thinking starts
      setIsHidden(false)
      setIsFadingOut(false)
    } else if (summary) {
      // Start fade-out timer when thinking stops and we have a summary
      setIsFadingOut(false)
      const fadeTimer = setTimeout(() => {
        setIsFadingOut(true)
      }, 2000)

      const hideTimer = setTimeout(() => {
        setIsHidden(true)
      }, 2500) // 2s delay + 500ms fade

      return () => {
        clearTimeout(fadeTimer)
        clearTimeout(hideTimer)
      }
    }
  }, [isThinking, summary])

  // Determine what to show
  const showThinking = isThinking && thinkingText
  const showSummary = !isThinking && summary && !isHidden

  if (!showThinking && !showSummary) {
    return null
  }

  const displayText = showThinking ? thinkingText : summary

  return (
    <div
      className={`
        fixed bottom-24 left-4 z-30
        max-w-xs
        bg-slate-800/80 backdrop-blur-sm border border-slate-700/50
        rounded-lg px-4 py-2
        text-sm text-slate-300
        animate-in fade-in duration-200
        transition-opacity duration-500
        ${isFadingOut ? 'opacity-0' : 'opacity-100'}
      `}
    >
      {displayText}
    </div>
  )
}
