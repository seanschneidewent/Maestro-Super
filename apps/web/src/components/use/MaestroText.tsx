import { useState, useEffect, useRef } from 'react';

interface MaestroTextProps {
  text: string;
  state: 'idle' | 'typing' | 'working' | 'complete';
}

export function MaestroText({ text, state }: MaestroTextProps) {
  const [displayedText, setDisplayedText] = useState('');
  const intervalRef = useRef<number | null>(null);
  const prevTextRef = useRef(text);

  // Clear interval
  const clearTypingInterval = () => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  };

  // Handle text and state changes
  useEffect(() => {
    prevTextRef.current = text;

    // Clear existing interval on any change
    clearTypingInterval();

    if (state === 'typing') {
      // Start typewriter effect
      setDisplayedText('');

      let charIndex = 0;
      intervalRef.current = window.setInterval(() => {
        if (charIndex < text.length) {
          setDisplayedText(text.slice(0, charIndex + 1));
          charIndex++;
        } else {
          clearTypingInterval();
        }
      }, 30);
    } else if (state === 'working' || state === 'idle' || state === 'complete') {
      // Show full text instantly
      setDisplayedText(text);
    }

    return () => {
      clearTypingInterval();
    };
  }, [text, state]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearTypingInterval();
    };
  }, []);

  // Status light classes
  const statusLightClasses = state === 'working'
    ? 'text-cyan-500 animate-status-blink'
    : 'text-cyan-500';

  return (
    <div className="flex items-center gap-3">
      <span className={statusLightClasses}>●</span>
      <span className="text-black text-2xl font-mono whitespace-nowrap">
        {displayedText}
      </span>
    </div>
  );
}
