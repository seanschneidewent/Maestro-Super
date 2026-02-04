import { useState, useCallback } from 'react';
import type { WorkspacePage, PageState, BoundingBox } from '../components/maestro/PageWorkspace';
import type { AgentSelectedPage } from './useQueryManager';
import type { AgentFinding } from '../types';

// Re-export for convenience
export type { WorkspacePage };

interface UseWorkspacePagesReturn {
  /** Current workspace pages. */
  pages: WorkspacePage[];

  /**
   * Add a page to the workspace (e.g. from a `page_found` SSE event).
   * If the page already exists, it is updated in-place (state, imageUrl).
   */
  addPage: (page: {
    pageId: string;
    pageName: string;
    imageUrl: string;
    state?: PageState;
  }) => void;

  /**
   * Bulk-sync pages from the query manager's `selectedPages` array.
   * Merges new pages and updates existing ones without losing pin state.
   */
  syncFromSelectedPages: (
    selectedPages: AgentSelectedPage[],
    findings?: AgentFinding[],
  ) => void;

  /** Append bboxes to a specific page. */
  addBboxes: (pageId: string, bboxes: BoundingBox[]) => void;

  /** Replace findings for a specific page. */
  setFindings: (pageId: string, findings: AgentFinding[]) => void;

  /** Set the processing state of a specific page. */
  setPageState: (pageId: string, state: PageState) => void;

  /** Mark all pages as done. */
  markAllDone: () => void;

  /** Toggle pin state for a page. */
  togglePin: (pageId: string) => void;

  /** Clear all pages (e.g. on new conversation). */
  clear: () => void;
}

/**
 * Manages the workspace page list for the PageWorkspace component.
 *
 * This hook is the single source of truth for workspace page state.
 * It bridges between:
 *  - SSE events (page_found, annotated_image, done) via useQueryManager
 *  - The PageWorkspace / WorkspacePageCard UI components
 */
export function useWorkspacePages(): UseWorkspacePagesReturn {
  const [pages, setPages] = useState<WorkspacePage[]>([]);

  const addPage = useCallback((page: {
    pageId: string;
    pageName: string;
    imageUrl: string;
    state?: PageState;
  }) => {
    setPages((prev) => {
      const existing = prev.find((p) => p.pageId === page.pageId);
      if (existing) {
        // Update in-place, preserve pin state and accumulated bboxes/findings
        return prev.map((p) =>
          p.pageId === page.pageId
            ? {
                ...p,
                pageName: page.pageName || p.pageName,
                imageUrl: page.imageUrl || p.imageUrl,
                state: page.state ?? p.state,
              }
            : p,
        );
      }
      // New page
      return [
        ...prev,
        {
          pageId: page.pageId,
          pageName: page.pageName,
          imageUrl: page.imageUrl,
          state: page.state ?? 'queued',
          pinned: false,
          bboxes: [],
          findings: [],
        },
      ];
    });
  }, []);

  const syncFromSelectedPages = useCallback(
    (selectedPages: AgentSelectedPage[], findings?: AgentFinding[]) => {
      setPages((prev) => {
        const existingMap = new Map<string, WorkspacePage>(prev.map((p) => [p.pageId, p]));
        const newPages: WorkspacePage[] = [];

        for (const sp of selectedPages) {
          const existing = existingMap.get(sp.pageId);

          // Convert agent pointers to workspace bboxes
          const pointerBboxes: BoundingBox[] = sp.pointers.map((ptr) => ({
            x: ptr.bboxX,
            y: ptr.bboxY,
            width: ptr.bboxWidth,
            height: ptr.bboxHeight,
            label: ptr.title,
          }));

          // Filter findings for this page
          const pageFindings = (findings ?? []).filter(
            (f) => f.pageId === sp.pageId,
          );

          if (existing) {
            // Merge: preserve pin state, append new bboxes
            const existingBboxIds = new Set(
              existing.bboxes.map((b) => `${b.x}-${b.y}-${b.width}-${b.height}`),
            );
            const uniqueNewBboxes = pointerBboxes.filter(
              (b) => !existingBboxIds.has(`${b.x}-${b.y}-${b.width}-${b.height}`),
            );

            newPages.push({
              ...existing,
              pageName: sp.pageName || existing.pageName,
              imageUrl: sp.filePath || existing.imageUrl,
              bboxes: [...existing.bboxes, ...uniqueNewBboxes],
              findings:
                pageFindings.length > 0 ? pageFindings : existing.findings,
              state: existing.state === 'done' ? 'done' : 'processing',
            });
          } else {
            newPages.push({
              pageId: sp.pageId,
              pageName: sp.pageName,
              imageUrl: sp.filePath,
              state: 'processing',
              pinned: false,
              bboxes: pointerBboxes,
              findings: pageFindings,
            });
          }
        }

        // Keep any pinned pages that weren't in selectedPages
        for (const existing of prev) {
          if (
            existing.pinned &&
            !newPages.some((p) => p.pageId === existing.pageId)
          ) {
            newPages.push(existing);
          }
        }

        return newPages;
      });
    },
    [],
  );

  const addBboxes = useCallback((pageId: string, bboxes: BoundingBox[]) => {
    setPages((prev) =>
      prev.map((p) =>
        p.pageId === pageId
          ? { ...p, bboxes: [...p.bboxes, ...bboxes] }
          : p,
      ),
    );
  }, []);

  const setFindings = useCallback(
    (pageId: string, findings: AgentFinding[]) => {
      setPages((prev) =>
        prev.map((p) =>
          p.pageId === pageId ? { ...p, findings } : p,
        ),
      );
    },
    [],
  );

  const setPageState = useCallback(
    (pageId: string, state: PageState) => {
      setPages((prev) =>
        prev.map((p) =>
          p.pageId === pageId ? { ...p, state } : p,
        ),
      );
    },
    [],
  );

  const markAllDone = useCallback(() => {
    setPages((prev) => prev.map((p) => ({ ...p, state: 'done' as const })));
  }, []);

  const togglePin = useCallback((pageId: string) => {
    setPages((prev) =>
      prev.map((p) =>
        p.pageId === pageId ? { ...p, pinned: !p.pinned } : p,
      ),
    );
  }, []);

  const clear = useCallback(() => {
    setPages([]);
  }, []);

  return {
    pages,
    addPage,
    syncFromSelectedPages,
    addBboxes,
    setFindings,
    setPageState,
    markAllDone,
    togglePin,
    clear,
  };
}
