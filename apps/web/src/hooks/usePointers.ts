import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { api, PointerResponse } from '../lib/api';
import type { ContextPointer } from '../types';

/**
 * Hook for fetching and caching pointers for a specific page.
 * This is the single source of truth for pointer data in Setup Mode.
 * All components should use this hook instead of maintaining local state.
 */
export function usePagePointers(pageId: string | null) {
  return useQuery<PointerResponse[]>({
    queryKey: ['pointers', pageId],
    queryFn: () => api.pointers.list(pageId!),
    staleTime: 30_000,  // 30 seconds before considered stale
    enabled: !!pageId,  // Only fetch if pageId is provided
  });
}

/**
 * Convert API response to ContextPointer format used by components.
 */
export function toContextPointer(p: PointerResponse): ContextPointer {
  return {
    id: p.id,
    pageId: p.pageId,
    title: p.title,
    description: p.description,
    textSpans: p.textSpans,
    ocrData: p.ocrData,
    bboxX: p.bboxX,
    bboxY: p.bboxY,
    bboxWidth: p.bboxWidth,
    bboxHeight: p.bboxHeight,
    pngPath: p.pngPath,
    hasEmbedding: p.hasEmbedding,
    references: p.references,
  };
}

/**
 * Hook for converting usePagePointers result to ContextPointer[] format.
 * Use this in components that expect ContextPointer type.
 */
export function usePagePointersAsContext(pageId: string | null) {
  const query = usePagePointers(pageId);
  return {
    ...query,
    data: query.data?.map(toContextPointer) ?? [],
  };
}

// Types for create mutation
interface CreatePointerArgs {
  pageId: string;
  bounds: {
    bboxX: number;
    bboxY: number;
    bboxWidth: number;
    bboxHeight: number;
  };
  tempId: string;
  onCreated?: (pointer: PointerResponse) => void;
}

/**
 * Hook for creating a pointer with optimistic UI.
 * Shows "Generating..." immediately while API runs.
 */
export function useCreatePointer(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ pageId, bounds }: CreatePointerArgs) => {
      return api.pointers.create(pageId, bounds);
    },

    onMutate: async ({ pageId, bounds, tempId }) => {
      // Cancel any outgoing refetches to prevent race conditions
      await queryClient.cancelQueries({ queryKey: ['pointers', pageId] });

      // Snapshot previous value for rollback
      const previous = queryClient.getQueryData<PointerResponse[]>(['pointers', pageId]);

      // Create optimistic temp pointer
      const tempPointer: PointerResponse = {
        id: tempId,
        pageId,
        title: 'Generating...',
        description: '',
        bboxX: bounds.bboxX,
        bboxY: bounds.bboxY,
        bboxWidth: bounds.bboxWidth,
        bboxHeight: bounds.bboxHeight,
        hasEmbedding: false,
        createdAt: new Date().toISOString(),
        // Mark as generating for UI styling
        // Note: This is a custom property, PointerResponse doesn't have isGenerating
        // but we can add it and components will handle it
      } as PointerResponse & { isGenerating?: boolean };

      // Add isGenerating flag for UI
      (tempPointer as PointerResponse & { isGenerating?: boolean }).isGenerating = true;

      // Optimistically add temp pointer to cache
      queryClient.setQueryData<PointerResponse[]>(['pointers', pageId], (old = []) => [
        ...old,
        tempPointer,
      ]);

      return { previous, pageId, tempId };
    },

    onSuccess: (created, variables, context) => {
      if (!context) return;

      // Replace temp pointer with real one in cache
      queryClient.setQueryData<PointerResponse[]>(['pointers', context.pageId], (old = []) =>
        old.map(p => p.id === context.tempId ? created : p)
      );

      // Invalidate hierarchy to update pointer counts in tree/mindmap
      queryClient.invalidateQueries({ queryKey: ['hierarchy', projectId] });

      // Call success callback if provided (for auto-expand, focus, etc.)
      variables.onCreated?.(created);
    },

    onError: (error, variables, context) => {
      // Rollback to previous state on error
      if (context?.previous) {
        queryClient.setQueryData(['pointers', context.pageId], context.previous);
      }
      console.error('Failed to create pointer:', error);
    },
  });
}

// Types for delete mutation
interface DeletePointerArgs {
  pointerId: string;
  pageId: string;  // Need pageId to update correct cache
}

/**
 * Hook for deleting a pointer with optimistic UI.
 * Immediately removes from UI while API runs.
 */
export function useDeletePointer(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ pointerId }: DeletePointerArgs) => {
      return api.pointers.delete(pointerId);
    },

    onMutate: async ({ pointerId, pageId }) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['pointers', pageId] });

      // Snapshot previous value for rollback
      const previous = queryClient.getQueryData<PointerResponse[]>(['pointers', pageId]);

      // Optimistically remove pointer from cache
      queryClient.setQueryData<PointerResponse[]>(['pointers', pageId], (old = []) =>
        old.filter(p => p.id !== pointerId)
      );

      // Also optimistically update hierarchy cache
      const hierarchyPrevious = queryClient.getQueryData(['hierarchy', projectId]);

      return { previous, pageId, hierarchyPrevious };
    },

    onSuccess: () => {
      // Invalidate hierarchy to update pointer counts
      queryClient.invalidateQueries({ queryKey: ['hierarchy', projectId] });
    },

    onError: (error, variables, context) => {
      // Rollback on error
      if (context?.previous) {
        queryClient.setQueryData(['pointers', context.pageId], context.previous);
      }
      if (context?.hierarchyPrevious) {
        queryClient.setQueryData(['hierarchy', projectId], context.hierarchyPrevious);
      }
      console.error('Failed to delete pointer:', error);
    },
  });
}

/**
 * Hook to invalidate pointer cache for a specific page.
 * Call this when external changes might have modified pointers.
 */
export function useInvalidatePointers() {
  const queryClient = useQueryClient();

  return (pageId: string) => {
    queryClient.invalidateQueries({ queryKey: ['pointers', pageId] });
  };
}

/**
 * Hook to invalidate all pointer caches.
 * Use sparingly - prefer invalidating specific pages.
 */
export function useInvalidateAllPointers() {
  const queryClient = useQueryClient();

  return () => {
    queryClient.invalidateQueries({ queryKey: ['pointers'] });
  };
}
