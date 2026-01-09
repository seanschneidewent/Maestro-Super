import React, { useEffect, useState } from 'react';
import { useTutorial } from '../../hooks/useTutorial';
import { TutorialStep } from '../../types';

const BUBBLE_TEXT: Partial<Record<NonNullable<TutorialStep>, string>> = {
  viewer: 'Pinch to zoom. Drag to pan.',
  query: 'Ask me anything about these plans.',
  complete: 'Try your hardest to break me.',
};

export const TutorialBubble: React.FC = () => {
  const { currentStep, isActive, advanceStep, skipTutorial } = useTutorial();
  const [isVisible, setIsVisible] = useState(false);

  const text = currentStep ? BUBBLE_TEXT[currentStep] : null;

  // Fade in animation
  useEffect(() => {
    if (text) {
      const timer = setTimeout(() => setIsVisible(true), 100);
      return () => clearTimeout(timer);
    } else {
      setIsVisible(false);
    }
  }, [text]);

  // Auto-advance after 3 seconds for 'viewer' step
  useEffect(() => {
    if (currentStep === 'viewer') {
      const timer = setTimeout(advanceStep, 3000);
      return () => clearTimeout(timer);
    }
  }, [currentStep, advanceStep]);

  // Auto-end tutorial after 'complete' step shows briefly
  useEffect(() => {
    if (currentStep === 'complete') {
      const timer = setTimeout(advanceStep, 2500);
      return () => clearTimeout(timer);
    }
  }, [currentStep, advanceStep]);

  if (!isActive || !text) return null;

  return (
    <div
      className={`absolute bottom-28 left-1/2 -translate-x-1/2 z-40 transition-all duration-300 ${
        isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2'
      }`}
    >
      <div className="relative bg-slate-800 text-white px-5 py-3 rounded-2xl shadow-xl max-w-sm">
        <p className="text-sm font-medium">{text}</p>

        {/* Speech bubble tail */}
        <div className="absolute -bottom-2 left-1/2 -translate-x-1/2 w-0 h-0 border-l-[10px] border-r-[10px] border-t-[10px] border-transparent border-t-slate-800" />

        {/* Skip link for query step */}
        {currentStep === 'query' && (
          <button
            onClick={skipTutorial}
            className="absolute -top-8 right-0 text-xs text-slate-400 hover:text-slate-200 transition-colors"
          >
            Skip
          </button>
        )}
      </div>
    </div>
  );
};
