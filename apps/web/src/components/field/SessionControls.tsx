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
        bg-white/90 backdrop-blur-md border border-slate-200/50 rounded-xl shadow-lg
        flex items-center gap-1 p-1
      "
    >
      <button
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
