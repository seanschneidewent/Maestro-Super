import React from 'react';
import { useAgentToast } from '../../contexts/AgentToastContext';
import { AgentWorkingToast } from './AgentWorkingToast';

interface AgentToastStackProps {
  onNavigate: (queryId: string) => void;
  shouldShow?: boolean;
}

export const AgentToastStack: React.FC<AgentToastStackProps> = ({ onNavigate, shouldShow = true }) => {
  const { toasts, dismissToast } = useAgentToast();

  if (toasts.length === 0 || !shouldShow) {
    return null;
  }

  return (
    <div className="absolute top-[max(1rem,env(safe-area-inset-top))] left-4 z-40 flex flex-col gap-2 pointer-events-none">
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto">
          <AgentWorkingToast
            toast={toast}
            onDismiss={() => dismissToast(toast.id)}
            onNavigate={() => onNavigate(toast.queryId)}
          />
        </div>
      ))}
    </div>
  );
};
