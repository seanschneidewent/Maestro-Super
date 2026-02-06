import React, { useState, useEffect, useRef } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Hammer,
  CheckCircle2,
  Loader2,
  Sparkles,
  FileText,
  BookOpen,
  Database,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import type { AgentTraceStep } from '../../types';
import type { PageAgentState } from '../../hooks/useQueryManager';
import { ConstellationAnimation } from './ConstellationAnimation';

interface ThinkingSectionProps {
  isStreaming: boolean;
  thinkingText?: string;
  autoCollapse?: boolean;
  trace?: AgentTraceStep[];
  initialElapsedTime?: number;
  onNavigateToPage?: (pageId: string) => void;
  onOpenPointer?: (pointerId: string) => void;
  pageAgentStates?: PageAgentState[];
}

interface ProcessedAction {
  type: 'action' | 'thinking';
  text: string;
  isComplete: boolean;
  expandedContent?: string;
}

type ThinkingPanel = 'workspace_assembly' | 'learning' | 'knowledge_update';
type PanelTone = 'workspace' | 'learning' | 'knowledge';

// Generate human-readable text for a completed tool action.
function formatCompletedAction(toolCall: AgentTraceStep, toolResult: AgentTraceStep): string {
  const tool = toolCall.tool;
  const input = toolCall.input || {};
  const result = toolResult.result || {};

  switch (tool) {
    case 'search_pointers': {
      const query = input.query as string;
      const pointers = result.pointers as unknown[];
      const count = Array.isArray(pointers) ? pointers.length : 0;
      if (query) {
        return `Searched for "${query}" -> Found ${count} area${count !== 1 ? 's' : ''}`;
      }
      return `Found ${count} relevant area${count !== 1 ? 's' : ''}`;
    }
    case 'search_pages': {
      const query = input.query as string;
      const pages = result.pages as unknown[];
      const count = Array.isArray(pages) ? pages.length : 0;
      if (query) {
        return `Searched pages for "${query}" -> Found ${count}`;
      }
      return `Found ${count} page${count !== 1 ? 's' : ''}`;
    }
    case 'get_pointer': {
      const title = result.title as string;
      if (title) {
        const truncated = title.length > 40 ? `${title.slice(0, 40)}...` : title;
        return `Read "${truncated}"`;
      }
      return 'Read pointer details';
    }
    case 'get_page_context': {
      const sheetNumber = result.sheet_number as string;
      const pageName = result.page_name as string;
      if (sheetNumber) {
        return `Reviewed page ${sheetNumber}`;
      }
      if (pageName) {
        return `Reviewed "${pageName}"`;
      }
      return 'Reviewed page context';
    }
    case 'get_discipline_overview': {
      const name = result.name as string;
      if (name) {
        return `Reviewed ${name} overview`;
      }
      return 'Reviewed discipline';
    }
    case 'get_references_to_page': {
      const references = result.references as unknown[];
      const count = Array.isArray(references) ? references.length : 0;
      return `Found ${count} page${count !== 1 ? 's' : ''} referencing this`;
    }
    case 'select_pages':
    case 'add_pages': {
      const pages = result.pages as unknown[];
      const count = Array.isArray(pages) ? pages.length : 0;
      return `Selected ${count} page${count !== 1 ? 's' : ''} to show`;
    }
    case 'select_pointers':
    case 'highlight_pointers': {
      const pointers = result.pointers as unknown[];
      const count = Array.isArray(pointers) ? pointers.length : 0;
      return `Highlighted ${count} area${count !== 1 ? 's' : ''}`;
    }
    default:
      return tool?.replace(/_/g, ' ') || 'Completed action';
  }
}

