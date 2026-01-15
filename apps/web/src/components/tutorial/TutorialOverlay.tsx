import React, { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { useTutorial } from '../../hooks/useTutorial';
import { TutorialStep } from '../../types';

// Step configuration with target selectors and text
interface StepConfig {
  targetSelector: string | null; // null means center screen (no target)
  text: string;
  position: 'top' | 'bottom' | 'left' | 'right' | 'auto';
}

const STEP_CONFIG: Partial<Record<NonNullable<TutorialStep>, StepConfig>> = {
  welcome: {
    targetSelector: '[data-tutorial="sidebar-expand"]',
    text: "Let me show you around.",
    position: 'right',
  },
  sidebar: {
    targetSelector: '[data-tutorial="first-page"]',
    text: "Pick a sheet to get started.",
    position: 'right',
  },
  'toast-working': {
    targetSelector: '[data-tutorial="agent-toast"]',
    text: "I'm finding what you need.",
    position: 'bottom',
  },
  'toast-complete': {
    targetSelector: '[data-tutorial="toast-complete-btn"]',
    text: "Tap here to see what I found.",
    position: 'bottom',
  },
  thinking: {
    targetSelector: '[data-tutorial="thinking-section"]',
    text: "Here's what I did and how long it took.",
    position: 'left',
  },
  'page-zoom': {
    targetSelector: '[data-tutorial="first-page-result"]',
    text: "Tap any page to zoom in.",
    position: 'top',
  },
  'query-again': {
    targetSelector: '[data-tutorial="query-input"]',
    text: "Ask me anything else.",
    position: 'top',
  },
  history: {
    targetSelector: '[data-tutorial="history-btn"]',
    text: "Your conversations save here.",
    position: 'bottom',
  },
  'new-convo': {
    targetSelector: '[data-tutorial="new-conversation-btn"]',
    text: "Start fresh anytime.",
    position: 'top',
  },
  complete: {
    targetSelector: null, // Center screen
    text: "That's it! Create an account.",
    position: 'auto',
  },
};

// Padding around spotlight cutout
const SPOTLIGHT_PADDING = 12;

// Calculate best position for tooltip based on target location
function calculateTooltipPosition(
  targetRect: DOMRect,
  preferredPosition: 'top' | 'bottom' | 'left' | 'right' | 'auto'
): { top: number; left: number; arrowDirection: 'up' | 'down' | 'left' | 'right' } {
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const tooltipWidth = 280;
  const tooltipHeight = 80;
  const offset = 20;

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
      top = targetRect.bottom + SPOTLIGHT_PADDING + offset;
      left = targetRect.left + targetRect.width / 2 - tooltipWidth / 2;
      arrowDirection = 'up';
      break;
    case 'top':
      top = targetRect.top - SPOTLIGHT_PADDING - offset - tooltipHeight;
      left = targetRect.left + targetRect.width / 2 - tooltipWidth / 2;
      arrowDirection = 'down';
      break;
    case 'right':
      top = targetRect.top + targetRect.height / 2 - tooltipHeight / 2;
      left = targetRect.right + SPOTLIGHT_PADDING + offset;
      arrowDirection = 'left';
      break;
    case 'left':
      top = targetRect.top + targetRect.height / 2 - tooltipHeight / 2;
      left = targetRect.left - SPOTLIGHT_PADDING - offset - tooltipWidth;
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
  const rotations = {
    up: 'rotate-0',
    down: 'rotate-180',
    left: '-rotate-90',
    right: 'rotate-90',
  };

  return (
    <div className={`absolute ${rotations[direction]}`} style={{
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

export const TutorialOverlay: React.FC = () => {
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

  // Don't render if tutorial not active
  if (!isActive || !stepConfig) return null;

  // Calculate spotlight bounds (with padding)
  const spotlightBounds = targetRect ? {
    x: targetRect.left - SPOTLIGHT_PADDING,
    y: targetRect.top - SPOTLIGHT_PADDING,
    width: targetRect.width + SPOTLIGHT_PADDING * 2,
    height: targetRect.height + SPOTLIGHT_PADDING * 2,
  } : null;

  // Calculate tooltip position
  const tooltipPosition = targetRect
    ? calculateTooltipPosition(targetRect, stepConfig.position)
    : null;

  // For center screen (no target), show tooltip in center
  const isCentered = !targetSelector;

  return (
    <>
      {/* Dimmed overlay with spotlight cutout */}
      <div className="fixed inset-0 z-[60]" style={{ pointerEvents: 'none' }}>
        <svg className="w-full h-full">
          <defs>
            <mask id="spotlight-mask">
              {/* White = visible (dimmed), Black = hidden (spotlight) */}
              <rect x="0" y="0" width="100%" height="100%" fill="white" />
              {spotlightBounds && (
                <rect
                  x={spotlightBounds.x}
                  y={spotlightBounds.y}
                  width={spotlightBounds.width}
                  height={spotlightBounds.height}
                  rx="12"
                  fill="black"
                />
              )}
            </mask>
          </defs>
          {/* Dimmed background */}
          <rect
            x="0"
            y="0"
            width="100%"
            height="100%"
            fill="rgba(0, 0, 0, 0.7)"
            mask="url(#spotlight-mask)"
            style={{ pointerEvents: 'auto' }}
          />
        </svg>
      </div>

      {/* Spotlight glow ring */}
      {spotlightBounds && (
        <div
          className="fixed z-[61] pointer-events-none rounded-xl border-2 border-cyan-400 animate-pulse"
          style={{
            left: spotlightBounds.x,
            top: spotlightBounds.y,
            width: spotlightBounds.width,
            height: spotlightBounds.height,
            boxShadow: '0 0 30px rgba(34, 211, 238, 0.5), 0 0 60px rgba(34, 211, 238, 0.3)',
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
            pointerEvents: 'auto',
          }}
        >
          <TooltipArrow direction={tooltipPosition.arrowDirection} />
          <p className="text-slate-800 text-base font-medium leading-relaxed">
            {stepConfig.text}
          </p>
        </div>
      )}

      {/* Centered tooltip (for complete step) */}
      {isCentered && (
        <div className="fixed inset-0 z-[62] flex items-center justify-center pointer-events-none">
          <div
            className="bg-white rounded-xl shadow-2xl px-6 py-5 max-w-[320px] animate-in fade-in zoom-in-95 duration-300 pointer-events-auto text-center"
          >
            <p className="text-slate-800 text-lg font-medium leading-relaxed">
              {stepConfig.text}
            </p>
          </div>
        </div>
      )}

      {/* Skip button */}
      <button
        onClick={skipTutorial}
        className="fixed top-4 right-4 z-[63] p-2 rounded-full bg-white/90 hover:bg-white shadow-lg transition-colors"
        style={{ pointerEvents: 'auto' }}
      >
        <X size={20} className="text-slate-600" />
      </button>
    </>
  );
};
