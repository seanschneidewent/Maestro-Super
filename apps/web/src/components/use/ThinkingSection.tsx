import React, { useState, useEffect, useRef } from 'react';
import { ChevronDown, ChevronRight, Brain, Hammer, Search, FileText, File, Folder, List, GitBranch, CheckCircle2, Loader2 } from 'lucide-react';
import type { AgentTraceStep } from '../../types';

// Working phrases for cycling during streaming
const WORKING_PHRASES = [
  "Searching...",
  "Looking for details...",
  "Hunting through the plans...",
  "Looking through pages...",
  "Looking closer...",
  "Checking that out...",
  "Examining...",
  "Reading the page...",
  "Seeing what's here...",
  "Getting the overview...",
  "Zooming out...",
  "Finding references...",
  "Tracking connections...",
  "Following the trail...",
  "Pulling up the sheets...",
  "Loading pages...",
  "Highlighting...",
  "Marking the spots...",
  "Browsing the project...",
];

// Map tool names to icons and display names
const TOOL_CONFIG: Record<string, { icon: React.ReactNode; name: string }> = {
  search_pointers: { icon: <Search size={12} />, name: 'Search pointers' },
  get_pointer: { icon: <FileText size={12} />, name: 'Get pointer details' },
  get_page_context: { icon: <File size={12} />, name: 'Get page context' },
  get_discipline_overview: { icon: <Folder size={12} />, name: 'Get discipline overview' },
  list_project_pages: { icon: <List size={12} />, name: 'List project pages' },
  get_references_to_page: { icon: <GitBranch size={12} />, name: 'Get page references' },
};

interface ThinkingSectionProps {
  reasoning: string[];
  isStreaming: boolean;
  autoCollapse?: boolean;
  trace?: AgentTraceStep[];
  onNavigateToPage?: (pageId: string) => void;
  onOpenPointer?: (pointerId: string) => void;
}

