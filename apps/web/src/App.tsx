import React, { useState, useEffect, useRef } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { BrainMode } from './components/brain/BrainMode';
import { MaestroMode } from './components/maestro/MaestroMode';
import { ErrorBoundary } from './components/ErrorBoundary';
import { ToastProvider } from './components/ui/Toast';
import { AgentToastProvider } from './contexts/AgentToastContext';
import { queryClient } from './lib/queryClient';
import { AppMode, Project } from './types';
import { Loader2, ArrowLeft } from 'lucide-react';
import { api } from './lib/api';
import { supabase, signInAnonymously, isAnonymousUser } from './lib/supabase';
import { TutorialProvider, TutorialOverlay } from './components/tutorial';

// Types for brain mode state persistence
interface BrainState {
  selectedFileId: string | null;
  selectedPointerId: string | null;
  isDrawingEnabled: boolean;
  expandedNodes: string[];
}

const App: React.FC = () => {
  const [mode, setMode] = useState<AppMode>(AppMode.LOGIN);
  const [isLoading, setIsLoading] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [authTab, setAuthTab] = useState<'signin' | 'signup'>('signin');
  const [name, setName] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [project, setProject] = useState<Project | null>(null);
  const [projectLoading, setProjectLoading] = useState(false);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [checkingAuth, setCheckingAuth] = useState(true);

  // Track when we intentionally want to show login (not auto-sign-in anonymously)
  const pendingLoginRef = useRef(false);
  // Track current user ID to avoid reloading project on token refresh
  const currentUserIdRef = useRef<string | null>(null);

  // Persistent state for Brain mode (survives mode switches)
  const localFileMapRef = useRef<Map<string, File>>(new Map());
  const [brainState, setBrainState] = useState<BrainState>({
    selectedFileId: null,
    selectedPointerId: null,
    isDrawingEnabled: false,
    expandedNodes: [],
  });

  // Initialize auth - check session or sign in anonymously
  useEffect(() => {
    async function initAuth() {
      // Dev mode bypass - skip Supabase auth entirely
      if (import.meta.env.VITE_DEV_MODE === 'true') {
        console.log('[DEV] Auth bypassed - going straight to USE mode');
        setMode(AppMode.USE);
        setCheckingAuth(false);
        return;
      }

      const { data: { session } } = await supabase.auth.getSession();

      if (session) {
        currentUserIdRef.current = session.user.id;
        if (isAnonymousUser(session)) {
          setMode(AppMode.DEMO);
        } else {
          setMode(AppMode.USE);
        }
      } else {
        // No session - sign in anonymously for demo mode
        try {
          await signInAnonymously();
          setMode(AppMode.DEMO);
        } catch (err) {
          console.error('Failed to sign in anonymously:', err);
          setMode(AppMode.LOGIN);
        }
      }
      setCheckingAuth(false);
    }
    initAuth();

    // Listen for auth changes (skip in dev mode)
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (import.meta.env.VITE_DEV_MODE === 'true') return; // Don't override dev mode
      if (event === 'SIGNED_IN' && session) {
        if (isAnonymousUser(session)) {
          // Don't switch to DEMO if we're transitioning to LOGIN
          // (Supabase auto-signs-in anonymously after signOut)
          if (pendingLoginRef.current) {
            return;
          }
          setMode(AppMode.DEMO);
        } else {
          pendingLoginRef.current = false; // Clear flag on real login
          // Only clear project if user actually changed (not just token refresh)
          if (currentUserIdRef.current !== session.user.id) {
            setProject(null);
          }
          currentUserIdRef.current = session.user.id;
          setMode(AppMode.USE);
        }
      } else if (event === 'SIGNED_OUT') {
        currentUserIdRef.current = null;
        setProject(null);
        // Check if this is intentional (user clicked "Get Started")
        if (pendingLoginRef.current) {
          // Don't reset pendingLoginRef here - keep it true to block auto-anonymous-signin
          setMode(AppMode.LOGIN);
        } else {
          // After sign out, try anonymous sign-in for demo mode
          signInAnonymously()
            .then(() => setMode(AppMode.DEMO))
            .catch(() => setMode(AppMode.LOGIN));
        }
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  // Load or create default project when authenticated
  useEffect(() => {
    if (mode === AppMode.LOGIN || checkingAuth) return;

    // Demo mode uses demo project ID from env
    if (mode === AppMode.DEMO) {
      const demoProjectId = import.meta.env.VITE_DEMO_PROJECT_ID;
      if (demoProjectId) {
        setProject({
          id: demoProjectId,
          name: 'Demo Project',
          status: 'ready' as const,
          createdAt: new Date().toISOString()
        });
      }
      setProjectLoading(false);
      return;
    }

    if (project) return; // Already have project, skip loading

    async function loadProject() {
      try {
        setProjectLoading(true);
        setProjectError(null);
        console.log('[DEV] loadProject starting, calling api.projects.list()...');

        const projects = await api.projects.list();
        console.log('[DEV] loadProject got projects:', projects);

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
  }, [mode, checkingAuth, project]);

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

  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault();

    if (password !== confirmPassword) {
      setAuthError('Passwords do not match');
      return;
    }

    if (password.length < 6) {
      setAuthError('Password must be at least 6 characters');
      return;
    }

    setIsLoading(true);
    setAuthError(null);

    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          full_name: name,
        },
      },
    });

    if (error) {
      setAuthError(error.message);
    } else {
      setAuthError('Check your email for a confirmation link!');
    }
    setIsLoading(false);
  };

  const handleTabSwitch = (tab: 'signin' | 'signup') => {
    setAuthTab(tab);
    setEmail('');
    setPassword('');
    setName('');
    setConfirmPassword('');
    setAuthError(null);
  };

  const handleGoogleSignIn = async () => {
    setIsLoading(true);
    setAuthError(null);

    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        scopes: 'https://www.googleapis.com/auth/drive.readonly',
        redirectTo: window.location.origin,
      },
    });

    if (error) {
      setAuthError(error.message);
      setIsLoading(false);
    }
    // Note: OAuth redirects, so we don't need to set loading to false on success
  };

  const handleGetStarted = async () => {
    pendingLoginRef.current = true;
    await supabase.auth.signOut();
  };

  const handleBackToDemo = async () => {
    try {
      // Clear the pending login flag so we can go back to demo
      pendingLoginRef.current = false;
      // Reset tutorial so it shows again
      localStorage.removeItem('maestro-tutorial-completed');
      // Sign in anonymously for demo mode
      await signInAnonymously();
      setMode(AppMode.DEMO);
    } catch (err) {
      console.error('Failed to return to demo:', err);
    }
  };

  // Show loading while checking auth
  if (checkingAuth) {
    return (
      <div className="fixed inset-0 bg-gradient-radial-dark flex items-center justify-center font-sans">
        <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
      </div>
    );
  }

  if (mode === AppMode.LOGIN) {
    return (
        <div className="fixed inset-0 bg-gradient-radial-dark flex items-center justify-center p-4 font-sans blueprint-grid-dark">
            <div className="glass-panel p-8 rounded-2xl w-full max-w-md animate-scale-in">
                <div className="text-center mb-8">
                    <h1 className="text-3xl font-bold text-white mb-2">
                      Maestro<span className="text-cyan-400 drop-shadow-[0_0_10px_rgba(6,182,212,0.5)]">4D</span>
                    </h1>
                    <p className="text-slate-400 text-sm">Construction plan intelligence</p>
                </div>
                {/* Tab Selector */}
                <div className="flex mb-6 bg-slate-800/30 rounded-lg p-1">
                    <button
                        type="button"
                        onClick={() => handleTabSwitch('signin')}
                        className={`flex-1 py-2.5 rounded-md text-sm font-medium transition-all ${
                            authTab === 'signin'
                                ? 'bg-slate-700 text-white'
                                : 'text-slate-400 hover:text-white'
                        }`}
                    >
                        Sign In
                    </button>
                    <button
                        type="button"
                        onClick={() => handleTabSwitch('signup')}
                        className={`flex-1 py-2.5 rounded-md text-sm font-medium transition-all ${
                            authTab === 'signup'
                                ? 'bg-slate-700 text-white'
                                : 'text-slate-400 hover:text-white'
                        }`}
                    >
                        Create Account
                    </button>
                </div>

                <form onSubmit={authTab === 'signin' ? handleLogin : handleSignUp} className="space-y-5">
                    {/* Name field - only for signup */}
                    {authTab === 'signup' && (
                        <div>
                            <label className="block text-xs font-semibold text-slate-400 uppercase mb-2 tracking-wider">Name</label>
                            <input
                                type="text"
                                placeholder="John Smith"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                className="w-full p-3.5 bg-slate-800/50 border border-slate-700/50 rounded-xl text-white placeholder-slate-500 focus:border-cyan-500/50 focus:bg-slate-800/70 transition-all"
                                required
                            />
                        </div>
                    )}

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

                    {/* Confirm password - only for signup */}
                    {authTab === 'signup' && (
                        <div>
                            <label className="block text-xs font-semibold text-slate-400 uppercase mb-2 tracking-wider">Confirm Password</label>
                            <input
                                type="password"
                                placeholder="••••••••"
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                className="w-full p-3.5 bg-slate-800/50 border border-slate-700/50 rounded-xl text-white placeholder-slate-500 focus:border-cyan-500/50 focus:bg-slate-800/70 transition-all"
                                required
                            />
                        </div>
                    )}

                    {authError && (
                        <p className={`text-sm ${authError.includes('Check your email') ? 'text-green-400' : 'text-red-400'}`}>
                            {authError}
                        </p>
                    )}

                    <button
                        type="submit"
                        disabled={isLoading}
                        className="w-full btn-primary text-white font-bold py-3.5 rounded-xl flex justify-center items-center mt-6"
                    >
                        {isLoading ? (
                            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        ) : authTab === 'signin' ? 'Sign In' : 'Create Account'}
                    </button>
                </form>

                {/* Google Sign In */}
                <div className="mt-6">
                    <div className="relative">
                        <div className="absolute inset-0 flex items-center">
                            <div className="w-full border-t border-slate-700/50" />
                        </div>
                        <div className="relative flex justify-center text-xs">
                            <span className="px-2 bg-slate-900/50 text-slate-500">or</span>
                        </div>
                    </div>
                    <button
                        type="button"
                        onClick={handleGoogleSignIn}
                        disabled={isLoading}
                        className="mt-4 w-full bg-white hover:bg-gray-100 text-gray-800 font-medium py-3.5 rounded-xl flex justify-center items-center gap-3 transition-all disabled:opacity-50"
                    >
                        <svg className="w-5 h-5" viewBox="0 0 24 24">
                            <path
                                fill="#4285F4"
                                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                            />
                            <path
                                fill="#34A853"
                                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                            />
                            <path
                                fill="#FBBC05"
                                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                            />
                            <path
                                fill="#EA4335"
                                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                            />
                        </svg>
                        Continue with Google
                    </button>
                    <p className="mt-3 text-xs text-slate-500 text-center">
                        Sign in with Google to import files from Drive
                    </p>
                </div>
                <div className="mt-8 pt-6 border-t border-white/5 text-center">
                    <button
                      onClick={handleBackToDemo}
                      className="text-xs text-slate-500 hover:text-cyan-400 transition-colors flex items-center gap-2 mx-auto"
                    >
                        <ArrowLeft size={12} />
                        Back to Demo
                    </button>
                </div>
            </div>
        </div>
    );
  }

  // Show loading state while project loads
  if (projectLoading) {
    return (
      <div className="fixed inset-0 bg-gradient-radial-dark flex items-center justify-center font-sans">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
          <p className="text-slate-400 text-sm">Loading project...</p>
        </div>
      </div>
    );
  }

  // Demo mode - field only with demo header in sidebar
  if (mode === AppMode.DEMO && project) {
    return (
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <ErrorBoundary>
            <TutorialProvider>
              <AgentToastProvider>
                <TutorialOverlay onGetStarted={handleGetStarted} />
                <MaestroMode
                  mode={mode}
                  setMode={setMode}
                  projectId={project.id}
                  onGetStarted={handleGetStarted}
                />
              </AgentToastProvider>
            </TutorialProvider>
          </ErrorBoundary>
        </ToastProvider>
      </QueryClientProvider>
    );
  }

  // Show error state
  if (projectError || !project) {
    return (
      <div className="fixed inset-0 bg-gradient-radial-dark flex items-center justify-center font-sans">
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

  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <ToastProvider>
          {/* Render both modes but hide inactive one to preserve state */}
          <div className={mode === AppMode.SETUP ? 'contents' : 'hidden'}>
            <BrainMode
              mode={mode}
              setMode={setMode}
              projectId={project.id}
              localFileMapRef={localFileMapRef}
              brainState={brainState}
              setBrainState={setBrainState}
            />
          </div>
          <div className={mode === AppMode.USE ? 'contents' : 'hidden'}>
            <AgentToastProvider>
              <MaestroMode mode={mode} setMode={setMode} projectId={project.id} />
            </AgentToastProvider>
          </div>
        </ToastProvider>
      </ErrorBoundary>
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
};

export default App;
