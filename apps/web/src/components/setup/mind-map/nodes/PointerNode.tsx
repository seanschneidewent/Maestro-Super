import { memo, useRef, useEffect } from 'react';
import { NodeProps, Handle, Position } from 'reactflow';
import { Crosshair, X } from 'lucide-react';
import type { PointerNodeData } from '../types';

function PointerNodeComponent({ data }: NodeProps<PointerNodeData>) {
  const { title, onClick, onDelete, animationKey } = data;
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
        className="!bg-violet-400 !w-2 !h-2 !border-0"
      />
      {/* Glow effect on hover */}
      <div className="absolute inset-0 rounded-md bg-violet-400/0 blur-md group-hover:bg-violet-400/20 transition-all pointer-events-none" />

      {/* Node body */}
      <div
        className="relative flex items-center gap-1.5 px-2.5 py-1.5 rounded-md
                   bg-slate-700 border border-violet-400/30
                   hover:border-violet-400/60 hover:bg-slate-700/80
                   shadow-sm shadow-violet-900/10
                   transition-all duration-200 cursor-pointer pointer-events-auto max-w-[140px]"
        onClick={onClick}
      >
        <Crosshair size={10} className="text-violet-400 shrink-0" />

        <p className="text-[11px] text-slate-300 truncate flex-1">{title}</p>

        {/* Delete button - appears on hover */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-red-500/20
                     text-slate-500 hover:text-red-400 transition-all shrink-0"
          title="Delete pointer"
        >
          <X size={12} />
        </button>
      </div>
    </div>
  );
}

export const PointerNode = memo(PointerNodeComponent);
