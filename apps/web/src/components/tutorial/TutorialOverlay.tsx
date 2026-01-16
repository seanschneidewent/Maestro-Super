import React, { useEffect, useState } from 'react';
import { X, ChevronLeft } from 'lucide-react';
import { useTutorial } from '../../hooks/useTutorial';
import { TutorialStep } from '../../types';

// Step configuration with target selectors and text
interface StepConfig {
  targetSelector: string | null; // null means centered modal
  text: string;
  position: 'top' | 'bottom' | 'left' | 'right' | 'auto';
  isCenteredModal?: boolean;
}

const STEP_CONFIG: Partial<Record<NonNullable<TutorialStep>, StepConfig>> = {
  welcome: {
    targetSelector: null,
    text: "Let me show you around.",
    position: 'auto',
    isCenteredModal: true,
  },
  'pick-sheet': {
    targetSelector: '[data-tutorial="first-page"]',
    text: "Pick a sheet to get started.",
    position: 'right',
  },
  'page-zoom': {
    targetSelector: '[data-tutorial="page-viewer"]',
    text: "Pinch to zoom in on the page.",
    position: 'left',
  },
  'prompt-suggestions': {
    targetSelector: '[data-tutorial="prompt-suggestions"]',
    text: "Try one of these.",
    position: 'top',
  },
  'background-task': {
    targetSelector: '[data-tutorial="agent-toast"]',
    text: "This is me working. You can still switch pages.",
    position: 'bottom',
  },
  'complete-task': {
    targetSelector: '[data-tutorial="toast-complete-btn"]',
    text: "Tap here when I'm done.",
    position: 'bottom',
  },
  'result-page': {
    targetSelector: '[data-tutorial="first-page-result"]',
    text: "Tap any page to zoom in.",
    position: 'top',
  },
  'new-session': {
    targetSelector: '[data-tutorial="new-conversation-btn"]',
    text: "Start fresh anytime.",
    position: 'left',
  },
  cta: {
    targetSelector: null,
    text: "That's it! Create an account to save your work.",
    position: 'auto',
    isCenteredModal: true,
  },
};

// Padding around highlight
const HIGHLIGHT_PADDING = 8;

// Calculate best position for tooltip based on target location
function calculateTooltipPosition(
  targetRect: DOMRect,
  preferredPosition: 'top' | 'bottom' | 'left' | 'right' | 'auto'
): { top: number; left: number; arrowDirection: 'up' | 'down' | 'left' | 'right' } {
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const tooltipWidth = 280;
  const tooltipHeight = 80;
  const offset = 16;

  let position = preferredPosition;

  // Auto-calculate best position
  if (position === 'auto') {
    const spaceAbove = targetRect.top;
    const spaceBelow = viewportHeight - targetRect.bottom;
    const spaceLeft = targetRect.left;
    const spaceRight = viewportWidth - targetRect.right;

    const maxSpace = Math.max(spaceAbove, spaceBelow, spaceLeft, spaceRight);
    if (maxSpace === spaceBelow) position = 'bottom';
    else if (maxSpace === spaceAbove) position = 'top';
    else if (maxSpace === spaceRight) position = 'right';
    else position = 'left';
  }

  let top = 0;
  let left = 0;
  let arrowDirection: 'up' | 'down' | 'left' | 'right' = 'up';

  switch (position) {
    case 'bottom':
      top = targetRect.bottom + HIGHLIGHT_PADDING + offset;
      left = targetRect.left + targetRect.width / 2 - tooltipWidth / 2;
      arrowDirection = 'up';
      break;
    case 'top':
      top = targetRect.top - HIGHLIGHT_PADDING - offset - tooltipHeight;
      left = targetRect.left + targetRect.width / 2 - tooltipWidth / 2;
      arrowDirection = 'down';
      break;
    case 'right':
      top = targetRect.top + targetRect.height / 2 - tooltipHeight / 2;
      left = targetRect.right + HIGHLIGHT_PADDING + offset;
      arrowDirection = 'left';
      break;
    case 'left':
      top = targetRect.top + targetRect.height / 2 - tooltipHeight / 2;
      left = targetRect.left - HIGHLIGHT_PADDING - offset - tooltipWidth;
      arrowDirection = 'right';
      break;
  }

  // Clamp to viewport
  left = Math.max(16, Math.min(left, viewportWidth - tooltipWidth - 16));
  top = Math.max(16, Math.min(top, viewportHeight - tooltipHeight - 16));

  return { top, left, arrowDirection };
}

