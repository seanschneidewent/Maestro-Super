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
        w-11 h-11 rounded-full
        flex items-center justify-center
        bg-white/90 backdrop-blur-md
        border border-slate-200/50
        shadow-lg
        transition-all duration-150
        ${disabled
          ? 'opacity-50 cursor-not-allowed'
          : 'hover:bg-slate-50 hover:border-slate-300 hover:shadow-xl active:scale-95'
        }
      `}
      title="New conversation"
    >
      <Plus size={20} className="text-slate-600" />
    </button>
  )
}
