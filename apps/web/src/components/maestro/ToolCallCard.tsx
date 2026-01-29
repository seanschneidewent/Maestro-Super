import React from 'react';
import { Search, FileText, File, Folder, List, GitBranch, Loader2, CheckCircle2 } from 'lucide-react';
import type { ToolCallState } from '../../types';

// Tool display configuration
const TOOL_CONFIG: Record<string, {
  icon: React.ReactNode;
  pendingText: (input: Record<string, unknown>) => string;
  completeText: (input: Record<string, unknown>, result?: Record<string, unknown>) => string;
}> = {
  search_pointers: {
    icon: <Search size={14} />,
    pendingText: (input) => `Searching for "${input.query || '...'}"`,
    completeText: (input, result) => {
      const count = Array.isArray(result?.pointers) ? result.pointers.length : 0;
      return `Found ${count} result${count !== 1 ? 's' : ''}`;
    },
  },
  get_pointer: {
    icon: <FileText size={14} />,
    pendingText: () => 'Reading pointer...',
    completeText: (_input, result) => `Read: ${(result?.title as string) || 'pointer'}`,
  },
  get_page_context: {
    icon: <File size={14} />,
    pendingText: (input) => `Loading page ${input.page_name || '...'}`,
    completeText: (_input, result) => `Viewed: ${(result?.pageName as string) || 'page'}`,
  },
  get_discipline_overview: {
    icon: <Folder size={14} />,
    pendingText: () => 'Reviewing discipline...',
    completeText: (_input, result) => `Reviewed: ${(result?.name as string) || 'discipline'}`,
  },
  list_project_pages: {
    icon: <List size={14} />,
    pendingText: () => 'Listing pages...',
    completeText: (_input, result) => {
      const count = Array.isArray(result?.pages) ? result.pages.length : 0;
      return `Listed ${count} page${count !== 1 ? 's' : ''}`;
    },
  },
  get_references_to_page: {
    icon: <GitBranch size={14} />,
    pendingText: () => 'Finding references...',
    completeText: (_input, result) => {
      const count = Array.isArray(result?.references) ? result.references.length : 0;
      return `Found ${count} ref${count !== 1 ? 's' : ''}`;
    },
  },
};

// Default config for unknown tools
const DEFAULT_CONFIG = {
  icon: <FileText size={14} />,
  pendingText: (input: Record<string, unknown>) => `Running ${input.tool || 'tool'}...`,
  completeText: () => 'Complete',
};

interface ToolCallCardProps {
  toolCall: ToolCallState;
}

export const ToolCallCard: React.FC<ToolCallCardProps> = ({ toolCall }) => {
  const config = TOOL_CONFIG[toolCall.tool] || DEFAULT_CONFIG;
  const isPending = toolCall.status === 'pending';

  const displayText = isPending
    ? config.pendingText(toolCall.input)
    : config.completeText(toolCall.input, toolCall.result);

  return (
    <div className={`flex items-center gap-2.5 py-2 px-3 rounded-lg border-l-2 transition-all duration-200 ${
      isPending
        ? 'bg-cyan-50/50 border-cyan-400'
        : 'bg-slate-50 border-slate-300'
    }`}>
      {/* Icon */}
      <div className={`flex-shrink-0 ${isPending ? 'text-cyan-500' : 'text-slate-400'}`}>
        {config.icon}
      </div>

      {/* Text */}
      <span className={`text-xs flex-1 truncate ${
        isPending ? 'text-cyan-700' : 'text-slate-600'
      }`}>
        {displayText}
      </span>

      {/* Status indicator */}
      <div className="flex-shrink-0">
        {isPending ? (
          <Loader2 size={14} className="text-cyan-500 animate-spin" />
        ) : (
          <CheckCircle2 size={14} className="text-green-500" />
        )}
      </div>
    </div>
  );
};