// Arrow component pointing in specified direction
const TooltipArrow: React.FC<{ direction: 'up' | 'down' | 'left' | 'right' }> = ({ direction }) => {
  return (
    <div className="absolute" style={{
      ...(direction === 'up' && { top: -10, left: '50%', transform: 'translateX(-50%)' }),
      ...(direction === 'down' && { bottom: -10, left: '50%', transform: 'translateX(-50%) rotate(180deg)' }),
      ...(direction === 'left' && { left: -10, top: '50%', transform: 'translateY(-50%) rotate(-90deg)' }),
      ...(direction === 'right' && { right: -10, top: '50%', transform: 'translateY(-50%) rotate(90deg)' }),
    }}>
      <svg width="20" height="10" viewBox="0 0 20 10" className="text-white drop-shadow-lg">
        <path d="M0 10 L10 0 L20 10 Z" fill="currentColor" />
      </svg>
    </div>
  );
};

// Centered modal component for welcome and CTA steps
const CenteredModal: React.FC<{
  children: React.ReactNode;
  showArrow?: boolean;
}> = ({ children, showArrow = false }) => {
  return (
    <div className="fixed inset-0 flex items-center justify-center z-[62] pointer-events-none">
      <div className="relative pointer-events-auto">
        {/* Bouncing arrow pointing left toward sidebar */}
        {showArrow && (
          <div className="absolute -left-16 top-1/2 -translate-y-1/2">
            <ChevronLeft
              size={40}
              className="text-cyan-500 animate-bounce-horizontal"
            />
          </div>
        )}
        <div
          className="bg-white rounded-2xl shadow-2xl px-8 py-6 max-w-sm text-center"
          style={{
            border: '2px solid rgba(34, 211, 238, 0.8)',
            animation: 'pulse-glow 2s ease-in-out infinite',
          }}
        >
          {children}
        </div>
      </div>
    </div>
  );
};

interface TutorialOverlayProps {
  onGetStarted?: () => void;
}

