import { memo, useRef, useEffect } from 'react';
import { NodeProps, Handle, Position } from 'reactflow';
import { ChevronDown, ChevronRight, Check, Loader2 } from 'lucide-react';
import type { PageNodeData, PageProcessingStatus } from '../types';

function getStatusIcon(
  pointerCount: number,
  processedPass2: boolean,
  processingStatus?: PageProcessingStatus,
  detailCount?: number
): React.ReactNode {
  // Brain Mode: show processing status
  if (processingStatus === 'completed') {
    return (
      <div className="w-4 h-4 bg-green-500 rounded-full flex items-center justify-center animate-checkmark-pulse">
        <Check size={10} className="text-white" strokeWidth={3} />
      </div>
    );
  }
  if (processingStatus === 'processing') {
    return <Loader2 size={14} className="text-cyan-400 animate-spin" />;
  }
  if (processingStatus === 'failed') {
    return <span className="text-red-400 text-sm">!</span>;
  }

  // Legacy pointer-based status (processingStatus is undefined, 'pending', or already handled above)
  if (pointerCount === 0 && (!detailCount || detailCount === 0)) return <span className="text-slate-500">○</span>;
  if (!processedPass2) return <span className="text-slate-400">◐</span>;
  return <span className="text-slate-300">●</span>;
}

function PageNodeComponent({ data }: NodeProps<PageNodeData>) {
  const {
    pageName,
    pointerCount,
    processedPass2,
    onExpand,
    onClick,
    isExpanded,
    isActive,
    animationKey,
    processingStatus,
    detailCount,
  } = data;
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

  const statusIcon = getStatusIcon(pointerCount, processedPass2, processingStatus, detailCount);
  const hasChildren = pointerCount > 0 || (detailCount && detailCount > 0);
  const childCount = pointerCount + (detailCount ?? 0);

  // Show processing glow when actively processing
  const isProcessing = processingStatus === 'processing';

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
      {/* Active glow */}
      {isActive && (
        <div className="absolute inset-0 rounded-lg bg-cyan-400/20 blur-md pointer-events-none" />
      )}
      {/* Processing glow */}
      {isProcessing && (
        <div className="absolute inset-0 rounded-lg bg-cyan-400/15 blur-md pointer-events-none animate-pulse" />
      )}

      {/* Node body */}
      <div
        className={`relative flex items-center gap-2 px-3 py-2 rounded-lg
                   bg-slate-800 border shadow-md
                   transition-all duration-200 cursor-pointer pointer-events-auto
                   ${isActive
                     ? 'border-cyan-400 shadow-cyan-900/30'
                     : isProcessing
                       ? 'border-cyan-500/50 shadow-cyan-900/20'
                       : 'border-slate-600/50 hover:border-slate-500 shadow-slate-900/20'
                   }`}
        onClick={onClick}
      >
        <span className="shrink-0 flex items-center justify-center w-4 h-4">
          {statusIcon}
        </span>

        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-slate-300 truncate">{pageName}</p>
        </div>

        {childCount > 0 && (
          <span className="text-[10px] text-slate-500 bg-slate-700/50 px-1.5 py-0.5 rounded shrink-0">
            {childCount}
          </span>
        )}

        {hasChildren && (
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
