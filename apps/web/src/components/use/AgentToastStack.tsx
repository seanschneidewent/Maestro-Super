import React from 'react';
import { useAgentToast } from '../../contexts/AgentToastContext';
import { AgentWorkingToast } from './AgentWorkingToast';

interface AgentToastStackProps {
  onNavigate: (conversationId: string) => void;
}

export const AgentToastStack: React.FC<AgentToastStackProps> = ({ onNavigate }) => {
  const { toasts, dismissToast } = useAgentToast();

  if (toasts.length === 0) {
    return null;
  }

  return (
    <div className="absolute top-4 left-4 z-40 flex flex-col gap-2 pointer-events-none">
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto">
          <AgentWorkingToast
            toast={toast}
            onDismiss={() => dismissToast(toast.id)}
            onNavigate={() => {
              if (toast.conversationId) {
                onNavigate(toast.conversationId);
              }
            }}
          />
        </div>
      ))}
    </div>
  );
};
