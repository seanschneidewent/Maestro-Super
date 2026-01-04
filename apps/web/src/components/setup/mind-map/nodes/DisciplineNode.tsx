import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { ChevronDown, ChevronRight, Star } from 'lucide-react';
import type { DisciplineNodeData } from '../types';

function DisciplineNodeComponent({ data }: NodeProps<DisciplineNodeData>) {
  const { displayName, processed, pageCount, pointerCount, onExpand, onClick, isExpanded } = data;

  return (
    <div className="relative group">
      {/* Glow effect */}
      {processed && (
        <div className="absolute inset-0 rounded-lg bg-amber-400/10 blur-lg group-hover:bg-amber-400/20 transition-all" />
      )}

      {/* Input handle */}
      <Handle
        type="target"
        position={Position.Top}
        className="!w-2.5 !h-2.5 !bg-slate-600 !border-2 !border-slate-800"
      />

      {/* Node body */}
      <div
        className={`relative flex items-center gap-2 px-4 py-2.5 rounded-lg
                   bg-slate-800 border-2
                   shadow-lg transition-all duration-200 cursor-pointer min-w-[160px]
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

      {/* Output handle */}
      <Handle
        type="source"
        position={Position.Bottom}
        className={`!w-2.5 !h-2.5 !border-2 !border-slate-800 ${processed ? '!bg-amber-400' : '!bg-slate-600'}`}
      />
    </div>
  );
}

export const DisciplineNode = memo(DisciplineNodeComponent);