function processTraceForDisplay(
  trace: AgentTraceStep[],
  isStreaming: boolean,
  panel: ThinkingPanel,
): ProcessedAction[] {
  if (panel !== 'workspace_assembly') {
    return trace
      .filter((step) => step.type === 'thinking' && step.panel === panel)
      .map((step) => {
        const content = step.content?.trim() || '';
        const truncated = content.length > 120 ? `${content.slice(0, 120)}...` : content;
        return {
          type: 'thinking',
          text: truncated,
          isComplete: !isStreaming,
          expandedContent: content.length > 120 ? content : undefined,
        } as ProcessedAction;
      })
      .filter((step) => step.text.length > 0);
  }

  const actions: ProcessedAction[] = [];

  let lastToolResultIndex = -1;
  for (let j = trace.length - 1; j >= 0; j--) {
    if (trace[j].type === 'tool_result') {
      lastToolResultIndex = j;
      break;
    }
  }

  let i = 0;
  while (i < trace.length) {
    const step = trace[i];

    if (step.type === 'thinking') {
      const panelValue = step.panel || 'workspace_assembly';
      if (panelValue !== 'workspace_assembly') {
        i++;
        continue;
      }

      const content = step.content?.trim() || '';
      if (content.length > 0) {
        const truncated = content.length > 80 ? `${content.slice(0, 80)}...` : content;
        actions.push({
          type: 'thinking',
          text: truncated,
          isComplete: !isStreaming,
          expandedContent: content.length > 80 ? content : undefined,
        });
      }
      i++;
    } else if (step.type === 'reasoning') {
      const content = step.content?.trim() || '';
      if (content.length > 20 && i > lastToolResultIndex) {
        const truncated = content.length > 60 ? `${content.slice(0, 60)}...` : content;
        actions.push({
          type: 'thinking',
          text: truncated,
          isComplete: true,
          expandedContent: content.length > 60 ? content : undefined,
        });
      }
      i++;
    } else if (step.type === 'tool_call') {
      let matchingResultIndex = -1;
      for (let j = i + 1; j < trace.length; j++) {
        if (trace[j].type === 'tool_result' && trace[j].tool === step.tool) {
          matchingResultIndex = j;
          break;
        }
        if (trace[j].type === 'tool_call') break;
      }

      if (matchingResultIndex !== -1) {
        actions.push({
          type: 'action',
          text: formatCompletedAction(step, trace[matchingResultIndex]),
          isComplete: true,
        });
        i = matchingResultIndex + 1;
      } else {
        if (isStreaming) {
          actions.push({
            type: 'action',
            text: step.tool?.replace(/_/g, ' ') || 'Working...',
            isComplete: false,
          });
        }
        i++;
      }
    } else if (step.type === 'code_execution') {
      const content = step.content?.trim() || '';
      if (content.length > 0) {
        const truncated = content.length > 80 ? `${content.slice(0, 80)}...` : content;
        actions.push({
          type: 'action',
          text: `Inspecting: ${truncated}`,
          isComplete: true,
          expandedContent: content.length > 80 ? content : undefined,
        });
      }
      i++;
    } else {
      i++;
    }
  }

  return actions;
}

const toneMap: Record<PanelTone, {
  heading: string;
  accent: string;
  hover: string;
  bodyBg: string;
  border: string;
}> = {
  workspace: {
    heading: 'text-sky-800',
    accent: 'text-sky-500',
    hover: 'hover:bg-sky-100/40',
    bodyBg: 'bg-sky-50',
    border: 'border-sky-200',
  },
  learning: {
    heading: 'text-amber-800',
    accent: 'text-amber-500',
    hover: 'hover:bg-amber-100/40',
    bodyBg: 'bg-amber-50',
    border: 'border-amber-200',
  },
  knowledge: {
    heading: 'text-violet-800',
    accent: 'text-violet-500',
    hover: 'hover:bg-violet-100/40',
    bodyBg: 'bg-violet-50',
    border: 'border-violet-200',
  },
};

