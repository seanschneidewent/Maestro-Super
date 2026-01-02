import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, Brain } from 'lucide-react';

interface ThinkingSectionProps {
  /** Array of reasoning strings streamed from the agent */
  reasoning: string[];
  /** Whether the agent is still streaming */
  isStreaming: boolean;
  /** Auto-collapse when streaming completes */
  autoCollapse?: boolean;
}

export const ThinkingSection: React.FC<ThinkingSectionProps> = ({
  reasoning,
  isStreaming,
  autoCollapse = true,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  // Auto-collapse when streaming completes
  useEffect(() => {
    if (autoCollapse && !isStreaming && isExpanded) {
      // Delay collapse slightly so user can see the final state
      const timer = setTimeout(() => {
        setIsExpanded(false);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [isStreaming, autoCollapse, isExpanded]);

  // Don't render if no reasoning
  if (reasoning.length === 0 && !isStreaming) {
    return null;
  }

  const combinedText = reasoning.join('');

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
        <div className="px-3 pb-3 animate-fade-in">
          <div className="text-xs text-slate-500 leading-relaxed whitespace-pre-wrap font-mono bg-white rounded-lg p-3 border border-slate-100 max-h-48 overflow-y-auto">
            {combinedText || (isStreaming ? 'Starting to think...' : 'No reasoning recorded')}
            {isStreaming && (
              <span className="inline-block w-1.5 h-4 bg-cyan-400 ml-0.5 animate-pulse" />
            )}
          </div>
        </div>
      )}
    </div>
  );
};
