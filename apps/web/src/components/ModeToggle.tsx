import React from 'react';
import { AppMode } from '../types';
import { Settings, Construction, LogOut } from 'lucide-react';

interface ModeToggleProps {
  mode: AppMode;
  setMode: (mode: AppMode) => void;
  variant?: 'dark' | 'light';
}

export const ModeToggle: React.FC<ModeToggleProps> = ({ mode, setMode, variant = 'dark' }) => {
  const isDark = variant === 'dark';

  return (
    <div className={`flex items-center gap-1 p-1 rounded-xl ${
      isDark ? 'glass' : 'bg-slate-100/80 border border-slate-200/50'
    }`}>
      <button
        onClick={() => setMode(AppMode.SETUP)}
        className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
          mode === AppMode.SETUP
            ? isDark
              ? 'bg-cyan-500/20 text-cyan-400 shadow-glow-cyan-sm'
              : 'bg-cyan-500 text-white shadow-glow-cyan-sm'
            : isDark
              ? 'text-slate-400 hover:text-white hover:bg-white/5'
              : 'text-slate-500 hover:text-slate-700 hover:bg-white/50'
        }`}
      >
        <Settings size={14} /> Setup
      </button>
      <button
        onClick={() => setMode(AppMode.USE)}
        className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
          mode === AppMode.USE
            ? isDark
              ? 'bg-cyan-500/20 text-cyan-400 shadow-glow-cyan-sm'
              : 'bg-cyan-500 text-white shadow-glow-cyan-sm'
            : isDark
              ? 'text-slate-400 hover:text-white hover:bg-white/5'
              : 'text-slate-500 hover:text-slate-700 hover:bg-white/50'
        }`}
      >
        <Construction size={14} /> Field
      </button>
      <div className={`w-px h-5 mx-0.5 ${isDark ? 'bg-white/10' : 'bg-slate-300'}`}></div>
      <button
        onClick={() => setMode(AppMode.LOGIN)}
        className="p-2 text-slate-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-all"
        title="Sign Out"
      >
        <LogOut size={14} />
      </button>
    </div>
  );
};