const ActionItem: React.FC<{
  action: ProcessedAction;
  tone: PanelTone;
}> = ({ action, tone }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const theme = toneMap[tone];

  return (
    <div className="group">
      <button
        onClick={() => action.expandedContent && setIsExpanded(!isExpanded)}
        className={`w-full flex items-center gap-2 py-1.5 px-2 rounded-lg transition-colors ${action.expandedContent ? `${theme.hover} cursor-pointer` : 'cursor-default'}`}
      >
        <div className="flex-shrink-0 w-4">
          {action.type === 'thinking' ? (
            <Sparkles size={14} className={`${theme.accent} ${action.isComplete ? '' : 'animate-pulse'}`} />
          ) : action.isComplete ? (
            <CheckCircle2 size={14} className="text-green-500" />
          ) : (
            <Loader2 size={14} className={`${theme.accent} animate-spin`} />
          )}
        </div>

        <span className={`text-xs flex-1 text-left ${action.type === 'thinking' ? theme.heading : 'text-slate-600'}`}>
          {action.type === 'thinking' ? (
            <ReactMarkdown
              components={{
                p: ({ children }) => <>{children}</>,
                strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                em: ({ children }) => <em>{children}</em>,
              }}
              allowedElements={['p', 'strong', 'em']}
              unwrapDisallowed
            >
              {action.text}
            </ReactMarkdown>
          ) : (
            action.text
          )}
        </span>

        {action.expandedContent && (
          <div className="flex-shrink-0">
            {isExpanded ? (
              <ChevronDown size={12} className="text-slate-400" />
            ) : (
              <ChevronRight size={12} className="text-slate-400" />
            )}
          </div>
        )}
      </button>

      {isExpanded && action.expandedContent && (
        <div className={`ml-6 mr-2 mt-1 mb-2 p-2 rounded-lg border ${theme.bodyBg} ${theme.border}`}>
          <div className="text-xs text-slate-700 leading-relaxed">
            <ReactMarkdown
              components={{
                p: ({ children }) => <p className="my-1 first:mt-0 last:mb-0">{children}</p>,
                strong: ({ children }) => <strong className="font-semibold text-slate-900">{children}</strong>,
                em: ({ children }) => <em>{children}</em>,
                ul: ({ children }) => <ul className="my-1 ml-4 list-disc">{children}</ul>,
                ol: ({ children }) => <ol className="my-1 ml-4 list-decimal">{children}</ol>,
                li: ({ children }) => <li className="my-0.5">{children}</li>,
              }}
            >
              {action.expandedContent}
            </ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  );
};

interface PanelCardProps {
  title: string;
  tone: PanelTone;
  icon: React.ReactNode;
  preview: string;
  showTimer?: string;
  isStreaming: boolean;
  actions: ProcessedAction[];
  expanded: boolean;
  onToggle: () => void;
  scrollRef?: React.RefObject<HTMLDivElement>;
  emptyLabel: string;
  footer?: React.ReactNode;
}

const PanelCard: React.FC<PanelCardProps> = ({
  title,
  tone,
  icon,
  preview,
  showTimer,
  isStreaming,
  actions,
  expanded,
  onToggle,
  scrollRef,
  emptyLabel,
  footer,
}) => {
  const theme = toneMap[tone];

  return (
    <div className={`rounded-xl border overflow-hidden ${theme.border} ${theme.bodyBg}/60`}>
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-white/40 transition-colors"
      >
        {expanded ? (
          <ChevronDown size={14} className="text-slate-400 flex-shrink-0" />
        ) : (
          <ChevronRight size={14} className="text-slate-400 flex-shrink-0" />
        )}
        <div className="flex-shrink-0">{icon}</div>
        <div className="flex-1 min-w-0">
          <div className={`text-xs font-semibold uppercase tracking-wide ${theme.heading}`}>{title}</div>
          <div className={`text-xs truncate ${theme.heading}`}>
            {preview}
          </div>
        </div>
        {showTimer && (
          <span className="text-xs font-mono text-slate-400 flex-shrink-0">{showTimer}</span>
        )}
        {isStreaming && !showTimer && <Loader2 size={12} className={`${theme.accent} animate-spin flex-shrink-0`} />}
      </button>

      {expanded && (
        <div ref={scrollRef} className="px-2 pb-2 max-h-60 overflow-y-auto overflow-x-hidden animate-fade-in">
          {actions.length === 0 ? (
            <div className="px-2 py-3 text-xs text-slate-500">{emptyLabel}</div>
          ) : (
            actions.map((action, index) => (
              <ActionItem key={`${title}-${index}`} action={action} tone={tone} />
            ))
          )}
          {footer}
        </div>
      )}
    </div>
  );
};

export const ThinkingSection: React.FC<ThinkingSectionProps> = ({
  isStreaming,
  thinkingText = '',
  autoCollapse = true,
  trace = [],
  initialElapsedTime,
  pageAgentStates = [],
}) => {
  const [expandedPanels, setExpandedPanels] = useState({
    workspace: true,
    learning: true,
    knowledge: true,
  });
  const [startTime, setStartTime] = useState<number | null>(null);
  const [elapsedTime, setElapsedTime] = useState<number>(initialElapsedTime || 0);
  const wasStreamingRef = useRef(isStreaming);
  const timerIntervalRef = useRef<number | null>(null);
  const workspaceScrollRef = useRef<HTMLDivElement>(null);
  const learningScrollRef = useRef<HTMLDivElement>(null);
  const knowledgeScrollRef = useRef<HTMLDivElement>(null);

  const workspaceActions = processTraceForDisplay(trace, isStreaming, 'workspace_assembly');
  const learningActions = processTraceForDisplay(trace, isStreaming, 'learning');
  const knowledgeActions = processTraceForDisplay(trace, isStreaming, 'knowledge_update');

  const formatTime = (ms: number) => `${(ms / 1000).toFixed(1)}s`;

  useEffect(() => {
    if (isStreaming && !startTime) {
      setStartTime(Date.now());
    }

    if (isStreaming) {
      timerIntervalRef.current = window.setInterval(() => {
        if (startTime) {
          setElapsedTime(Date.now() - startTime);
        }
      }, 100);

      return () => {
        if (timerIntervalRef.current) {
          clearInterval(timerIntervalRef.current);
        }
      };
    }

    if (!isStreaming && startTime) {
      setElapsedTime(Date.now() - startTime);
    }
  }, [isStreaming, startTime]);

  useEffect(() => {
    if (trace.length === 0 && !isStreaming) {
      setStartTime(null);
      setElapsedTime(0);
    }
  }, [trace.length, isStreaming]);

  useEffect(() => {
    const wasStreaming = wasStreamingRef.current;
    wasStreamingRef.current = isStreaming;

    if (autoCollapse && wasStreaming && !isStreaming && expandedPanels.workspace) {
      const timer = setTimeout(() => {
        setExpandedPanels((prev) => ({ ...prev, workspace: false }));
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [isStreaming, autoCollapse, expandedPanels.workspace]);

  useEffect(() => {
    if (expandedPanels.workspace && workspaceScrollRef.current) {
      workspaceScrollRef.current.scrollTop = workspaceScrollRef.current.scrollHeight;
    }
    if (expandedPanels.learning && learningScrollRef.current) {
      learningScrollRef.current.scrollTop = learningScrollRef.current.scrollHeight;
    }
    if (expandedPanels.knowledge && knowledgeScrollRef.current) {
      knowledgeScrollRef.current.scrollTop = knowledgeScrollRef.current.scrollHeight;
    }
  }, [
    expandedPanels.workspace,
    expandedPanels.learning,
    expandedPanels.knowledge,
    workspaceActions.length,
    learningActions.length,
    knowledgeActions.length,
  ]);

  if (trace.length === 0 && !isStreaming) {
    return null;
  }

  const learningPreview = learningActions.length > 0
    ? learningActions[learningActions.length - 1].text
    : 'No learning updates yet';
  const knowledgePreview = knowledgeActions.length > 0
    ? knowledgeActions[knowledgeActions.length - 1].text
    : 'No knowledge writes yet';
  const workspacePreview = thinkingText || (isStreaming ? 'Assembling workspace...' : 'Workspace assembly complete');

  return (
    <div className="w-full max-w-3xl mx-auto rounded-xl border border-slate-200 bg-slate-50/50 overflow-hidden transition-all duration-200 min-w-0 relative">
      <ConstellationAnimation isActive={isStreaming} />

      <div className="relative z-10 p-2 space-y-2">
        <PanelCard
          title="Workspace Assembly"
          tone="workspace"
          icon={isStreaming ? (
            <Sparkles size={12} className="text-sky-500 animate-pulse" />
          ) : (
            <Hammer size={12} className="text-sky-500" />
          )}
          preview={workspacePreview}
          showTimer={elapsedTime > 0 ? formatTime(elapsedTime) : undefined}
          isStreaming={isStreaming}
          actions={workspaceActions}
          expanded={expandedPanels.workspace}
          onToggle={() => setExpandedPanels((prev) => ({ ...prev, workspace: !prev.workspace }))}
          scrollRef={workspaceScrollRef}
          emptyLabel={isStreaming ? 'Starting workspace assembly...' : 'No workspace actions'}
          footer={pageAgentStates.length > 0 ? (
            <div className="mt-2 pt-2 border-t border-sky-200 space-y-1">
              <div className="px-2 text-xs font-medium text-sky-700 mb-1">Page Agents</div>
              {pageAgentStates.map((page) => (
                <div key={page.pageId} className="flex items-center gap-2 px-2 py-1 rounded-lg">
                  <div className="flex-shrink-0 w-4">
                    {page.state === 'done' ? (
                      <CheckCircle2 size={14} className="text-green-500" />
                    ) : page.state === 'processing' ? (
                      <Loader2 size={14} className="text-sky-500 animate-spin" />
                    ) : (
                      <FileText size={14} className="text-slate-400" />
                    )}
                  </div>
                  <span className={`text-xs truncate ${
                    page.state === 'done'
                      ? 'text-slate-700'
                      : page.state === 'processing'
                        ? 'text-sky-700 font-medium'
                        : 'text-slate-400'
                  }`}
                  >
                    {page.pageName}
                  </span>
                  <span className={`text-[10px] ml-auto flex-shrink-0 ${
                    page.state === 'done'
                      ? 'text-green-500'
                      : page.state === 'processing'
                        ? 'text-sky-500'
                        : 'text-slate-300'
                  }`}
                  >
                    {page.state}
                  </span>
                </div>
              ))}
            </div>
          ) : undefined}
        />

        <PanelCard
          title="Learning"
          tone="learning"
          icon={<BookOpen size={12} className="text-amber-500" />}
          preview={learningPreview}
          isStreaming={isStreaming}
          actions={learningActions}
          expanded={expandedPanels.learning}
          onToggle={() => setExpandedPanels((prev) => ({ ...prev, learning: !prev.learning }))}
          scrollRef={learningScrollRef}
          emptyLabel={isStreaming ? 'Learning agent is listening...' : 'No learning events'}
        />

        <PanelCard
          title="Knowledge Update"
          tone="knowledge"
          icon={<Database size={12} className="text-violet-500" />}
          preview={knowledgePreview}
          isStreaming={isStreaming}
          actions={knowledgeActions}
          expanded={expandedPanels.knowledge}
          onToggle={() => setExpandedPanels((prev) => ({ ...prev, knowledge: !prev.knowledge }))}
          scrollRef={knowledgeScrollRef}
          emptyLabel={isStreaming ? 'No knowledge write yet...' : 'No knowledge updates'}
        />
      </div>
    </div>
  );
};
