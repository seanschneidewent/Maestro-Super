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
