import React, { useState, useCallback, useMemo } from 'react';
import { WorkspacePageCard, WorkspacePage, PageState, BoundingBox } from './WorkspacePageCard';
import { Layers } from 'lucide-react';

// Re-export types so consumers can import from either file
export type { PageState, BoundingBox, WorkspacePage };

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface PageWorkspaceProps {
  /** Pages to display in the workspace. */
  pages: WorkspacePage[];
  /**
   * Called when a page's pinned state is toggled.
   * The parent is responsible for updating the `pages` array.
   */
  onTogglePin?: (pageId: string) => void;
  /** Optional class name applied to the scroll container. */
  className?: string;
}

// ---------------------------------------------------------------------------
// PageWorkspace
// ---------------------------------------------------------------------------

/**
 * Vertical scrollable workspace that shows query-result pages as cards.
 *
 * Features:
 * - Pinned pages are displayed first
 * - Each card shows page name, image with bbox overlays, state badge, and pin toggle
 * - Mobile-first: single-column vertical scroll
 * - Blueprint-grid background inherited from parent layout
 */
export const PageWorkspace: React.FC<PageWorkspaceProps> = ({
  pages,
  onTogglePin,
  className,
}) => {
  // --- Sort: pinned first, then by original order -------------------------
  const sortedPages = useMemo(() => {
    const pinned = pages.filter((p) => p.pinned);
    const unpinned = pages.filter((p) => !p.pinned);
    return [...pinned, ...unpinned];
  }, [pages]);

  // --- Empty state --------------------------------------------------------
  if (sortedPages.length === 0) {
    return (
      <div
        className={`flex flex-col items-center justify-center h-full text-slate-400 gap-3 px-4 ${
          className ?? ''
        }`}
      >
        <Layers size={40} className="text-slate-300" />
        <p className="text-sm text-center">
          No pages in workspace yet.
          <br />
          Run a query to see results here.
        </p>
      </div>
    );
  }

  // --- Render -------------------------------------------------------------
  return (
    <div
      className={`flex-1 overflow-y-auto px-4 md:px-6 pt-6 pb-48 ${className ?? ''}`}
      data-workspace-scroll
    >
      {/* Stats bar */}
      <div className="flex items-center justify-between mb-4 max-w-3xl mx-auto">
        <span className="text-xs uppercase tracking-wide text-slate-500">
          Workspace · {sortedPages.length} page{sortedPages.length !== 1 ? 's' : ''}
        </span>
        {sortedPages.some((p) => p.pinned) && (
          <span className="text-xs text-cyan-600 font-medium">
            📌 {sortedPages.filter((p) => p.pinned).length} pinned
          </span>
        )}
      </div>

      {/* Page cards */}
      <div className="space-y-6 max-w-3xl mx-auto">
        {sortedPages.map((page) => (
          <WorkspacePageCard
            key={page.pageId}
            page={page}
            onTogglePin={onTogglePin}
          />
        ))}
      </div>
    </div>
  );
};
