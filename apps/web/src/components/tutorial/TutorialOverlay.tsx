import React, { useEffect, useState } from 'react';
import { useTutorial } from '../../hooks/useTutorial';
import { TutorialStep } from '../../types';

interface StepConfig {
  text: string;
  subtitle: string;
  targetSelector: string;
}

const STEP_CONFIG: Partial<Record<NonNullable<TutorialStep>, StepConfig>> = {
  welcome: {
    text: 'Welcome to Maestro Super',
    subtitle: 'Click the sidebar icon to begin',
    targetSelector: '[data-tutorial="sidebar-expand"]',
  },
  sidebar: {
    text: 'Your plans, organized by trade',
    subtitle: 'Select a sheet to view',
    targetSelector: '[data-tutorial="first-page"]',
  },
};

export const TutorialOverlay: React.FC = () => {
  const { currentStep, isActive, skipTutorial } = useTutorial();
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);

  const config = currentStep ? STEP_CONFIG[currentStep] : null;

  // Find and track target element
  useEffect(() => {
    if (!config?.targetSelector) {
      setTargetRect(null);
      return;
    }

    const findTarget = () => {
      const el = document.querySelector(config.targetSelector);
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
  }, [config?.targetSelector]);

  // Only show for pre-page steps (welcome, sidebar)
  if (!isActive || !config) return null;

  return (
    <>
      {/* Skip button */}
      <button
        onClick={skipTutorial}
        className="fixed top-4 right-4 z-[60] px-3 py-1.5 text-sm text-slate-500 hover:text-slate-700 bg-white/90 backdrop-blur-sm rounded-lg border border-slate-200/50 transition-colors shadow-sm"
      >
        Skip Tutorial
      </button>

      {/* Semi-transparent backdrop */}
      <div className="fixed inset-0 z-[45] bg-slate-900/20 pointer-events-none" />

      {/* Center text */}
      <div className="fixed inset-0 z-[50] pointer-events-none flex items-center justify-center">
        <div className="text-center animate-fade-in">
          <h1 className="text-3xl font-semibold text-slate-800 mb-3 drop-shadow-sm">
            {config.text}
          </h1>
          <p className="text-lg text-slate-600">{config.subtitle}</p>
        </div>
      </div>

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
