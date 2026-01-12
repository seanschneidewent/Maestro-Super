import React, { useState } from 'react';
import { Loader2, Check, ChevronRight } from 'lucide-react';
import type { AgentToastItem } from '../../contexts/AgentToastContext';

function truncateToWords(text: string, wordCount: number): string {
  const words = text.split(/\s+/);
  if (words.length <= wordCount) return text;
  return words.slice(0, wordCount).join(' ');
}

interface AgentWorkingToastProps {
  toast: AgentToastItem;
  onDismiss: () => void;
  onNavigate: () => void;
}

export const AgentWorkingToast: React.FC<AgentWorkingToastProps> = ({
  toast,
  onDismiss,
  onNavigate,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isWorking = toast.status === 'working';
  const isComplete = toast.status === 'complete';

  const truncatedQuery = truncateToWords(toast.queryText, 5);
  const needsTruncation = truncatedQuery !== toast.queryText;

  const handleClick = () => {
    if (isWorking) {
      // Toggle expand/collapse while working
      setIsExpanded(!isExpanded);
    } else if (isComplete) {
      // Navigate to conversation when complete
      onNavigate();
      onDismiss();
    }
  };

  // Collapse when transitioning to complete
  React.useEffect(() => {
    if (isComplete && isExpanded) {
      setIsExpanded(false);
    }
  }, [isComplete, isExpanded]);

  return (
    <div
      onClick={handleClick}
      className={`
        bg-white/95 backdrop-blur-md border border-slate-200/50 shadow-lg rounded-xl
        px-3 py-2.5 cursor-pointer select-none
        transition-all duration-200 ease-out
        hover:shadow-xl hover:border-slate-300/50
        animate-in fade-in slide-in-from-left-2 duration-200
        ${isExpanded ? 'max-w-sm' : 'max-w-[280px]'}
      `}
    >
      {/* Compact view */}
      {!isExpanded && (
        <div className="flex items-center gap-2">
          {/* Icon */}
          {isWorking ? (
            <Loader2 size={16} className="text-cyan-500 animate-spin flex-shrink-0" />
          ) : (
            <Check size={16} className="text-green-500 flex-shrink-0" />
          )}

          {/* Query text with fade */}
          <div className="flex-1 min-w-0 relative">
            <span className="text-sm text-slate-700 truncate block pr-4">
              "{truncatedQuery}"
            </span>
            {needsTruncation && (
              <div className="absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-white/95 to-transparent pointer-events-none" />
            )}
          </div>

          {/* Status */}
          {isWorking ? (
            <span className="text-xs text-slate-500 flex-shrink-0 whitespace-nowrap">
              Working...
            </span>
          ) : (
            <span className="text-xs text-green-600 font-medium flex-shrink-0 flex items-center gap-0.5 whitespace-nowrap">
              Complete!
              <ChevronRight size={12} />
            </span>
          )}
        </div>
      )}

      {/* Expanded view */}
      {isExpanded && (
        <div className="flex flex-col gap-1.5">
          <div className="flex items-start gap-2">
            <Loader2 size={16} className="text-cyan-500 animate-spin flex-shrink-0 mt-0.5" />
            <p className="text-sm text-slate-700 leading-relaxed">
              "{toast.queryText}"
            </p>
          </div>
          <div className="pl-6">
            <span className="text-xs text-slate-500">Working on it...</span>
          </div>
        </div>
      )}
    </div>
  );
};
