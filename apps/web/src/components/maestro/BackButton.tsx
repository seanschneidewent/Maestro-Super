import { ArrowLeft } from 'lucide-react'

interface BackButtonProps {
  visible: boolean
  onBack: () => void
}

export function BackButton({ visible, onBack }: BackButtonProps) {
  if (!visible) return null

  return (
    <button
      onClick={onBack}
      className="
        fixed top-4 left-20 z-30
        bg-slate-800/80 backdrop-blur-sm border border-slate-700/50 rounded-lg
        flex items-center gap-2 px-3 py-2
        text-sm text-slate-300
        hover:bg-white/10 hover:text-white transition-colors
      "
    >
      <ArrowLeft size={18} />
      <span>Back</span>
    </button>
  )
}
