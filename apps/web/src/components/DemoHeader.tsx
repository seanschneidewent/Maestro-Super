import React from 'react';
import { LogIn } from 'lucide-react';

interface DemoHeaderProps {
  onGetStarted: () => void;
}

export const DemoHeader: React.FC<DemoHeaderProps> = ({ onGetStarted }) => {
  return (
    <div className="flex items-center gap-1 p-1 rounded-xl bg-slate-100/80 border border-slate-200/50">
      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-cyan-500 text-white shadow-glow-cyan-sm">
        <div className="w-2 h-2 rounded-full bg-white animate-pulse" />
        <span className="text-xs font-semibold">Demo Mode</span>
      </div>
      <div className="w-px h-5 mx-0.5 bg-slate-300"></div>
      <button
        onClick={onGetStarted}
        className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold text-slate-500 hover:text-cyan-600 hover:bg-cyan-500/10 transition-all"
        title="Get Started"
      >
        <LogIn size={14} />
        <span>Get Started</span>
      </button>
    </div>
  );
};
