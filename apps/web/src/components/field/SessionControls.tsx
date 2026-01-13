import { Clock } from 'lucide-react'

interface SessionControlsProps {
  onToggleHistory: () => void
  isHistoryOpen: boolean
  showSkipTutorial?: boolean
  onSkipTutorial?: () => void
}

export function SessionControls({
  onToggleHistory,
  isHistoryOpen,
  showSkipTutorial = false,
  onSkipTutorial,
}: SessionControlsProps) {
  return (
    <div
      className="
        fixed top-5 right-4 z-30
        bg-white/90 backdrop-blur-md border border-slate-200/50 rounded-xl shadow-lg
        flex items-center gap-1 p-1
      "
    >
      {showSkipTutorial && onSkipTutorial && (
        <button
          onClick={onSkipTutorial}
          className="px-3 py-1.5 text-sm text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
        >
          Skip
        </button>
      )}
      <button
        data-tutorial="history-btn"
        onClick={onToggleHistory}
        className={`
          p-2 rounded-lg transition-colors
          ${isHistoryOpen ? 'bg-cyan-100 text-cyan-600' : 'hover:bg-slate-100 text-slate-500'}
        `}
        title="Query history"
      >
        <Clock size={20} />
      </button>
    </div>
  )
}
