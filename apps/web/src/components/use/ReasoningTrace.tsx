import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Search, FileText, GitBranch, CheckCircle2, Brain, File, Folder, List } from 'lucide-react';
import type { AgentTraceStep } from '../../types';

// Map tool names to icons
const TOOL_ICONS: Record<string, React.ReactNode> = {
  search_pointers: <Search size={12} />,
  get_pointer: <FileText size={12} />,
  get_page_context: <File size={12} />,
  get_discipline_overview: <Folder size={12} />,
  list_project_pages: <List size={12} />,
  get_references_to_page: <GitBranch size={12} />,
};

interface ReasoningTraceProps {
  trace: AgentTraceStep[];
  onNavigateToPage?: (pageId: string) => void;
  onOpenPointer?: (pointerId: string) => void;
}

export const ReasoningTrace: React.FC<ReasoningTraceProps> = ({
  trace,
  onNavigateToPage,
  onOpenPointer,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  if (trace.length === 0) {
    return null;
  }

  // Get icon for a step
  const getStepIcon = (step: AgentTraceStep) => {
    if (step.type === 'reasoning') {
      return <Brain size={12} />;
    }
    if (step.type === 'tool_call' && step.tool) {
      return TOOL_ICONS[step.tool] || <FileText size={12} />;
    }
    if (step.type === 'tool_result') {
      return <CheckCircle2 size={12} />;
    }
    return <FileText size={12} />;
  };

  // Get display text for a step
  const getStepText = (step: AgentTraceStep) => {
    if (step.type === 'reasoning') {
      // Truncate long reasoning
      const text = step.content || '';
      return text.length > 100 ? text.slice(0, 100) + '...' : text;
    }
    if (step.type === 'tool_call') {
      const toolName = step.tool?.replace(/_/g, ' ') || 'tool';
      return `Called ${toolName}`;
    }
    if (step.type === 'tool_result') {
      return `Result received`;
    }
    return 'Unknown step';
  };

  // Check if a step is clickable (has page or pointer reference)
  const getClickHandler = (step: AgentTraceStep): (() => void) | undefined => {
    if (step.type === 'tool_result' && step.result) {
      // Check for page navigation
      if (step.result.pageId && onNavigateToPage) {
        return () => onNavigateToPage(step.result!.pageId as string);
      }
      // Check for pointer opening
      if (step.result.pointerId && onOpenPointer) {
        return () => onOpenPointer(step.result!.pointerId as string);
      }
    }
    return undefined;
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-slate-50 transition-colors"
      >
        <div className="flex-shrink-0">
          {isExpanded ? (
            <ChevronDown size={14} className="text-slate-400" />
          ) : (
            <ChevronRight size={14} className="text-slate-400" />
          )}
        </div>
        <span className="text-xs font-medium text-slate-500">
          See reasoning trace ({trace.length} steps)
        </span>
      </button>

      {/* Trace steps */}
      {isExpanded && (
        <div className="border-t border-slate-100 px-3 py-2 space-y-1 max-h-64 overflow-y-auto animate-fade-in">
          {trace.map((step, index) => {
            const clickHandler = getClickHandler(step);
            const isClickable = !!clickHandler;

            return (
              <div
                key={index}
                onClick={clickHandler}
                className={`flex items-start gap-2 py-1.5 px-2 rounded ${
                  isClickable
                    ? 'cursor-pointer hover:bg-cyan-50 transition-colors'
                    : ''
                }`}
              >
                {/* Step number */}
                <span className="text-[10px] text-slate-400 font-mono w-4 flex-shrink-0 pt-0.5">
                  {(index + 1).toString().padStart(2, '0')}
                </span>

                {/* Icon */}
                <div className={`flex-shrink-0 mt-0.5 ${
                  step.type === 'reasoning'
                    ? 'text-purple-400'
                    : step.type === 'tool_call'
                    ? 'text-cyan-500'
                    : 'text-green-500'
                }`}>
                  {getStepIcon(step)}
                </div>

                {/* Text */}
                <span className={`text-xs flex-1 ${
                  isClickable ? 'text-cyan-600' : 'text-slate-600'
                }`}>
                  {getStepText(step)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
