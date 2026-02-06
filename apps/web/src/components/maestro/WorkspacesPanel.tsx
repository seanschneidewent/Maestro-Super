import { useMemo, useState } from 'react';
import { X, Layers, RefreshCw, Plus, Loader2, Pin, CheckCircle2 } from 'lucide-react';
import type { V3SessionSummary, V3WorkspaceState } from '../../types';
import type { AgentSelectedPage } from '../../hooks/useQueryManager';

interface WorkspacesPanelProps {
  projectId: string;
  isOpen: boolean;
  onClose: () => void;
  workspaces: V3SessionSummary[];
  activeSessionId: string | null;
  workspaceState: V3WorkspaceState | null;
  workspacePages: AgentSelectedPage[];
  isLoading?: boolean;
  error?: string | null;
  onRefresh: () => Promise<void> | void;
  onCreateWorkspace: (name?: string) => Promise<string | null>;
  onSwitchWorkspace: (sessionId: string) => Promise<boolean>;
}

function formatTimeAgo(value?: string | null): string {
  if (!value) return 'Unknown activity';
  const date = new Date(value);
  const now = Date.now();
  const delta = now - date.getTime();
  const minutes = Math.floor(delta / 60000);
  const hours = Math.floor(delta / 3600000);
  const days = Math.floor(delta / 86400000);

  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString();
}

export function WorkspacesPanel({
  projectId,
  isOpen,
  onClose,
  workspaces,
  activeSessionId,
  workspaceState,
  workspacePages,
  isLoading = false,
  error = null,
  onRefresh,
  onCreateWorkspace,
  onSwitchWorkspace,
}: WorkspacesPanelProps) {
  const [newWorkspaceName, setNewWorkspaceName] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [switchingSessionId, setSwitchingSessionId] = useState<string | null>(null);

  const pageNameById = useMemo(() => {
    return new Map(workspacePages.map((page) => [page.pageId, page.pageName]));
  }, [workspacePages]);

  if (!isOpen) return null;

  return (
    <div className="w-96 h-full bg-white/95 backdrop-blur-md border-l border-slate-200/50 flex flex-col z-20 shadow-lg">
      <div className="flex items-center justify-between px-4 py-3 pt-12 border-b border-slate-200/50">
        <div>
          <h2 className="text-lg font-medium text-slate-800">Workspaces</h2>
          <p className="text-xs text-slate-500 truncate">Project {projectId}</p>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded-lg hover:bg-slate-100 transition-colors"
          title="Close workspaces panel"
        >
          <X size={18} className="text-slate-500" />
        </button>
      </div>

      <div className="p-3 border-b border-slate-200/50 space-y-2">
        <div className="flex gap-2">
          <input
            value={newWorkspaceName}
            onChange={(event) => setNewWorkspaceName(event.target.value)}
            placeholder={`Workspace ${workspaces.length + 1}`}
            className="flex-1 h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-cyan-200"
          />
          <button
            onClick={async () => {
              if (isCreating) return;
              setIsCreating(true);
              const workspaceName = newWorkspaceName.trim() || `Workspace ${workspaces.length + 1}`;
              const createdId = await onCreateWorkspace(workspaceName);
              if (createdId) {
                setNewWorkspaceName('');
              }
              setIsCreating(false);
            }}
            disabled={isCreating || isLoading}
            className="h-9 px-3 rounded-lg bg-cyan-600 text-white text-sm font-medium hover:bg-cyan-700 disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center gap-1"
          >
            {isCreating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
            New
          </button>
        </div>
        <button
          onClick={() => onRefresh()}
          disabled={isLoading}
          className="h-8 w-full rounded-lg border border-slate-200 text-slate-600 text-xs font-medium hover:bg-slate-50 disabled:opacity-50 inline-flex items-center justify-center gap-1"
        >
          <RefreshCw size={12} className={isLoading ? 'animate-spin' : ''} />
          Refresh Workspaces
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {error && (
          <div className="p-3 text-sm text-red-600 bg-red-50 border-b border-red-100">{error}</div>
        )}

        {!error && workspaces.length === 0 && !isLoading && (
          <div className="p-4 text-sm text-slate-500">No workspaces yet.</div>
        )}

        <div className="divide-y divide-slate-100">
          {workspaces.map((workspace) => {
            const isActive = workspace.sessionId === activeSessionId;
            const isSwitching = switchingSessionId === workspace.sessionId;
            return (
              <button
                key={workspace.sessionId}
                disabled={isSwitching || isLoading}
                onClick={async () => {
                  if (isActive) return;
                  setSwitchingSessionId(workspace.sessionId);
                  await onSwitchWorkspace(workspace.sessionId);
                  setSwitchingSessionId(null);
                }}
                className={`w-full px-4 py-3 text-left transition-colors ${
                  isActive ? 'bg-cyan-50' : 'hover:bg-slate-50'
                } disabled:opacity-70`}
              >
                <div className="flex items-start gap-2">
                  <Layers size={15} className={isActive ? 'text-cyan-600 mt-0.5' : 'text-slate-400 mt-0.5'} />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-slate-700 truncate">
                      {workspace.workspaceName || 'Unnamed workspace'}
                    </div>
                    <div className="text-xs text-slate-500">{formatTimeAgo(workspace.lastActiveAt)}</div>
                    {workspace.lastMessagePreview && (
                      <div className="mt-1 text-xs text-slate-500 truncate">{workspace.lastMessagePreview}</div>
                    )}
                  </div>
                  {isSwitching ? (
                    <Loader2 size={14} className="text-cyan-500 animate-spin mt-1" />
                  ) : isActive ? (
                    <CheckCircle2 size={14} className="text-cyan-600 mt-1" />
                  ) : null}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="p-3 border-t border-slate-200/50 bg-slate-50/60">
        <div className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Current Workspace State</div>
        {!workspaceState ? (
          <div className="text-xs text-slate-500">No workspace selected.</div>
        ) : (
          <div className="space-y-2">
            <div className="text-xs text-slate-600">
              Pages: {workspaceState.displayedPages.length} • Pinned: {workspaceState.pinnedPages.length} • Highlights: {workspaceState.highlightedPointers.length}
            </div>
            {workspaceState.displayedPages.length > 0 ? (
              <div className="max-h-24 overflow-y-auto space-y-1">
                {workspaceState.displayedPages.map((pageId) => {
                  const isPinned = workspaceState.pinnedPages.includes(pageId);
                  return (
                    <div key={pageId} className="flex items-center gap-1 text-xs text-slate-600">
                      {isPinned ? <Pin size={11} className="text-amber-500" /> : <span className="w-[11px]" />}
                      <span className="truncate">{pageNameById.get(pageId) || pageId}</span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-xs text-slate-500">No pages currently in this workspace.</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
