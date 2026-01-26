import { memo, useRef, useEffect } from 'react';
import { NodeProps, Handle, Position } from 'reactflow';
import { Star } from 'lucide-react';
import type { DisciplineNodeData } from '../types';

function DisciplineNodeComponent({ data }: NodeProps<DisciplineNodeData>) {
  const { displayName, processed, pageCount, pointerCount, onExpand, onClick, isExpanded, animationKey } = data;
  const divRef = useRef<HTMLDivElement>(null);
  const prevAnimationKey = useRef(animationKey);

  useEffect(() => {
    // Only restart animation when animationKey changes, not on initial mount
    if (divRef.current && prevAnimationKey.current !== animationKey) {
      // Delay animation restart to let ReactFlow update positions first
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (divRef.current) {
            divRef.current.style.animation = 'none';
            divRef.current.offsetHeight; // Trigger reflow
            divRef.current.style.animation = '';
          }
        });
      });
    }
    prevAnimationKey.current = animationKey;
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

      {/* Node body - click to expand/collapse */}
      <div
        className={`relative flex items-center gap-2 px-4 py-2.5 rounded-lg
                   bg-slate-800 border-2 min-w-[140px] max-w-[180px]
                   shadow-lg transition-all duration-200 cursor-pointer pointer-events-auto
                   ${processed
                     ? 'border-amber-400/50 hover:border-amber-400 shadow-amber-900/20'
                     : 'border-slate-600 hover:border-slate-500 shadow-slate-900/30'
                   }`}
        onClick={onExpand}
      >
        {processed && (
          <Star size={14} className="text-amber-400 fill-amber-400 shrink-0" />
        )}

        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-200 truncate">{displayName}</p>
          <p className="text-xs text-slate-500">
            {pageCount} pages
          </p>
        </div>
      </div>
    </div>
  );
}

export const DisciplineNode = memo(DisciplineNodeComponent);