export const TutorialOverlay: React.FC<TutorialOverlayProps> = ({ onGetStarted }) => {
  const { currentStep, isActive, skipTutorial } = useTutorial();
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);

  const stepConfig = currentStep ? STEP_CONFIG[currentStep] : null;
  const targetSelector = stepConfig?.targetSelector ?? null;

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

    // Keep tracking (element might not exist immediately or might move)
    const interval = setInterval(findTarget, 100);
    window.addEventListener('resize', findTarget);
    window.addEventListener('scroll', findTarget, true);

    return () => {
      clearInterval(interval);
      window.removeEventListener('resize', findTarget);
      window.removeEventListener('scroll', findTarget, true);
    };
  }, [targetSelector]);

  // Don't render if tutorial not active or no step config
  if (!isActive || !stepConfig) return null;

  // Welcome step - centered modal with bouncing arrow
  if (currentStep === 'welcome') {
    return (
      <>
        <CenteredModal showArrow={true}>
          <p className="text-slate-800 text-lg font-medium">
            {stepConfig.text}
          </p>
        </CenteredModal>

        {/* Skip button */}
        <button
          onClick={skipTutorial}
          className="fixed top-4 left-4 z-[63] p-2 rounded-full bg-white/90 hover:bg-white shadow-lg transition-colors"
        >
          <X size={20} className="text-slate-600" />
        </button>

        {/* CSS for animations */}
        <style>{`
          @keyframes pulse-glow {
            0%, 100% { box-shadow: 0 0 12px rgba(34, 211, 238, 0.5); }
            50% { box-shadow: 0 0 24px rgba(34, 211, 238, 0.8); }
          }
          @keyframes bounce-horizontal {
            0%, 100% { transform: translateX(0) translateY(-50%); }
            50% { transform: translateX(-10px) translateY(-50%); }
          }
          .animate-bounce-horizontal {
            animation: bounce-horizontal 1s ease-in-out infinite;
          }
        `}</style>
      </>
    );
  }

  // CTA step - centered modal with button
  if (currentStep === 'cta') {
    return (
      <>
        <CenteredModal>
          <p className="text-slate-800 text-lg font-medium mb-4">
            {stepConfig.text}
          </p>
          {onGetStarted && (
            <button
              onClick={onGetStarted}
              className="px-6 py-3 bg-cyan-500 text-white rounded-xl font-medium text-lg hover:bg-cyan-600 transition-colors shadow-lg"
            >
              Create Account
            </button>
          )}
        </CenteredModal>

        {/* Skip button */}
        <button
          onClick={skipTutorial}
          className="fixed top-4 left-4 z-[63] p-2 rounded-full bg-white/90 hover:bg-white shadow-lg transition-colors"
        >
          <X size={20} className="text-slate-600" />
        </button>

        {/* CSS for animations */}
        <style>{`
          @keyframes pulse-glow {
            0%, 100% { box-shadow: 0 0 12px rgba(34, 211, 238, 0.5); }
            50% { box-shadow: 0 0 24px rgba(34, 211, 238, 0.8); }
          }
        `}</style>
      </>
    );
  }

  // Calculate highlight bounds (with padding)
  const highlightBounds = targetRect ? {
    x: targetRect.left - HIGHLIGHT_PADDING,
    y: targetRect.top - HIGHLIGHT_PADDING,
    width: targetRect.width + HIGHLIGHT_PADDING * 2,
    height: targetRect.height + HIGHLIGHT_PADDING * 2,
  } : null;

  // Calculate tooltip position
  const tooltipPosition = targetRect
    ? calculateTooltipPosition(targetRect, stepConfig.position)
    : null;

  return (
    <>
      {/* Pulsing highlight glow on target - z-40 so expanded modal (z-50) covers it */}
      {highlightBounds && (
        <div
          className="fixed z-40 pointer-events-none rounded-xl"
          style={{
            left: highlightBounds.x,
            top: highlightBounds.y,
            width: highlightBounds.width,
            height: highlightBounds.height,
            border: '2px solid rgba(34, 211, 238, 0.8)',
            animation: 'pulse-glow 2s ease-in-out infinite',
          }}
        />
      )}

      {/* Tooltip card */}
      {tooltipPosition && (
        <div
          className="fixed z-[62] bg-white rounded-xl shadow-2xl px-5 py-4 max-w-[280px] animate-in fade-in slide-in-from-bottom-2 duration-300"
          style={{
            top: tooltipPosition.top,
            left: tooltipPosition.left,
          }}
        >
          <TooltipArrow direction={tooltipPosition.arrowDirection} />
          <p className="text-slate-800 text-base font-medium leading-relaxed">
            {stepConfig.text}
          </p>
        </div>
      )}

      {/* Skip button - positioned top-left to avoid overlap with expanded page modal close button */}
      <button
        onClick={skipTutorial}
        className="fixed top-4 left-4 z-[63] p-2 rounded-full bg-white/90 hover:bg-white shadow-lg transition-colors"
      >
        <X size={20} className="text-slate-600" />
      </button>

      {/* CSS for pulse animation */}
      <style>{`
        @keyframes pulse-glow {
          0%, 100% { box-shadow: 0 0 12px rgba(34, 211, 238, 0.5); }
          50% { box-shadow: 0 0 24px rgba(34, 211, 238, 0.8); }
        }
      `}</style>
    </>
  );
};
