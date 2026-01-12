import React, { useState, useEffect, useRef } from 'react';
import { Check, ChevronRight } from 'lucide-react';
import type { AgentToastItem } from '../../contexts/AgentToastContext';

// Working phrases (same as ThinkingSection)
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

function truncateToWords(text: string, wordCount: number): string {
  const words = text.split(/\s+/);
  if (words.length <= wordCount) return text;
  return words.slice(0, wordCount).join(' ') + '...';
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
  const isWorking = toast.status === 'working';
  const isComplete = toast.status === 'complete';
  const truncatedQuery = truncateToWords(toast.queryText, 5);

  // Typewriter state
  const [displayedText, setDisplayedText] = useState('');
  const intervalRef = useRef<number | null>(null);
  const timeoutRef = useRef<number | null>(null);
  const phraseIndexRef = useRef(Math.floor(Math.random() * WORKING_PHRASES.length));

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
  const typewritePhrase = (phrase: string, onTypeComplete: () => void) => {
    setDisplayedText('');
    let charIndex = 0;

    intervalRef.current = window.setInterval(() => {
      if (charIndex < phrase.length) {
        setDisplayedText(phrase.slice(0, charIndex + 1));
        charIndex++;
      } else {
        clearTypingInterval();
        onTypeComplete();
      }
    }, 30);
  };

  // Start cycling through working phrases
  const startWorkingCycle = () => {
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

  // Handle working state for typewriter effect
  useEffect(() => {
    if (isWorking) {
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
  }, [isWorking]);

  const handleCompleteClick = () => {
    onNavigate();
    onDismiss();
  };

  return (
    <div className="flex flex-col gap-1.5 animate-in fade-in slide-in-from-left-2 duration-200 max-w-[280px]">
      {/* Blue query bubble */}
      <div className="bg-blue-600 text-white px-3 py-2 rounded-2xl shadow-md">
        <span className="text-sm">{truncatedQuery}</span>
      </div>

      {/* Working indicator or Complete button */}
      {isWorking ? (
        <div className="rounded-xl border border-slate-200 bg-slate-50/80 backdrop-blur-sm px-3 py-2 shadow-sm">
          <div className="flex items-center gap-2">
            <span className="text-cyan-500 animate-pulse">●</span>
            <span className="text-xs font-medium text-slate-600 truncate">
              {displayedText}
            </span>
          </div>
        </div>
      ) : (
        <button
          onClick={handleCompleteClick}
          className="rounded-xl border border-green-200 bg-green-50/80 backdrop-blur-sm px-3 py-2 shadow-sm
                     hover:bg-green-100 hover:border-green-300 transition-colors cursor-pointer
                     flex items-center gap-2"
        >
          <Check size={14} className="text-green-600" />
          <span className="text-xs font-medium text-green-700">Complete!</span>
          <ChevronRight size={12} className="text-green-600 ml-auto" />
        </button>
      )}
    </div>
  );
};
