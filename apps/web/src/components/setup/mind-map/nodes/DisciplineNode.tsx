import { memo, useRef, useEffect } from 'react';
import { NodeProps, Handle, Position } from 'reactflow';
import { ChevronDown, ChevronRight, Star } from 'lucide-react';
import type { DisciplineNodeData } from '../types';

function DisciplineNodeComponent({ data }: NodeProps<DisciplineNodeData>) {
  const { displayName, processed, pageCount, pointerCount, onExpand, onClick, isExpanded, animationKey } = data;
  const divRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (divRef.current) {
      divRef.current.style.animation = 'none';
      divRef.current.offsetHeight; // Trigger reflow
      divRef.current.style.animation = '';
    }
  }, [animationKey]);

  return (
    <div ref={divRef} className="relative group animate-scale-in">
      {/* Target handle (left side) */}
      <Handle
        type="target"
        position={Position.Left}
        className="!bg-slate-500 !w-2 !h-2 !border-0"
      />
      {/* Source handle (right side) */}
      <Handle
        type="source"
        position={Position.Right}
        className="!bg-slate-500 !w-2 !h-2 !border-0"
      />
      {/* Glow effect */}
      {processed && (
        <div className="absolute inset-0 rounded-lg bg-amber-400/10 blur-lg group-hover:bg-amber-400/20 transition-all pointer-events-none" />
      )}

      {/* Node body */}
      <div
        className={`relative flex items-center gap-2 px-4 py-2.5 rounded-lg
                   bg-slate-800 border-2 min-w-[140px] max-w-[180px]
                   shadow-lg transition-all duration-200 cursor-pointer pointer-events-auto
                   ${processed
                     ? 'border-amber-400/50 hover:border-amber-400 shadow-amber-900/20'
                     : 'border-slate-600 hover:border-slate-500 shadow-slate-900/30'
                   }`}
        onClick={onClick}
      >
        {processed && (
          <Star size={14} className="text-amber-400 fill-amber-400 shrink-0" />
        )}

        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-200 truncate">{displayName}</p>
          <p className="text-xs text-slate-500">
            {pageCount} pg · {pointerCount} ptr
          </p>
        </div>

        <button
          className="p-1 rounded-md hover:bg-white/10 text-slate-400 hover:text-white transition-colors shrink-0"
          onClick={(e) => {
            e.stopPropagation();
            onExpand();
          }}
        >
          {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
      </div>
    </div>
  );
}

export const DisciplineNode = memo(DisciplineNodeComponent);
