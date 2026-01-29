import React, { useEffect, useState } from 'react';
import { Check } from 'lucide-react';

interface ProcessingNotificationProps {
  pageName: string | null;
  detailCount: number;
  onDismiss: () => void;
}

/**
 * Top notification shown briefly when a page completes processing.
 * Auto-fades after 2 seconds.
 */
export const ProcessingNotification: React.FC<ProcessingNotificationProps> = ({
  pageName,
  detailCount,
  onDismiss,
}) => {
  const [isVisible, setIsVisible] = useState(false);
  const [isExiting, setIsExiting] = useState(false);

  useEffect(() => {
    if (pageName) {
      setIsVisible(true);
      setIsExiting(false);

      // Start exit animation after 2 seconds
      const exitTimer = setTimeout(() => {
        setIsExiting(true);
      }, 2000);

      // Fully dismiss after animation completes
      const dismissTimer = setTimeout(() => {
        setIsVisible(false);
        onDismiss();
      }, 2300);

      return () => {
        clearTimeout(exitTimer);
        clearTimeout(dismissTimer);
      };
    }
  }, [pageName, onDismiss]);

  if (!isVisible || !pageName) return null;

  return (
    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-30 pointer-events-none">
      <div
        className={`flex items-center gap-2 px-4 py-2.5 bg-slate-800/95 backdrop-blur-sm
                    border border-green-500/30 rounded-lg shadow-xl shadow-green-900/10
                    transition-all duration-300 ease-out
                    ${isExiting ? 'opacity-0 -translate-y-2' : 'opacity-100 translate-y-0 animate-slide-down'}`}
      >
        {/* Green checkmark with pulse */}
        <div className="relative">
          <div className="w-5 h-5 bg-green-500 rounded-full flex items-center justify-center">
            <Check size={12} className="text-white" strokeWidth={3} />
          </div>
          <div className="absolute inset-0 w-5 h-5 bg-green-500 rounded-full animate-ping opacity-30" />
        </div>

        {/* Text */}
        <span className="text-sm text-white font-medium">{pageName}</span>
        <span className="text-sm text-slate-400">complete</span>
        {detailCount > 0 && (
          <span className="text-xs text-cyan-400 bg-cyan-500/10 px-1.5 py-0.5 rounded">
            {detailCount} detail{detailCount !== 1 ? 's' : ''}
          </span>
        )}
      </div>
    </div>
  );
};
