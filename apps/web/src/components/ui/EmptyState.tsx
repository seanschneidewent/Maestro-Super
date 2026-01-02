import React from 'react';
import { Target, Search, FileText, FolderOpen, MessageSquare, RefreshCw } from 'lucide-react';

interface EmptyStateProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

/**
 * Generic empty state component for displaying helpful messages
 * when content areas have no data to show.
 */
export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
}) => (
  <div className="flex flex-col items-center justify-center h-full py-12 px-4 text-center">
    <div className="w-16 h-16 rounded-full bg-slate-800/50 flex items-center justify-center mb-4 text-slate-500">
      {icon}
    </div>
    <h3 className="text-lg font-medium text-slate-300 mb-2">{title}</h3>
    <p className="text-sm text-slate-500 max-w-xs mb-4">{description}</p>
    {action && (
      <button
        onClick={action.onClick}
        className="px-4 py-2 text-sm bg-cyan-600 hover:bg-cyan-500 rounded-lg text-white transition-colors"
      >
        {action.label}
      </button>
    )}
  </div>
);

/**
 * Empty state for when no pointers have been created yet
 */
export const NoPointersEmpty: React.FC<{ onAction?: () => void }> = ({ onAction }) => (
  <EmptyState
    icon={<Target size={28} />}
    title="No regions analyzed yet"
    description="Draw boxes on the plans to start analyzing specific areas and extracting information."
    action={onAction ? { label: 'Select a Page', onClick: onAction } : undefined}
  />
);

/**
 * Empty state for when a search returns no results
 */
export const NoSearchResultsEmpty: React.FC<{ query?: string; onClear?: () => void }> = ({
  query,
  onClear,
}) => (
  <EmptyState
    icon={<Search size={28} />}
    title="No matches found"
    description={
      query
        ? `No results found for "${query}". Try different search terms.`
        : 'Try different search terms or check your filters.'
    }
    action={onClear ? { label: 'Clear Search', onClick: onClear } : undefined}
  />
);

/**
 * Empty state for when no pages/files have been uploaded
 */
export const NoPagesEmpty: React.FC<{ onUpload?: () => void }> = ({ onUpload }) => (
  <EmptyState
    icon={<FileText size={28} />}
    title="No pages uploaded"
    description="Upload PDF files or images to start analyzing your construction plans."
    action={onUpload ? { label: 'Upload Files', onClick: onUpload } : undefined}
  />
);

/**
 * Empty state for when no disciplines exist in project
 */
export const NoDisciplinesEmpty: React.FC = () => (
  <EmptyState
    icon={<FolderOpen size={28} />}
    title="No disciplines yet"
    description="Upload files to see the project hierarchy organized by discipline."
  />
);

/**
 * Empty state for chat/query panel with no messages
 */
export const NoChatMessagesEmpty: React.FC = () => (
  <EmptyState
    icon={<MessageSquare size={28} />}
    title="Start a conversation"
    description="Ask questions about your plans and get AI-powered insights with references to specific details."
  />
);

/**
 * Empty state for when data failed to load
 */
export const LoadErrorEmpty: React.FC<{ onRetry?: () => void; message?: string }> = ({
  onRetry,
  message,
}) => (
  <EmptyState
    icon={<RefreshCw size={28} />}
    title="Failed to load"
    description={message || 'Something went wrong while loading the data. Please try again.'}
    action={onRetry ? { label: 'Retry', onClick: onRetry } : undefined}
  />
);
