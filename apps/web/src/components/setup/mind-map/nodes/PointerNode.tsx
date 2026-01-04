import { memo } from 'react';
import { NodeProps, Handle, Position } from 'reactflow';
import { Crosshair } from 'lucide-react';
import type { PointerNodeData } from '../types';

function PointerNodeComponent({ data }: NodeProps<PointerNodeData>) {
  const { title, onClick } = data;

  return (
    <div className="relative group">
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
                   transition-all duration-200 cursor-pointer max-w-[140px]"
        onClick={onClick}
      >
        <Crosshair size={10} className="text-violet-400 shrink-0" />

        <p className="text-[11px] text-slate-300 truncate">{title}</p>
      </div>
    </div>
  );
}

export const PointerNode = memo(PointerNodeComponent);
