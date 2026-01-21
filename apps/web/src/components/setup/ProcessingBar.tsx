import React from 'react';
import { Loader2, Brain } from 'lucide-react';

interface ProcessingBarProps {
  currentPageName: string | null;
  current: number;
  total: number;
  isVisible: boolean;
}

/**
 * Bottom progress bar shown during sheet-analyzer processing.
 * Displays current page being processed with progress.
 */
export const ProcessingBar: React.FC<ProcessingBarProps> = ({
  currentPageName,
  current,
  total,
  isVisible,
}) => {
  if (!isVisible) return null;

  const progress = total > 0 ? (current / total) * 100 : 0;

  return (
    <div className="absolute bottom-0 left-0 right-0 z-20 animate-slide-up">
      <div className="mx-4 mb-4 bg-slate-800/95 backdrop-blur-sm border border-slate-700/50 rounded-lg shadow-xl overflow-hidden">
        <div className="px-4 py-3 flex items-center gap-3">
          {/* Animated brain icon */}
          <div className="relative">
            <Brain size={20} className="text-cyan-400" />
            <div className="absolute inset-0 animate-ping">
              <Brain size={20} className="text-cyan-400 opacity-30" />
            </div>
          </div>

          {/* Status text */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-400">Reading:</span>
              <span className="text-sm font-medium text-white truncate">
                {currentPageName || 'Preparing...'}
              </span>
            </div>
          </div>

          {/* Progress indicator */}
          <div className="flex items-center gap-3 shrink-0">
            <Loader2 size={16} className="text-cyan-400 animate-spin" />
            <span className="text-sm font-mono text-slate-300">
              {current}/{total}
            </span>
          </div>
        </div>

        {/* Progress bar */}
        <div className="h-1 bg-slate-700">
          <div
            className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 transition-all duration-500 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
    </div>
  );
};
