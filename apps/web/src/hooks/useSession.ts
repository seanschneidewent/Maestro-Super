import { useCallback, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, SessionResponse } from '../lib/api';

/**
 * Hook for managing the current session.
 *
 * Sessions group related queries together and enable features like:
 * - Query history within a session
 * - "New conversation" via clearSession
 * - Restoring previous sessions
 */
export function useSession(projectId: string | undefined) {
  const queryClient = useQueryClient();

  // Query for the current session (most recent for this project)
  const {
    data: sessions,
    isLoading: isLoadingSessions,
  } = useQuery({
    queryKey: ['sessions', projectId],
    queryFn: () => api.sessions.list(projectId!),
    enabled: !!projectId,
    staleTime: 60 * 1000, // 1 minute
  });

  // The current session is the most recent one (first in list, ordered by created_at desc)
  const currentSession = sessions?.[0] ?? null;

  // Mutation to create a new session
  const createSessionMutation = useMutation({
    mutationFn: (projId: string) => api.sessions.create(projId),
    onSuccess: (newSession) => {
      // Add the new session to the cache at the front of the list
      queryClient.setQueryData<SessionResponse[]>(
        ['sessions', projectId],
        (old) => [newSession, ...(old ?? [])]
      );
    },
  });

  // Create session function
  const createSession = useCallback(async () => {
    if (!projectId) {
      console.warn('Cannot create session: no projectId');
      return null;
    }
    return createSessionMutation.mutateAsync(projectId);
  }, [projectId, createSessionMutation]);

  // Clear session (create new one) - called when "+" is tapped
  const clearSession = useCallback(async () => {
    if (!projectId) {
      console.warn('Cannot clear session: no projectId');
      return null;
    }
    return createSessionMutation.mutateAsync(projectId);
  }, [projectId, createSessionMutation]);

  // Auto-create session on load if none exists
  useEffect(() => {
    if (
      projectId &&
      !isLoadingSessions &&
      sessions !== undefined &&
      sessions.length === 0 &&
      !createSessionMutation.isPending
    ) {
      createSession();
    }
  }, [projectId, isLoadingSessions, sessions, createSession, createSessionMutation.isPending]);

  return {
    currentSession,
    isLoading: isLoadingSessions,
    isCreating: createSessionMutation.isPending,
    createSession,
    clearSession,
  };
}

/**
 * Hook to get a session with all its queries.
 */
export function useSessionWithQueries(sessionId: string | undefined) {
  return useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => api.sessions.get(sessionId!),
    enabled: !!sessionId,
    staleTime: 30 * 1000, // 30 seconds
  });
}

/**
 * Hook to invalidate session cache when data changes.
 */
export function useInvalidateSessions() {
  const queryClient = useQueryClient();

  return useCallback((projectId: string) => {
    queryClient.invalidateQueries({ queryKey: ['sessions', projectId] });
  }, [queryClient]);
}
