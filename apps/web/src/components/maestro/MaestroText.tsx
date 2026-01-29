import { useState, useEffect, useRef } from 'react';

interface MaestroTextProps {
  text: string;
  state: 'idle' | 'typing' | 'working' | 'complete';
}

// Unique working phrases (deduped from original tool-specific messages)
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

export function MaestroText({ text, state }: MaestroTextProps) {
  const [displayedText, setDisplayedText] = useState('');
  const intervalRef = useRef<number | null>(null);
  const timeoutRef = useRef<number | null>(null);
  const phraseIndexRef = useRef(0);

  // Clear interval
  const clearTypingInterval = () => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  };

  // Clear timeout
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

  // Handle state changes
  useEffect(() => {
    // Clear existing timers on any change
    clearTypingInterval();
    clearDelayTimeout();

    if (state === 'typing') {
      // Typewrite the provided text
      typewritePhrase(text, () => {});
    } else if (state === 'working') {
      // Start cycling through working phrases
      startWorkingCycle();
    } else if (state === 'idle' || state === 'complete') {
      // Show full text instantly
      setDisplayedText(text);
    }

    return () => {
      clearTypingInterval();
      clearDelayTimeout();
    };
  }, [text, state]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearTypingInterval();
      clearDelayTimeout();
    };
  }, []);

  // Status light classes
  const statusLightClasses = state === 'working'
    ? 'text-cyan-500 animate-status-blink'
    : 'text-cyan-500';

  return (
    <div className="flex items-center gap-3">
      <span className={statusLightClasses}>●</span>
      <span className="text-black text-2xl whitespace-nowrap">
        {displayedText}
      </span>
    </div>
  );
}
