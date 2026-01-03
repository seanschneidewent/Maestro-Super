import React, { useState, useEffect, useRef } from 'react';
import { ChevronDown, ChevronRight, Brain, Search, FileText, File, Folder, List, GitBranch, CheckCircle2 } from 'lucide-react';
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

interface ThinkingSectionProps {
  /** Array of reasoning strings streamed from the agent */
  reasoning: string[];
  /** Whether the agent is still streaming */
  isStreaming: boolean;
  /** Auto-collapse when streaming completes */
  autoCollapse?: boolean;
  /** Trace steps from completed agent response */
  trace?: AgentTraceStep[];
  /** Callback when navigating to a page */
  onNavigateToPage?: (pageId: string) => void;
  /** Callback when opening a pointer */
  onOpenPointer?: (pointerId: string) => void;
}

export const ThinkingSection: React.FC<ThinkingSectionProps> = ({
  reasoning,
  isStreaming,
  autoCollapse = true,
  trace = [],
  onNavigateToPage,
  onOpenPointer,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const wasStreamingRef = useRef(isStreaming);

  // Auto-collapse only when streaming transitions from true to false
  useEffect(() => {
    const wasStreaming = wasStreamingRef.current;
    wasStreamingRef.current = isStreaming;

    // Only auto-collapse if streaming just completed (was streaming, now not)
    if (autoCollapse && wasStreaming && !isStreaming && isExpanded) {
      const timer = setTimeout(() => {
        setIsExpanded(false);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [isStreaming, autoCollapse, isExpanded]);

  // Don't render if no reasoning and no trace
  if (reasoning.length === 0 && trace.length === 0 && !isStreaming) {
    return null;
  }

  const combinedText = reasoning.join('');

  // Get icon for a trace step
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

  // Get display text for a trace step
  const getStepText = (step: AgentTraceStep) => {
    if (step.type === 'reasoning') {
      return step.content || '';
    }
    if (step.type === 'tool_call') {
      const toolName = step.tool?.replace(/_/g, ' ') || 'tool';
      return `Called ${toolName}`;
    }
    if (step.type === 'tool_result') {
      return 'Result received';
    }
    return 'Unknown step';
  };

  // Check if a step is clickable (has page or pointer reference)
  const getClickHandler = (step: AgentTraceStep): (() => void) | undefined => {
    if (step.type === 'tool_result' && step.result) {
      if (step.result.pageId && onNavigateToPage) {
        return () => onNavigateToPage(step.result!.pageId as string);
      }
      if (step.result.pointerId && onOpenPointer) {
        return () => onOpenPointer(step.result!.pointerId as string);
      }
    }
    return undefined;
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/50 overflow-hidden transition-all duration-200">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-slate-100/50 transition-colors"
      >
        <div className={`flex-shrink-0 transition-transform duration-200 ${isExpanded ? 'rotate-0' : ''}`}>
          {isExpanded ? (
            <ChevronDown size={14} className="text-slate-400" />
          ) : (
            <ChevronRight size={14} className="text-slate-400" />
          )}
        </div>

        <Brain size={14} className={`flex-shrink-0 ${isStreaming ? 'text-cyan-500' : 'text-slate-400'}`} />

        <span className="text-xs font-medium text-slate-600 flex-1 text-left">
          {isStreaming ? 'Thinking' : 'Thought process'}
        </span>

        {/* Animated dots while streaming */}
        {isStreaming && (
          <div className="flex items-center gap-0.5">
            <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
            <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
            <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
        )}
      </button>

      {/* Content */}
      {isExpanded && (
        <div className="px-3 pb-3 animate-fade-in space-y-2">
          {/* Reasoning text */}
          {(combinedText || isStreaming) && (
            <div className="text-xs text-slate-500 leading-relaxed whitespace-pre-wrap font-mono bg-white rounded-lg p-3 border border-slate-100 max-h-48 overflow-y-auto">
              {combinedText || (isStreaming ? 'Starting to think...' : '')}
              {isStreaming && (
                <span className="inline-block w-1.5 h-4 bg-cyan-400 ml-0.5 animate-pulse" />
              )}
            </div>
          )}

          {/* Trace steps */}
          {trace.length > 0 && (
            <div className="border-t border-slate-100 pt-2 space-y-1 max-h-64 overflow-y-auto">
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
      )}
    </div>
  );
};
