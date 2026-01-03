import { X } from 'lucide-react'
import { FieldPointer } from '../../types'

interface PointerPopoverProps {
  pointer: FieldPointer
  onClose: () => void
}

export function PointerPopover({ pointer, onClose }: PointerPopoverProps) {
  return (
    <div
      className="
        fixed bottom-24 left-1/2 -translate-x-1/2 z-40
        max-w-md w-full mx-4
        bg-slate-800/90 backdrop-blur-md border border-slate-700/50
        rounded-xl p-4 shadow-2xl
        animate-in fade-in slide-in-from-bottom-4 duration-200
      "
    >
      <button
        onClick={onClose}
        className="absolute top-3 right-3 text-slate-400 hover:text-white transition-colors"
      >
        <X size={18} />
      </button>

      <p className="text-lg font-medium text-white mb-3 pr-6">
        {pointer.answer}
      </p>

      {pointer.evidence.type === 'quote' ? (
        <p className="text-slate-300 italic">
          "{pointer.evidence.text}"
        </p>
      ) : (
        <p className="text-slate-400 text-sm">
          {pointer.evidence.text}
        </p>
      )}
    </div>
  )
}
