import React, { useEffect, useState } from 'react';
import { useTutorial } from '../../hooks/useTutorial';
import { TutorialStep } from '../../types';

// Target selectors for each step
const TARGET_SELECTORS: Partial<Record<NonNullable<TutorialStep>, string>> = {
  welcome: '[data-tutorial="sidebar-expand"]',
  sidebar: '[data-tutorial="first-page"]',
};

export const TutorialOverlay: React.FC = () => {
  const { currentStep, isActive } = useTutorial();
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);

  const targetSelector = currentStep ? TARGET_SELECTORS[currentStep] : null;

  // Find and track target element
  useEffect(() => {
    if (!targetSelector) {
      setTargetRect(null);
      return;
    }

    const findTarget = () => {
      const el = document.querySelector(targetSelector);
      if (el) {
        setTargetRect(el.getBoundingClientRect());
      } else {
        setTargetRect(null);
      }
    };

    // Initial find
    findTarget();

    // Keep tracking (element might not exist immediately)
    const interval = setInterval(findTarget, 100);
    window.addEventListener('resize', findTarget);
    window.addEventListener('scroll', findTarget, true);

    return () => {
      clearInterval(interval);
      window.removeEventListener('resize', findTarget);
      window.removeEventListener('scroll', findTarget, true);
    };
  }, [targetSelector]);

  // Only show for pre-page steps (welcome, sidebar)
  if (!isActive || !targetSelector) return null;

  return (
    <>
      {/* Highlight ring around target */}
      {targetRect && (
        <>
          {/* Glowing ring */}
          <div
            className="fixed z-[55] pointer-events-none rounded-xl border-2 border-cyan-500 animate-pulse"
            style={{
              left: targetRect.left - 8,
              top: targetRect.top - 8,
              width: targetRect.width + 16,
              height: targetRect.height + 16,
              boxShadow: '0 0 20px rgba(6, 182, 212, 0.5), 0 0 40px rgba(6, 182, 212, 0.3)',
            }}
          />

          {/* Arrow pointing to target */}
          <div
            className="fixed z-[55] pointer-events-none"
            style={{
              left: targetRect.left + targetRect.width / 2 - 20,
              top: targetRect.top - 50,
            }}
          >
            <svg
              width="40"
              height="40"
              viewBox="0 0 40 40"
              className="animate-bounce text-cyan-500"
            >
              <path
                d="M20 5 L20 30 M12 22 L20 30 L28 22"
                stroke="currentColor"
                strokeWidth="3"
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
        </>
      )}
    </>
  );
};