// Individual expandable step component
const TraceStepItem: React.FC<{
  step: AgentTraceStep;
  index: number;
  isLast: boolean;
  isStreaming: boolean;
  onNavigateToPage?: (pageId: string) => void;
  onOpenPointer?: (pointerId: string) => void;
}> = ({ step, index, isLast, isStreaming, onNavigateToPage, onOpenPointer }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const toolConfig = step.tool ? TOOL_CONFIG[step.tool] : null;

  // Get step display info
  const getStepInfo = () => {
    if (step.type === 'reasoning') {
      // Truncate for display
      const text = step.content || '';
      const truncated = text.length > 80 ? text.slice(0, 80) + '...' : text;
      return {
        icon: <Brain size={12} />,
        title: truncated || 'Thinking...',
        color: 'text-purple-500',
        bgColor: 'bg-purple-50',
        hasDetails: text.length > 80,
      };
    }
    if (step.type === 'tool_call') {
      return {
        icon: toolConfig?.icon || <FileText size={12} />,
        title: toolConfig?.name || step.tool?.replace(/_/g, ' ') || 'Tool call',
        color: 'text-cyan-500',
        bgColor: 'bg-cyan-50',
        hasDetails: !!step.input && Object.keys(step.input).length > 0,
      };
    }
    if (step.type === 'tool_result') {
      return {
        icon: <CheckCircle2 size={12} />,
        title: `${toolConfig?.name || step.tool?.replace(/_/g, ' ') || 'Tool'} result`,
        color: 'text-green-500',
        bgColor: 'bg-green-50',
        hasDetails: !!step.result,
      };
    }
    return { icon: <FileText size={12} />, title: 'Unknown', color: 'text-slate-500', bgColor: 'bg-slate-50', hasDetails: false };
  };

  const info = getStepInfo();
  const showSpinner = isLast && isStreaming && step.type === 'tool_call';

  // Format result data for display
  const formatResult = (result: Record<string, unknown>) => {
    // Check for common result patterns
    if (result.pages && Array.isArray(result.pages)) {
      return `Found ${result.pages.length} pages`;
    }
    if (result.pointers && Array.isArray(result.pointers)) {
      return `Found ${result.pointers.length} pointers`;
    }
    if (result.disciplines && Array.isArray(result.disciplines)) {
      return `Found ${result.disciplines.length} disciplines`;
    }
    if (result.error) {
      return `Error: ${result.error}`;
    }
    // Truncate JSON for display
    const json = JSON.stringify(result, null, 2);
    return json.length > 500 ? json.slice(0, 500) + '...' : json;
  };

  return (
    <div className="group min-w-0">
      <button
        onClick={() => info.hasDetails && setIsExpanded(!isExpanded)}
        className={`w-full flex items-center gap-2 py-1.5 px-2 rounded-lg transition-colors min-w-0 ${
          info.hasDetails ? 'hover:bg-slate-100 cursor-pointer' : 'cursor-default'
        }`}
      >
        {/* Expand chevron or spacer */}
        <div className="w-3 flex-shrink-0">
          {info.hasDetails && (
            isExpanded ? (
              <ChevronDown size={10} className="text-slate-400" />
            ) : (
              <ChevronRight size={10} className="text-slate-400" />
            )
          )}
        </div>

        {/* Icon */}
        <div className={`flex-shrink-0 ${info.color}`}>
          {showSpinner ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            info.icon
          )}
        </div>

        {/* Title */}
        <span className="text-xs text-slate-600 flex-1 text-left truncate min-w-0">
          {info.title}
        </span>

        {/* Step number */}
        <span className="text-[10px] text-slate-400 font-mono flex-shrink-0">
          {(index + 1).toString().padStart(2, '0')}
        </span>
      </button>

      {/* Expanded details */}
      {isExpanded && info.hasDetails && (
        <div className={`ml-5 mr-2 mt-1 mb-2 p-2 rounded-lg ${info.bgColor} border border-slate-100 animate-fade-in overflow-hidden`}>
          {step.type === 'reasoning' && step.content && (
            <p className="text-xs text-slate-600 whitespace-pre-wrap leading-relaxed">
              {step.content}
            </p>
          )}

          {step.type === 'tool_call' && step.input && (
            <div className="space-y-1">
              <p className="text-[10px] font-medium text-slate-500 uppercase tracking-wide">Input</p>
              <pre className="text-xs text-slate-600 font-mono whitespace-pre-wrap break-all">
                {JSON.stringify(step.input, null, 2)}
              </pre>
            </div>
          )}

          {step.type === 'tool_result' && step.result && (
            <div className="space-y-1">
              <p className="text-[10px] font-medium text-slate-500 uppercase tracking-wide">Result</p>
              <pre className="text-xs text-slate-600 font-mono whitespace-pre-wrap break-all max-h-48 overflow-y-auto">
                {formatResult(step.result)}
              </pre>
            </div>
          )}
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
  onNavigateToPage,
  onOpenPointer,
}) => {
  const [isExpanded, setIsExpanded] = useState(false); // Start collapsed
  const [displayedText, setDisplayedText] = useState(''); // For typewriter effect
  const [startTime, setStartTime] = useState<number | null>(null);
  const [elapsedTime, setElapsedTime] = useState<number>(0);
  const wasStreamingRef = useRef(isStreaming);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const intervalRef = useRef<number | null>(null);
  const timeoutRef = useRef<number | null>(null);
  const timerIntervalRef = useRef<number | null>(null);
  const phraseIndexRef = useRef(0);

  // Format elapsed time as seconds with 1 decimal
  const formatTime = (ms: number) => `${(ms / 1000).toFixed(1)}s`;

  // Clear typing interval
  const clearTypingInterval = () => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  };

  // Clear delay timeout
  const clearDelayTimeout = () => {
    if (timeoutRef.current !== null) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  };

  // Typewrite a phrase, then call onComplete when done
  const typewritePhrase = (phrase: string, onComplete: () => void) => {
    setDisplayedText('');
    let charIndex = 0;

    intervalRef.current = window.setInterval(() => {
      if (charIndex < phrase.length) {
        setDisplayedText(phrase.slice(0, charIndex + 1));
        charIndex++;
      } else {
        clearTypingInterval();
        onComplete();
      }
    }, 30);
  };

  // Start cycling through working phrases
  const startWorkingCycle = () => {
    // Pick a random starting index
    phraseIndexRef.current = Math.floor(Math.random() * WORKING_PHRASES.length);

    const cycleNext = () => {
      const phrase = WORKING_PHRASES[phraseIndexRef.current];
      phraseIndexRef.current = (phraseIndexRef.current + 1) % WORKING_PHRASES.length;

      typewritePhrase(phrase, () => {
        // Wait 5 seconds then start next phrase
        timeoutRef.current = window.setTimeout(cycleNext, 5000);
      });
    };

    cycleNext();
  };

  // Handle streaming state changes for typewriter effect
  useEffect(() => {
    if (isStreaming) {
      startWorkingCycle();
    } else {
      clearTypingInterval();
      clearDelayTimeout();
      setDisplayedText('');
    }

    return () => {
      clearTypingInterval();
      clearDelayTimeout();
    };
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

  // Count step types for header
  const toolCallCount = trace.filter(s => s.type === 'tool_call').length;

  return (
    <div className="w-1/2 rounded-xl border border-slate-200 bg-slate-50/50 overflow-hidden transition-all duration-200 min-w-0">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-slate-100/50 transition-colors"
      >
        <div className="flex-shrink-0">
          {isExpanded ? (
            <ChevronDown size={14} className="text-slate-400" />
          ) : (
            <ChevronRight size={14} className="text-slate-400" />
          )}
        </div>

        {isStreaming ? (
          /* Streaming: blinking dot + cycling typewriter text + timer */
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
          /* Completed: hammer icon + "See my process." + final time */
          <>
            <Hammer size={14} className="flex-shrink-0 text-cyan-500" />
            <span className="text-xs font-medium text-slate-600 flex-1 text-left">
              See my process.
            </span>
            {elapsedTime > 0 && (
              <span className="text-xs font-mono text-slate-400 flex-shrink-0">
                {formatTime(elapsedTime)}
              </span>
            )}
          </>
        )}
      </button>

      {/* Trace steps */}
      {isExpanded && (
        <div ref={scrollContainerRef} className="px-2 pb-2 animate-fade-in max-h-80 overflow-y-auto overflow-x-hidden">
          {trace.length === 0 && isStreaming && (
            <div className="flex items-center gap-2 px-2 py-3 text-xs text-slate-400">
              <Loader2 size={12} className="animate-spin" />
              Starting to think...
            </div>
          )}

          {trace.map((step, index) => (
            <TraceStepItem
              key={index}
              step={step}
              index={index}
              isLast={index === trace.length - 1}
              isStreaming={isStreaming}
              onNavigateToPage={onNavigateToPage}
              onOpenPointer={onOpenPointer}
            />
          ))}
        </div>
      )}
    </div>
  );
};
