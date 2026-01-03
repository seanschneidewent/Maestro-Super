import React from 'react';
import { List, Loader2, CheckCircle2 } from 'lucide-react';
import type { ToolCallState } from '../../types';

interface PageSearchCounterProps {
  toolCalls: ToolCallState[];
}

export const PageSearchCounter: React.FC<PageSearchCounterProps> = ({ toolCalls }) => {
  if (toolCalls.length === 0) return null;

  const isPending = toolCalls.some(tc => tc.status === 'pending');
  const totalPages = toolCalls.reduce((sum, tc) => {
    if (tc.result && Array.isArray(tc.result.pages)) {
      return sum + tc.result.pages.length;
    }
    return sum;
  }, 0);

  return (
    <div className={`flex items-center gap-2.5 py-2 px-3 rounded-lg border-l-2 transition-all duration-200 ${
      isPending
        ? 'bg-cyan-50/50 border-cyan-400'
        : 'bg-slate-50 border-slate-300'
    }`}>
      <div className={`flex-shrink-0 ${isPending ? 'text-cyan-500' : 'text-slate-400'}`}>
        <List size={14} />
      </div>
      <span className={`text-xs flex-1 ${isPending ? 'text-cyan-700' : 'text-slate-600'}`}>
        {isPending ? `${totalPages} page${totalPages !== 1 ? 's' : ''} found...` : `${totalPages} page${totalPages !== 1 ? 's' : ''} found`}
      </span>
      <div className="flex-shrink-0">
        {isPending ? (
          <Loader2 size={14} className="text-cyan-500 animate-spin" />
        ) : (
          <CheckCircle2 size={14} className="text-green-500" />
        )}
      </div>
    </div>
  );
};
