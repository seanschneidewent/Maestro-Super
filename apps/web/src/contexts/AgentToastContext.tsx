import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';

export interface AgentToastItem {
  id: string;
  queryText: string;
  queryId: string;
  status: 'working' | 'complete';
  createdAt: number;
  completedAt?: number;
}

interface AgentToastContextValue {
  toasts: AgentToastItem[];
  addToast: (queryText: string, queryId: string) => string;
  markComplete: (toastId: string) => void;
  dismissToast: (toastId: string) => void;
}

const AgentToastContext = createContext<AgentToastContextValue | null>(null);

const MAX_TOASTS = 5;
const AUTO_DISMISS_MS = 10000;

interface AgentToastProviderProps {
  children: React.ReactNode;
}

export const AgentToastProvider: React.FC<AgentToastProviderProps> = ({ children }) => {
  const [toasts, setToasts] = useState<AgentToastItem[]>([]);
  const timersRef = useRef<Map<string, NodeJS.Timeout>>(new Map());

  // Clean up timers on unmount
  useEffect(() => {
    return () => {
      timersRef.current.forEach((timer) => clearTimeout(timer));
    };
  }, []);

  const dismissToast = useCallback((toastId: string) => {
    // Clear any existing timer
    const existingTimer = timersRef.current.get(toastId);
    if (existingTimer) {
      clearTimeout(existingTimer);
      timersRef.current.delete(toastId);
    }
    setToasts((prev) => prev.filter((t) => t.id !== toastId));
  }, []);

  const addToast = useCallback((queryText: string, queryId: string): string => {
    const id = `agent-toast-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const newToast: AgentToastItem = {
      id,
      queryText,
      queryId,
      status: 'working',
      createdAt: Date.now(),
    };

    setToasts((prev) => {
      // Add to front (newest first), limit to MAX_TOASTS
      const updated = [newToast, ...prev].slice(0, MAX_TOASTS);
      return updated;
    });

    return id;
  }, []);

  const markComplete = useCallback((toastId: string) => {
    setToasts((prev) =>
      prev.map((t) =>
        t.id === toastId
          ? { ...t, status: 'complete' as const, completedAt: Date.now() }
          : t
      )
    );

    // Start auto-dismiss timer
    const timer = setTimeout(() => {
      dismissToast(toastId);
    }, AUTO_DISMISS_MS);
    timersRef.current.set(toastId, timer);
  }, [dismissToast]);

  return (
    <AgentToastContext.Provider value={{ toasts, addToast, markComplete, dismissToast }}>
      {children}
    </AgentToastContext.Provider>
  );
};

export const useAgentToast = (): AgentToastContextValue => {
  const context = useContext(AgentToastContext);
  if (!context) {
    throw new Error('useAgentToast must be used within an AgentToastProvider');
  }
  return context;
};
