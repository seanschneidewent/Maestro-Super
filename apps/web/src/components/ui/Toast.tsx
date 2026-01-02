import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { X, CheckCircle, AlertCircle, AlertTriangle, Info } from 'lucide-react';

type ToastType = 'success' | 'error' | 'warning' | 'info';

interface Toast {
  id: string;
  message: string;
  type: ToastType;
  duration?: number;
}

interface ToastContextValue {
  showToast: (message: string, type?: ToastType, duration?: number) => void;
  showError: (message: string, duration?: number) => void;
  showSuccess: (message: string, duration?: number) => void;
  showWarning: (message: string, duration?: number) => void;
  showInfo: (message: string, duration?: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const TOAST_ICONS: Record<ToastType, React.ReactNode> = {
  success: <CheckCircle size={18} />,
  error: <AlertCircle size={18} />,
  warning: <AlertTriangle size={18} />,
  info: <Info size={18} />,
};

const TOAST_STYLES: Record<ToastType, string> = {
  success: 'bg-green-50 border-green-200 text-green-800',
  error: 'bg-red-50 border-red-200 text-red-800',
  warning: 'bg-amber-50 border-amber-200 text-amber-800',
  info: 'bg-blue-50 border-blue-200 text-blue-800',
};

const TOAST_ICON_STYLES: Record<ToastType, string> = {
  success: 'text-green-500',
  error: 'text-red-500',
  warning: 'text-amber-500',
  info: 'text-blue-500',
};

interface ToastItemProps {
  toast: Toast;
  onDismiss: (id: string) => void;
}

const ToastItem: React.FC<ToastItemProps> = ({ toast, onDismiss }) => {
  useEffect(() => {
    if (toast.duration && toast.duration > 0) {
      const timer = setTimeout(() => {
        onDismiss(toast.id);
      }, toast.duration);
      return () => clearTimeout(timer);
    }
  }, [toast.id, toast.duration, onDismiss]);

  return (
    <div
      className={`flex items-start gap-3 p-4 rounded-lg border shadow-lg animate-slide-up ${TOAST_STYLES[toast.type]}`}
      role="alert"
    >
      <div className={`flex-shrink-0 ${TOAST_ICON_STYLES[toast.type]}`}>
        {TOAST_ICONS[toast.type]}
      </div>
      <div className="flex-1 text-sm font-medium">{toast.message}</div>
      <button
        onClick={() => onDismiss(toast.id)}
        className="flex-shrink-0 p-1 rounded hover:bg-black/5 transition-colors"
        aria-label="Dismiss"
      >
        <X size={16} />
      </button>
    </div>
  );
};

interface ToastProviderProps {
  children: React.ReactNode;
}

export const ToastProvider: React.FC<ToastProviderProps> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, type: ToastType = 'info', duration: number = 5000) => {
      const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      setToasts((prev) => [...prev, { id, message, type, duration }]);
    },
    []
  );

  const showError = useCallback(
    (message: string, duration: number = 7000) => {
      showToast(message, 'error', duration);
    },
    [showToast]
  );

  const showSuccess = useCallback(
    (message: string, duration: number = 5000) => {
      showToast(message, 'success', duration);
    },
    [showToast]
  );

  const showWarning = useCallback(
    (message: string, duration: number = 6000) => {
      showToast(message, 'warning', duration);
    },
    [showToast]
  );

  const showInfo = useCallback(
    (message: string, duration: number = 5000) => {
      showToast(message, 'info', duration);
    },
    [showToast]
  );

  return (
    <ToastContext.Provider
      value={{ showToast, showError, showSuccess, showWarning, showInfo }}
    >
      {children}
      {/* Toast container - fixed at bottom right */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none">
        {toasts.map((toast) => (
          <div key={toast.id} className="pointer-events-auto">
            <ToastItem toast={toast} onDismiss={removeToast} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
};

export const useToast = (): ToastContextValue => {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
};
