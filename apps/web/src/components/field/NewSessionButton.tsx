import { Plus } from 'lucide-react'

interface NewSessionButtonProps {
  onClick: () => void
  disabled?: boolean
}

export function NewSessionButton({ onClick, disabled }: NewSessionButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`
        w-14 h-14 rounded-full
        flex items-center justify-center
        bg-white/90 backdrop-blur-md
        border border-cyan-300/40
        shadow-glow-cyan animate-glow-pulse
        transition-all duration-150
        ${disabled
          ? 'opacity-50 cursor-not-allowed'
          : 'hover:bg-slate-50 hover:border-cyan-400/60 active:scale-95'
        }
      `}
      title="New conversation"
    >
      <Plus size={24} className="text-slate-600" />
    </button>
  )
}
