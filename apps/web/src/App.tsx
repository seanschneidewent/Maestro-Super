import React, { useState, useEffect, useRef } from 'react';
import { SetupMode } from './components/setup/SetupMode';
import { UseMode } from './components/use/UseMode';
import { AppMode, Project } from './types';
import { Settings, Loader2 } from 'lucide-react';
import { api } from './lib/api';
import { supabase } from './lib/supabase';

// Types for setup mode state persistence
interface SetupState {
  selectedFileId: string | null;
  selectedPointerId: string | null;
  activeTool: 'select' | 'rect' | 'text';
}

const App: React.FC = () => {
  const [mode, setMode] = useState<AppMode>(AppMode.LOGIN);
  const [isLoading, setIsLoading] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [project, setProject] = useState<Project | null>(null);
  const [projectLoading, setProjectLoading] = useState(false);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [checkingAuth, setCheckingAuth] = useState(true);

  // Persistent state for Setup mode (survives mode switches)
  const localFileMapRef = useRef<Map<string, File>>(new Map());
  const [setupState, setSetupState] = useState<SetupState>({
    selectedFileId: null,
    selectedPointerId: null,
    activeTool: 'select',
  });

  // Check for existing session on mount
  useEffect(() => {
    async function checkSession() {
      const { data: { session } } = await supabase.auth.getSession();
      if (session) {
        setMode(AppMode.USE);
      }
      setCheckingAuth(false);
    }
    checkSession();

    // Listen for auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'SIGNED_IN' && session) {
        setMode(AppMode.USE);
      } else if (event === 'SIGNED_OUT') {
        setMode(AppMode.LOGIN);
        setProject(null);
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  // Load or create default project when authenticated
  useEffect(() => {
    if (mode === AppMode.LOGIN || checkingAuth) return;

    async function loadProject() {
      try {
        setProjectLoading(true);
        setProjectError(null);

        const projects = await api.projects.list();

        if (projects.length > 0) {
          setProject(projects[0]);
        } else {
          const newProject = await api.projects.create('My Project');
          setProject(newProject);
        }
      } catch (err) {
        console.error('Failed to load project:', err);
        setProjectError(err instanceof Error ? err.message : 'Failed to load project');
      } finally {
        setProjectLoading(false);
      }
    }

    loadProject();
  }, [mode, checkingAuth]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setAuthError(null);

    const { error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    if (error) {
      setAuthError(error.message);
      setIsLoading(false);
    } else {
      setIsLoading(false);
      setMode(AppMode.USE);
    }
  };

  const handleSignUp = async () => {
    setIsLoading(true);
    setAuthError(null);

    const { error } = await supabase.auth.signUp({
      email,
      password,
    });

    if (error) {
      setAuthError(error.message);
    } else {
      setAuthError('Check your email for a confirmation link!');
    }
    setIsLoading(false);
  };

  // Show loading while checking auth
  if (checkingAuth) {
    return (
      <div className="min-h-screen bg-gradient-radial-dark flex items-center justify-center font-sans">
        <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
      </div>
    );
  }

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
                          value={email}
                          onChange={(e) => setEmail(e.target.value)}
                          className="w-full p-3.5 bg-slate-800/50 border border-slate-700/50 rounded-xl text-white placeholder-slate-500 focus:border-cyan-500/50 focus:bg-slate-800/70 transition-all"
                          required
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-semibold text-slate-400 uppercase mb-2 tracking-wider">Password</label>
                        <input
                          type="password"
                          placeholder="••••••••"
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                          className="w-full p-3.5 bg-slate-800/50 border border-slate-700/50 rounded-xl text-white placeholder-slate-500 focus:border-cyan-500/50 focus:bg-slate-800/70 transition-all"
                          required
                        />
                    </div>
                    {authError && (
                      <p className={`text-sm ${authError.includes('Check your email') ? 'text-green-400' : 'text-red-400'}`}>
                        {authError}
                      </p>
                    )}
                    <div className="flex gap-3 mt-6">
                        <button
                            type="submit"
                            disabled={isLoading}
                            className="flex-1 btn-primary text-white font-bold py-3.5 rounded-xl flex justify-center items-center"
                        >
                            {isLoading ? (
                                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                            ) : "Sign In"}
                        </button>
                        <button
                            type="button"
                            onClick={handleSignUp}
                            disabled={isLoading}
                            className="flex-1 bg-slate-700/50 hover:bg-slate-700 text-white font-bold py-3.5 rounded-xl flex justify-center items-center transition-all border border-slate-600/50"
                        >
                            Sign Up
                        </button>
                    </div>
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

  // Show loading state while project loads
  if (projectLoading) {
    return (
      <div className="min-h-screen bg-gradient-radial-dark flex items-center justify-center font-sans">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
          <p className="text-slate-400 text-sm">Loading project...</p>
        </div>
      </div>
    );
  }

  // Show error state
  if (projectError || !project) {
    return (
      <div className="min-h-screen bg-gradient-radial-dark flex items-center justify-center font-sans">
        <div className="glass-panel p-8 rounded-2xl max-w-md text-center">
          <p className="text-red-400 mb-4">{projectError || 'Failed to load project'}</p>
          <button
            onClick={() => window.location.reload()}
            className="btn-primary px-6 py-2 rounded-lg text-white"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return mode === AppMode.SETUP
    ? <SetupMode
        mode={mode}
        setMode={setMode}
        projectId={project.id}
        localFileMapRef={localFileMapRef}
        setupState={setupState}
        setSetupState={setSetupState}
      />
    : <UseMode mode={mode} setMode={setMode} projectId={project.id} />;
};

export default App;
