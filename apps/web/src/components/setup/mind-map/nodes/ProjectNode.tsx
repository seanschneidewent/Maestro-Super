import { memo } from 'react';
import { NodeProps, Handle, Position } from 'reactflow';
import { ChevronDown, ChevronRight, Layers } from 'lucide-react';
import type { ProjectNodeData } from '../types';

function ProjectNodeComponent({ data }: NodeProps<ProjectNodeData>) {
  const { name, disciplineCount, onExpand, isExpanded } = data;

  return (
    <div className="relative group">
      {/* Source handle (right side) */}
      <Handle
        type="source"
        position={Position.Right}
        className="!bg-cyan-400 !w-2 !h-2 !border-0"
      />
      {/* Glow effect */}
      <div className="absolute inset-0 rounded-xl bg-cyan-400/20 blur-xl group-hover:bg-cyan-400/30 transition-all" />

      {/* Node body */}
      <div
        className="relative flex items-center gap-3 px-5 py-3 rounded-xl
                   bg-slate-800 border-2 border-cyan-400/60
                   shadow-lg shadow-cyan-900/30
                   hover:border-cyan-400 hover:shadow-cyan-400/20
                   transition-all duration-200 cursor-pointer"
        onClick={onExpand}
      >
        <div className="p-2 rounded-lg bg-cyan-400/10">
          <Layers size={20} className="text-cyan-400" />
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-100 truncate">{name}</p>
          <p className="text-xs text-slate-400">
            {disciplineCount} discipline{disciplineCount !== 1 ? 's' : ''}
          </p>
        </div>

        <button
          className="p-1 rounded-md hover:bg-white/10 text-slate-400 hover:text-white transition-colors"
          onClick={(e) => {
            e.stopPropagation();
            onExpand();
          }}
        >
          {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </button>
      </div>
    </div>
  );
}

export const ProjectNode = memo(ProjectNodeComponent);
