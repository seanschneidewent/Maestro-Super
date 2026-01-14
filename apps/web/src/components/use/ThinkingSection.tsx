import React, { useState, useEffect, useRef } from 'react';
import { ChevronDown, ChevronRight, Hammer, CheckCircle2, Loader2 } from 'lucide-react';
import type { AgentTraceStep } from '../../types';
import { ConstellationAnimation } from './ConstellationAnimation';

interface ThinkingSectionProps {
  reasoning: string[];
  isStreaming: boolean;
  autoCollapse?: boolean;
  trace?: AgentTraceStep[];
  initialElapsedTime?: number; // For completed responses - time in ms
  onNavigateToPage?: (pageId: string) => void;
  onOpenPointer?: (pointerId: string) => void;
}

// Generate a productivity phrase from a tool result
function generateProductivityPhrase(step: AgentTraceStep): string | null {
  if (step.type !== 'tool_result' || !step.result) return null;

  const result = step.result;
  const tool = step.tool;

  switch (tool) {
    case 'search_pointers': {
      const pointers = result.pointers as unknown[];
      if (Array.isArray(pointers)) {
        return `Found ${pointers.length} relevant area${pointers.length !== 1 ? 's' : ''}`;
      }
      return 'Searching areas...';
    }
    case 'search_pages': {
      const pages = result.pages as unknown[];
      if (Array.isArray(pages)) {
        return `Found ${pages.length} page${pages.length !== 1 ? 's' : ''}`;
      }
      return 'Searching pages...';
    }
    case 'get_pointer': {
      const title = result.title as string;
      if (title) {
        const truncated = title.length > 30 ? title.slice(0, 30) + '...' : title;
        return `Reading "${truncated}"`;
      }
      return 'Reading details...';
    }
    case 'get_page_context': {
      const sheetNumber = result.sheet_number as string;
      if (sheetNumber) {
        return `Understanding ${sheetNumber}`;
      }
      return 'Understanding page...';
    }
    case 'get_discipline_overview': {
      const name = result.name as string;
      if (name) {
        return `Reviewing ${name}`;
      }
      return 'Reviewing discipline...';
    }
    case 'get_references_to_page': {
      const references = result.references as unknown[];
      if (Array.isArray(references)) {
        return `Found ${references.length} connected page${references.length !== 1 ? 's' : ''}`;
      }
      return 'Finding connections...';
    }
    case 'select_pages': {
      const pages = result.pages as unknown[];
      if (Array.isArray(pages)) {
        return `Selected ${pages.length} page${pages.length !== 1 ? 's' : ''}`;
      }
      return 'Selecting pages...';
    }
    case 'select_pointers': {
      const pointers = result.pointers as unknown[];
      if (Array.isArray(pointers)) {
        return `Highlighting ${pointers.length} area${pointers.length !== 1 ? 's' : ''}`;
      }
      return 'Highlighting areas...';
    }
    default:
      return null;
  }
}

// Generate human-readable text for a completed tool action
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
        return `Searched for "${query}" → Found ${count} area${count !== 1 ? 's' : ''}`;
      }
      return `Found ${count} relevant area${count !== 1 ? 's' : ''}`;
    }
    case 'search_pages': {
      const query = input.query as string;
      const pages = result.pages as unknown[];
      const count = Array.isArray(pages) ? pages.length : 0;
      if (query) {
        return `Searched pages for "${query}" → Found ${count}`;
      }
      return `Found ${count} page${count !== 1 ? 's' : ''}`;
    }
    case 'get_pointer': {
      const title = result.title as string;
      if (title) {
        const truncated = title.length > 40 ? title.slice(0, 40) + '...' : title;
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
    case 'select_pages': {
      const pages = result.pages as unknown[];
      const count = Array.isArray(pages) ? pages.length : 0;
      return `Selected ${count} page${count !== 1 ? 's' : ''} to show`;
    }
    case 'select_pointers': {
      const pointers = result.pointers as unknown[];
      const count = Array.isArray(pointers) ? pointers.length : 0;
      return `Highlighted ${count} area${count !== 1 ? 's' : ''}`;
    }
    default:
      return tool?.replace(/_/g, ' ') || 'Completed action';
  }
}

// Process trace into human-readable actions
interface ProcessedAction {
  type: 'action' | 'thinking';
  text: string;
  isComplete: boolean;
  expandedContent?: string;
}

