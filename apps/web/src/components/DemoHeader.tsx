import React from 'react';

interface DemoHeaderProps {
  onGetStarted: () => void;
}

export const DemoHeader: React.FC<DemoHeaderProps> = ({ onGetStarted }) => {
  return (
    <div className="absolute top-4 right-4 z-40 flex items-center gap-3">
      <div className="flex items-center gap-2 px-3 py-1.5 bg-white/80 backdrop-blur-sm rounded-lg border border-slate-200/50">
        <div className="w-2 h-2 rounded-full bg-cyan-500 animate-pulse" />
        <span className="text-sm text-slate-600 font-medium">Demo Mode</span>
      </div>
      <button
        onClick={onGetStarted}
        className="px-4 py-2 bg-cyan-500 hover:bg-cyan-600 text-white font-semibold rounded-xl shadow-lg transition-all hover:shadow-cyan-500/25 hover:scale-105"
      >
        Get Started
      </button>
    </div>
  );
};
