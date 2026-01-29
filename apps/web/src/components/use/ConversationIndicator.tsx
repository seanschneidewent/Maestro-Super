import React from 'react';

interface ConversationIndicatorProps {
  conversationTitle: string | null;
  isVisible: boolean;
}

/**
 * Shows "In conversation: [title]" indicator when user is bound to a conversation
 * and agent is idle (no toasts showing, not streaming).
 *
 * Positioned in the same area as AgentToastStack (top-left).
 */
export const ConversationIndicator: React.FC<ConversationIndicatorProps> = ({
  conversationTitle,
  isVisible,
}) => {
  if (!isVisible) {
    return null;
  }

  const displayText = conversationTitle
    ? `In conversation: ${conversationTitle}`
    : 'In conversation';

  return (
    <div className="absolute top-[max(1rem,env(safe-area-inset-top))] left-4 z-40 pointer-events-none">
      <div className="px-3 py-1.5 rounded-full bg-white/80 backdrop-blur-sm border border-slate-200/50 shadow-sm">
        <span className="text-xs text-slate-500 italic">{displayText}</span>
      </div>
    </div>
  );
};