function processTraceForDisplay(trace: AgentTraceStep[], isStreaming: boolean): ProcessedAction[] {
  const actions: ProcessedAction[] = [];

  // Find the last tool_result index to filter out intermediate reasoning
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

    if (step.type === 'reasoning') {
      // Only show reasoning if it's AFTER the last tool_result (i.e., it's the final answer)
      // Skip intermediate reasoning that came before/between tool calls
      const content = step.content?.trim() || '';
      if (content.length > 20 && i > lastToolResultIndex) {
        const truncated = content.length > 60 ? content.slice(0, 60) + '...' : content;
        actions.push({
          type: 'thinking',
          text: truncated,
          isComplete: true,
          expandedContent: content.length > 60 ? content : undefined,
        });
      }
      i++;
    } else if (step.type === 'tool_call') {
      // Look for matching tool_result
      const nextStep = trace[i + 1];
      if (nextStep?.type === 'tool_result' && nextStep.tool === step.tool) {
        // Completed action
        actions.push({
          type: 'action',
          text: formatCompletedAction(step, nextStep),
          isComplete: true,
        });
        i += 2;
      } else {
        // In-progress tool call (no result yet)
        if (isStreaming) {
          actions.push({
            type: 'action',
            text: step.tool?.replace(/_/g, ' ') || 'Working...',
            isComplete: false,
          });
        }
        i++;
      }
    } else if (step.type === 'tool_result') {
      // Orphan result without call (shouldn't happen, but handle it)
      i++;
    } else {
      i++;
    }
  }

  return actions;
}

// Individual action item component
const ActionItem: React.FC<{
  action: ProcessedAction;
  index: number;
}> = ({ action, index }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="group">
      <button
        onClick={() => action.expandedContent && setIsExpanded(!isExpanded)}
        className={`w-full flex items-center gap-2 py-1.5 px-2 rounded-lg transition-colors ${
          action.expandedContent ? 'hover:bg-slate-100 cursor-pointer' : 'cursor-default'
        }`}
      >
        {/* Status icon */}
        <div className="flex-shrink-0 w-4">
          {action.isComplete ? (
            <CheckCircle2 size={14} className="text-green-500" />
          ) : (
            <Loader2 size={14} className="text-cyan-500 animate-spin" />
          )}
        </div>

        {/* Action text */}
        <span className={`text-xs flex-1 text-left ${
          action.type === 'thinking' ? 'text-slate-500 italic' : 'text-slate-600'
        }`}>
          {action.text}
        </span>

        {/* Expand indicator for thinking with more content */}
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

      {/* Expanded content */}
      {isExpanded && action.expandedContent && (
        <div className="ml-6 mr-2 mt-1 mb-2 p-2 rounded-lg bg-slate-100 border border-slate-200">
          <p className="text-xs text-slate-600 whitespace-pre-wrap leading-relaxed">
            {action.expandedContent}
          </p>
        </div>
      )}
    </div>
  );
};

