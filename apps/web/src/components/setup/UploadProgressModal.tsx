import React from 'react';
import { Loader2, AlertCircle, RefreshCw } from 'lucide-react';

interface ProgressStage {
  current: number;
  total: number;
}

interface UploadProgressModalProps {
  isOpen: boolean;
  progress: {
    upload: ProgressStage;
    png: ProgressStage;
    ocr: ProgressStage;
    ai: ProgressStage;
  };
  error?: string;
  onRetry?: () => void;
}

export const UploadProgressModal: React.FC<UploadProgressModalProps> = ({
  isOpen,
  progress,
  error,
  onRetry,
}) => {
  if (!isOpen) return null;

  const isComplete =
    progress.upload.current === progress.upload.total &&
    progress.png.current === progress.png.total &&
    progress.ocr.current === progress.ocr.total &&
    progress.ai.current === progress.ai.total &&
    progress.upload.total > 0;

  const stages = [
    { label: 'Upload', data: progress.upload, color: 'bg-blue-500' },
    { label: 'Rendering', data: progress.png, color: 'bg-green-500' },
    { label: 'Text Extraction', data: progress.ocr, color: 'bg-cyan-500' },
    { label: 'AI Analysis', data: progress.ai, color: 'bg-purple-500' },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fade-in">
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl">
        {/* Header */}
        <div className="flex items-center gap-3 mb-5">
          {error ? (
            <div className="p-2 rounded-full bg-red-500/20">
              <AlertCircle size={20} className="text-red-400" />
            </div>
          ) : isComplete ? (
            <div className="w-9 h-9 rounded-full bg-green-500 flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
              </svg>
            </div>
          ) : (
            <Loader2 className="w-6 h-6 text-cyan-400 animate-spin" />
          )}
          <h3 className="text-lg font-semibold text-white">
            {error ? 'Processing Error' : isComplete ? 'Processing Complete!' : 'Processing Files...'}
          </h3>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30">
            <p className="text-sm text-red-300">{error}</p>
          </div>
        )}

        {/* Progress Bars */}
        <div className="space-y-3">
          {stages.map(({ label, data, color }) => (
            <div key={label}>
              <div className="flex justify-between text-xs text-slate-400 mb-1">
                <span>{label}</span>
                <span>{data.current} / {data.total}</span>
              </div>
              <div className="w-full bg-slate-700 rounded-full h-2">
                <div
                  className={`${color} h-2 rounded-full transition-all duration-300`}
                  style={{
                    width: `${data.total > 0 ? (data.current / data.total) * 100 : 0}%`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>

        {/* Retry Button (only shown on error) */}
        {error && onRetry && (
          <div className="mt-5 flex justify-end">
            <button
              onClick={onRetry}
              className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-medium transition-all flex items-center gap-2"
            >
              <RefreshCw size={14} />
              Retry
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
