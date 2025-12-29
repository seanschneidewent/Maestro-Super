import React, { useState } from 'react';
import { SetupMode } from './components/setup/SetupMode';
import { UseMode } from './components/use/UseMode';
import { AppMode } from './types';
import { Settings, LogOut, Layout, Construction } from 'lucide-react';

const App: React.FC = () => {
  const [mode, setMode] = useState<AppMode>(AppMode.LOGIN);
  const [isLoading, setIsLoading] = useState(false);

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setTimeout(() => {
        setIsLoading(false);
        setMode(AppMode.USE);
    }, 1500);
  };

  if (mode === AppMode.LOGIN) {
    return (
        <div className="min-h-screen bg-gradient-radial-dark flex items-center justify-center p-4 font-sans blueprint-grid-dark">
            <div className="glass-panel p-8 rounded-2xl w-full max-w-md animate-scale-in">
                <div className="text-center mb-8">
                    <h1 className="text-3xl font-bold text-white mb-2">
                      Maestro<span className="text-cyan-400 drop-shadow-[0_0_10px_rgba(6,182,212,0.5)]">4D</span>
                    </h1>
                    <p className="text-slate-400 text-sm">Construction plan intelligence</p>
                </div>
                <form onSubmit={handleLogin} className="space-y-5">
                    <div>
                        <label className="block text-xs font-semibold text-slate-400 uppercase mb-2 tracking-wider">Email</label>
                        <input
                          type="email"
                          placeholder="super@site.com"
                          className="w-full p-3.5 bg-slate-800/50 border border-slate-700/50 rounded-xl text-white placeholder-slate-500 focus:border-cyan-500/50 focus:bg-slate-800/70 transition-all"
                          required
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-semibold text-slate-400 uppercase mb-2 tracking-wider">Password</label>
                        <input
                          type="password"
                          placeholder="••••••••"
                          className="w-full p-3.5 bg-slate-800/50 border border-slate-700/50 rounded-xl text-white placeholder-slate-500 focus:border-cyan-500/50 focus:bg-slate-800/70 transition-all"
                          required
                        />
                    </div>
                    <button
                        type="submit"
                        disabled={isLoading}
                        className="w-full btn-primary text-white font-bold py-3.5 rounded-xl flex justify-center items-center mt-6"
                    >
                        {isLoading ? (
                            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        ) : "Sign In"}
                    </button>
                </form>
                <div className="mt-8 pt-6 border-t border-white/5 text-center">
                    <button
                      onClick={() => setMode(AppMode.SETUP)}
                      className="text-xs text-slate-500 hover:text-cyan-400 transition-colors flex items-center gap-2 mx-auto"
                    >
                        <Settings size={12} />
                        Switch to Setup Mode (Admin)
                    </button>
                </div>
            </div>
        </div>
    );
  }

  return (
    <div className="relative">
      {/* Mode Switcher - Floating Pill */}
      <div className="fixed bottom-5 left-5 z-50 glass rounded-2xl p-1.5 toolbar-float animate-fade-in">
        <div className="flex items-center gap-1">
           <button
              onClick={() => setMode(AppMode.SETUP)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold transition-all ${
                mode === AppMode.SETUP
                  ? 'bg-cyan-500/20 text-cyan-400 shadow-glow-cyan-sm'
                  : 'text-slate-400 hover:text-white hover:bg-white/5'
              }`}
           >
              <Settings size={14} /> Setup
           </button>
           <button
              onClick={() => setMode(AppMode.USE)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold transition-all ${
                mode === AppMode.USE
                  ? 'bg-cyan-500/20 text-cyan-400 shadow-glow-cyan-sm'
                  : 'text-slate-400 hover:text-white hover:bg-white/5'
              }`}
           >
              <Construction size={14} /> Field
           </button>
           <div className="w-px h-6 bg-white/10 mx-1"></div>
           <button
             onClick={() => setMode(AppMode.LOGIN)}
             className="p-2.5 text-slate-500 hover:text-red-400 hover:bg-red-500/10 rounded-xl transition-all"
           >
              <LogOut size={14} />
           </button>
        </div>
      </div>

      {mode === AppMode.SETUP ? <SetupMode /> : <UseMode />}
    </div>
  );
};

export default App;