export const ThinkingSection: React.FC<ThinkingSectionProps> = ({
  reasoning,
  isStreaming,
  autoCollapse = true,
  trace = [],
  initialElapsedTime,
  onNavigateToPage,
  onOpenPointer,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [displayedText, setDisplayedText] = useState('');
  const [currentPhrase, setCurrentPhrase] = useState('Thinking...');
  const [startTime, setStartTime] = useState<number | null>(null);
  const [elapsedTime, setElapsedTime] = useState<number>(initialElapsedTime || 0);
  const wasStreamingRef = useRef(isStreaming);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const intervalRef = useRef<number | null>(null);
  const timerIntervalRef = useRef<number | null>(null);
  const lastPhraseRef = useRef<string>('');

  // Format elapsed time as seconds with 1 decimal
  const formatTime = (ms: number) => `${(ms / 1000).toFixed(1)}s`;

  // Clear typing interval
  const clearTypingInterval = () => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  };

  // Typewrite a phrase
  const typewritePhrase = (phrase: string) => {
    clearTypingInterval();
    setDisplayedText('');
    let charIndex = 0;

    intervalRef.current = window.setInterval(() => {
      if (charIndex < phrase.length) {
        setDisplayedText(phrase.slice(0, charIndex + 1));
        charIndex++;
      } else {
        clearTypingInterval();
      }
    }, 25);
  };

  // Watch trace for tool_results and generate productivity phrases
  useEffect(() => {
    if (!isStreaming) return;

    // Find the latest tool_result
    for (let i = trace.length - 1; i >= 0; i--) {
      const step = trace[i];
      if (step.type === 'tool_result') {
        const phrase = generateProductivityPhrase(step);
        if (phrase && phrase !== lastPhraseRef.current) {
          lastPhraseRef.current = phrase;
          setCurrentPhrase(phrase);
          typewritePhrase(phrase);
        }
        break;
      }
    }
  }, [trace, isStreaming]);

  // Initialize with "Thinking..." when streaming starts
  useEffect(() => {
    if (isStreaming && !wasStreamingRef.current) {
      setCurrentPhrase('Thinking...');
      lastPhraseRef.current = '';
      typewritePhrase('Thinking...');
    }

    if (!isStreaming) {
      clearTypingInterval();
      setDisplayedText('');
    }

    return () => clearTypingInterval();
  }, [isStreaming]);

  // Timer: track elapsed time during streaming
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
    } else if (startTime) {
      // Streaming ended - keep final time
      setElapsedTime(Date.now() - startTime);
    }
  }, [isStreaming, startTime]);

  // Reset timer when trace is cleared (new query)
  useEffect(() => {
    if (trace.length === 0 && !isStreaming) {
      setStartTime(null);
      setElapsedTime(0);
    }
  }, [trace.length, isStreaming]);

  // Auto-scroll to bottom when trace updates during streaming
  useEffect(() => {
    if (isStreaming && isExpanded && scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    }
  }, [trace, isStreaming, isExpanded]);

  // Auto-collapse only when streaming transitions from true to false
  useEffect(() => {
    const wasStreaming = wasStreamingRef.current;
    wasStreamingRef.current = isStreaming;

    if (autoCollapse && wasStreaming && !isStreaming && isExpanded) {
      const timer = setTimeout(() => {
        setIsExpanded(false);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [isStreaming, autoCollapse, isExpanded]);

  // Don't render if no trace and not streaming
  if (trace.length === 0 && !isStreaming) {
    return null;
  }

  // Process trace into human-readable actions
  const processedActions = processTraceForDisplay(trace, isStreaming);

  return (
    <div className="w-1/2 rounded-xl border border-slate-200 bg-slate-50/50 overflow-hidden transition-all duration-200 min-w-0 relative">
      {/* Constellation animation background */}
      <ConstellationAnimation isActive={isStreaming} />

      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="relative z-10 w-full flex items-center gap-2 px-3 py-2 hover:bg-slate-100/50 transition-colors"
      >
        <div className="flex-shrink-0">
          {isExpanded ? (
            <ChevronDown size={14} className="text-slate-400" />
          ) : (
            <ChevronRight size={14} className="text-slate-400" />
          )}
        </div>

        {isStreaming ? (
          /* Streaming: blinking dot + productivity phrase + timer */
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <span className="text-cyan-500 animate-pulse">●</span>
            <span className="text-xs font-medium text-slate-600 truncate">
              {displayedText}
            </span>
            <span className="text-xs font-mono text-slate-400 flex-shrink-0">
              {formatTime(elapsedTime)}
            </span>
          </div>
        ) : (
          /* Completed: hammer icon + "Completed in X.Xs" (or just "Completed" if no time) */
          <>
            <Hammer size={14} className="flex-shrink-0 text-cyan-500" />
            <span className="text-xs font-medium text-slate-600 flex-1 text-left">
              {elapsedTime > 0 ? `Completed in ${formatTime(elapsedTime)}` : 'Completed'}
            </span>
          </>
        )}
      </button>

      {/* Processed actions */}
      {isExpanded && (
        <div ref={scrollContainerRef} className="relative z-10 px-2 pb-2 animate-fade-in max-h-80 overflow-y-auto overflow-x-hidden">
          {processedActions.length === 0 && isStreaming && (
            <div className="flex items-center gap-2 px-2 py-3 text-xs text-slate-400">
              <Loader2 size={12} className="animate-spin" />
              Starting to think...
            </div>
          )}

          {processedActions.map((action, index) => (
            <ActionItem
              key={index}
              action={action}
              index={index}
            />
          ))}
        </div>
      )}
    </div>
  );
};
