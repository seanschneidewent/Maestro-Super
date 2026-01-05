import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import type { ProjectHierarchy } from '../types';

/**
 * Hook for fetching and caching project hierarchy data.
 * Used by ContextMindMap and PlansPanel components.
 */
export function useHierarchy(projectId: string) {
  return useQuery<ProjectHierarchy>({
    queryKey: ['hierarchy', projectId],
    queryFn: () => api.projects.getHierarchy(projectId),
    staleTime: 60 * 1000,  // 1 minute before considered stale
    enabled: !!projectId,  // Only fetch if projectId is provided
  });
}

/**
 * Hook to invalidate hierarchy cache when data changes.
 * Call this after creating/deleting pointers, pages, or disciplines.
 */
export function useInvalidateHierarchy() {
  const queryClient = useQueryClient();

  return (projectId: string) => {
    queryClient.invalidateQueries({ queryKey: ['hierarchy', projectId] });
  };
}

/**
 * Hook for optimistic deletion of a pointer from the hierarchy cache.
 * Immediately removes the pointer from cache for instant UI feedback.
 * Returns a rollback function to restore the cache on API failure.
 */
export function useOptimisticDeletePointer() {
  const queryClient = useQueryClient();

  return (projectId: string, pointerId: string): (() => void) => {
    const previousData = queryClient.getQueryData<ProjectHierarchy>(['hierarchy', projectId]);

    if (previousData) {
      // Immediately remove pointer from cache
      const updatedData: ProjectHierarchy = {
        ...previousData,
        disciplines: previousData.disciplines.map(discipline => ({
          ...discipline,
          pages: discipline.pages.map(page => ({
            ...page,
            pointerCount: page.pointers.some(p => p.id === pointerId)
              ? page.pointerCount - 1
              : page.pointerCount,
            pointers: page.pointers.filter(p => p.id !== pointerId),
          })),
        })),
      };
      queryClient.setQueryData(['hierarchy', projectId], updatedData);
    }

    // Return rollback function
    return () => {
      if (previousData) {
        queryClient.setQueryData(['hierarchy', projectId], previousData);
      }
    };
  };
}

/**
 * Hook to prefetch hierarchy data (useful for navigation optimization).
 */
export function usePrefetchHierarchy() {
  const queryClient = useQueryClient();

  return (projectId: string) => {
    queryClient.prefetchQuery({
      queryKey: ['hierarchy', projectId],
      queryFn: () => api.projects.getHierarchy(projectId),
      staleTime: 60 * 1000,
    });
  };
}
