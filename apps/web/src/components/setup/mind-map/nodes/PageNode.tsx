import { memo } from 'react';
import { NodeProps, Handle, Position } from 'reactflow';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { PageNodeData } from '../types';

function getStatusIcon(pointerCount: number, processedPass2: boolean): string {
  if (pointerCount === 0) return '○';
  if (!processedPass2) return '◐';
  return '●';
}

function PageNodeComponent({ data }: NodeProps<PageNodeData>) {
  const {
    pageName,
    pointerCount,
    processedPass2,
    onExpand,
    onClick,
    isExpanded,
    isActive
  } = data;

  const statusIcon = getStatusIcon(pointerCount, processedPass2);
  const hasPointers = pointerCount > 0;

  return (
    <div className="relative group">
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
      {/* Active glow */}
      {isActive && (
        <div className="absolute inset-0 rounded-lg bg-cyan-400/20 blur-md pointer-events-none" />
      )}

      {/* Node body */}
      <div
        className={`relative flex items-center gap-2 px-3 py-2 rounded-lg
                   bg-slate-800 border shadow-md
                   transition-all duration-200 cursor-pointer pointer-events-auto
                   ${isActive
                     ? 'border-cyan-400 shadow-cyan-900/30'
                     : 'border-slate-600/50 hover:border-slate-500 shadow-slate-900/20'
                   }`}
        onClick={onClick}
      >
        <span className={`text-sm shrink-0 ${
          hasPointers ? 'text-slate-300' : 'text-slate-500'
        }`}>
          {statusIcon}
        </span>

        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-slate-300 truncate">{pageName}</p>
        </div>

        {pointerCount > 0 && (
          <span className="text-[10px] text-slate-500 bg-slate-700/50 px-1.5 py-0.5 rounded shrink-0">
            {pointerCount}
          </span>
        )}

        {hasPointers && (
          <button
            className="p-0.5 rounded hover:bg-white/10 text-slate-500 hover:text-white transition-colors shrink-0"
            onClick={(e) => {
              e.stopPropagation();
              onExpand();
            }}
          >
            {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>
        )}
      </div>
    </div>
  );
}

export const PageNode = memo(PageNodeComponent);
