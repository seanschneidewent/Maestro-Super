import React from 'react';
import { Loader2, Brain, Pause, Play } from 'lucide-react';

interface ProcessingBarProps {
  currentPageName: string | null;
  current: number;
  total: number;
  isVisible: boolean;
  isPaused?: boolean;
  onPause?: () => void;
  onResume?: () => void;
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
  isPaused = false,
  onPause,
  onResume,
}) => {
  if (!isVisible) return null;

  const progress = total > 0 ? (current / total) * 100 : 0;

  return (
    <div className="absolute bottom-0 left-0 right-0 z-20 animate-slide-up">
      <div className="mx-4 mb-4 bg-slate-800/95 backdrop-blur-sm border border-slate-700/50 rounded-lg shadow-xl overflow-hidden">
        <div className="px-4 py-3 flex items-center gap-3">
          {/* Animated brain icon */}
          <div className="relative">
            <Brain size={20} className={isPaused ? "text-amber-400" : "text-cyan-400"} />
            {!isPaused && (
              <div className="absolute inset-0 animate-ping">
                <Brain size={20} className="text-cyan-400 opacity-30" />
              </div>
            )}
          </div>

          {/* Status text */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-400">
                {isPaused ? 'Paused:' : 'Reading:'}
              </span>
              <span className="text-sm font-medium text-white truncate">
                {isPaused
                  ? `${current}/${total} pages complete`
                  : (currentPageName || 'Preparing...')}
              </span>
            </div>
          </div>

          {/* Pause/Resume button */}
          {isPaused ? (
            onResume && (
              <button
                onClick={onResume}
                className="flex items-center gap-2 px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-medium rounded-md transition-colors"
              >
                <Play size={14} />
                Resume
              </button>
            )
          ) : (
            onPause && (
              <button
                onClick={onPause}
                className="flex items-center gap-2 px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white text-sm font-medium rounded-md transition-colors"
              >
                <Pause size={14} />
                Pause
              </button>
            )
          )}

          {/* Progress indicator */}
          <div className="flex items-center gap-3 shrink-0">
            {!isPaused && <Loader2 size={16} className="text-cyan-400 animate-spin" />}
            <span className="text-sm font-mono text-slate-300">
              {current}/{total}
            </span>
          </div>
        </div>

        {/* Progress bar */}
        <div className="h-1 bg-slate-700">
          <div
            className={`h-full transition-all duration-500 ease-out ${
              isPaused
                ? 'bg-gradient-to-r from-amber-500 to-orange-500'
                : 'bg-gradient-to-r from-cyan-500 to-blue-500'
            }`}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
    </div>
  );
};
