import { Clock } from 'lucide-react'

interface SessionControlsProps {
  onToggleHistory: () => void
  isHistoryOpen: boolean
}

export function SessionControls({ onToggleHistory, isHistoryOpen }: SessionControlsProps) {
  return (
    <div
      className="
        fixed top-4 right-4 z-30
        bg-slate-800/80 backdrop-blur-sm border border-slate-700/50 rounded-xl
        flex items-center gap-1 p-1
      "
    >
      <button
        onClick={onToggleHistory}
        className={`
          p-2 rounded-lg transition-colors
          ${isHistoryOpen ? 'bg-white/10' : 'hover:bg-white/10'}
        `}
      >
        <Clock size={20} className="text-slate-300" />
      </button>
    </div>
  )
}
