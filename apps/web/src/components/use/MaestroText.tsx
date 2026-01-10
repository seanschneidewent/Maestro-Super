import { useState, useEffect, useRef } from 'react';

interface MaestroTextProps {
  text: string;
  state: 'idle' | 'typing' | 'working' | 'complete';
}

type CursorState = 'typing' | 'blinking' | 'hidden';

export function MaestroText({ text, state }: MaestroTextProps) {
  const [displayedText, setDisplayedText] = useState('');
  const [cursorState, setCursorState] = useState<CursorState>('hidden');

  const intervalRef = useRef<number | null>(null);
  const timeoutRefs = useRef<number[]>([]);
  const prevTextRef = useRef(text);
  const prevStateRef = useRef(state);

  // Clear all timeouts
  const clearTimeouts = () => {
    timeoutRefs.current.forEach(id => clearTimeout(id));
    timeoutRefs.current = [];
  };

  // Clear interval
  const clearTypingInterval = () => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  };

  // Handle text and state changes
  useEffect(() => {
    const textChanged = text !== prevTextRef.current;
    const stateChanged = state !== prevStateRef.current;

    prevTextRef.current = text;
    prevStateRef.current = state;

    // Clear existing intervals and timeouts on any change
    clearTypingInterval();
    clearTimeouts();

    if (state === 'typing') {
      // Start typewriter effect
      setDisplayedText('');
      setCursorState('typing');

      let charIndex = 0;
      intervalRef.current = window.setInterval(() => {
        if (charIndex < text.length) {
          setDisplayedText(text.slice(0, charIndex + 1));
          charIndex++;
        } else {
          // Typing complete - start blink-out sequence
          clearTypingInterval();
          setCursorState('blinking');

          // Blink 2x then hide: on 300ms, off 300ms, on 300ms, off 300ms, hide
          // The 'blinking' state shows cursor, we'll toggle it manually
          let t1 = window.setTimeout(() => setCursorState('hidden'), 300);
          let t2 = window.setTimeout(() => setCursorState('blinking'), 600);
          let t3 = window.setTimeout(() => setCursorState('hidden'), 900);
          let t4 = window.setTimeout(() => setCursorState('blinking'), 1200);
          let t5 = window.setTimeout(() => setCursorState('hidden'), 1500);

          timeoutRefs.current.push(t1, t2, t3, t4, t5);
        }
      }, 30);
    } else if (state === 'working' || state === 'idle') {
      // Show full text instantly, no cursor
      setDisplayedText(text);
      setCursorState('hidden');
    } else if (state === 'complete') {
      // If was typing, the blink sequence handles itself
      // If not, just show full text
      if (!textChanged && displayedText === text) {
        // Already finished typing, let blink sequence continue
      } else {
        setDisplayedText(text);
        setCursorState('hidden');
      }
    }

    return () => {
      clearTypingInterval();
      clearTimeouts();
    };
  }, [text, state]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearTypingInterval();
      clearTimeouts();
    };
  }, []);

  // Status light classes
  const statusLightClasses = state === 'working'
    ? 'text-cyan-500 animate-status-blink'
    : 'text-cyan-500';

  // Cursor visibility
  const showCursor = cursorState === 'typing' || cursorState === 'blinking';
  const cursorClasses = cursorState === 'typing' ? 'animate-cursor-blink' : '';

  return (
    <div className="flex items-center gap-3">
      <span className={statusLightClasses}>●</span>
      <span className="text-black text-2xl whitespace-nowrap">
        {displayedText}
        {showCursor && <span className={cursorClasses}>█</span>}
      </span>
    </div>
  );
}
