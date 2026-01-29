import { FieldPointer } from '../../types'

interface PointerOverlayProps {
  pointer: FieldPointer
  isActive: boolean
  onTap: () => void
}

export function PointerOverlay({ pointer, isActive, onTap }: PointerOverlayProps) {
  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    onTap()
  }

  return (
    <div
      onClick={handleClick}
      style={{
        position: 'absolute',
        left: `${pointer.region.bboxX * 100}%`,
        top: `${pointer.region.bboxY * 100}%`,
        width: `${pointer.region.bboxWidth * 100}%`,
        height: `${pointer.region.bboxHeight * 100}%`,
      }}
      className={`
        border-2 rounded cursor-pointer transition-all
        ${
          isActive
            ? 'border-blue-500 bg-blue-500/25 ring-2 ring-blue-400/50'
            : 'border-blue-500/50 bg-blue-500/10 hover:bg-blue-500/20'
        }
      `}
    >
      <div
        className="
          absolute -top-6 left-0
          bg-slate-800/80 backdrop-blur-sm
          text-xs text-slate-200 px-2 py-0.5 rounded
          truncate max-w-[150px]
        "
      >
        {pointer.label}
      </div>
    </div>
  )
}
