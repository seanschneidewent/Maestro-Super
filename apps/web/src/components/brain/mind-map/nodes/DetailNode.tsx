import { memo, useRef, useEffect } from 'react';
import { NodeProps, Handle, Position } from 'reactflow';
import { Ruler, Package, FileText } from 'lucide-react';
import type { DetailNodeData } from '../types';

// Icon selection based on detail content
function getDetailIcon(detail: { materials: string[]; dimensions: string[] }) {
  if (detail.dimensions.length > 0) {
    return <Ruler size={10} className="text-cyan-400 shrink-0" />;
  }
  if (detail.materials.length > 0) {
    return <Package size={10} className="text-orange-400 shrink-0" />;
  }
  return <FileText size={10} className="text-slate-400 shrink-0" />;
}

function DetailNodeComponent({ data }: NodeProps<DetailNodeData>) {
  const { title, number, materials, dimensions, onClick, animationKey, staggerIndex = 0 } = data;
  const divRef = useRef<HTMLDivElement>(null);
  const prevAnimationKey = useRef(animationKey);

  // Staggered animation delay (50ms per detail)
  const animationDelay = `${staggerIndex * 50}ms`;

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

  // Format display title
  const displayTitle = number ? `${title} (${number})` : title;

  return (
    <div
      ref={divRef}
      className="relative group animate-detail-zap"
      style={{ animationDelay }}
    >
      {/* Target handle (left side) */}
      <Handle
        type="target"
        position={Position.Left}
        className="!bg-cyan-400 !w-2 !h-2 !border-0"
      />
      {/* Glow effect on hover */}
      <div className="absolute inset-0 rounded-md bg-cyan-400/0 blur-md group-hover:bg-cyan-400/15 transition-all pointer-events-none" />

      {/* Node body */}
      <div
        className="relative flex items-center gap-1.5 px-2.5 py-1.5 rounded-md
                   bg-slate-800/80 border border-cyan-500/20
                   hover:border-cyan-400/40 hover:bg-slate-700/80
                   shadow-sm shadow-cyan-900/10
                   transition-all duration-200 cursor-pointer pointer-events-auto max-w-[160px]"
        onClick={onClick}
      >
        {getDetailIcon({ materials, dimensions })}

        <p className="text-[11px] text-slate-300 truncate flex-1" title={displayTitle}>
          {displayTitle}
        </p>

        {/* Badge showing count of materials/dimensions */}
        {(materials.length > 0 || dimensions.length > 0) && (
          <span className="text-[9px] text-slate-500 bg-slate-700/50 px-1 py-0.5 rounded shrink-0">
            {materials.length + dimensions.length}
          </span>
        )}
      </div>
    </div>
  );
}

export const DetailNode = memo(DetailNodeComponent);
