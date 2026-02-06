import { useCallback, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, QueryResponse, V3SessionSummaryResponse, V3SessionTurnResponse } from '../lib/api';

interface WorkspaceConversation {
  id: string;
  title: string | null;
  createdAt: string;
  updatedAt: string;
}

interface WorkspaceConversationWithQueries extends WorkspaceConversation {
  queries: QueryResponse[];
}

const SESSION_QUERY_KEY = 'workspace-sessions';

function toWorkspaceConversation(session: V3SessionSummaryResponse): WorkspaceConversation {
  const timestamp = session.last_active_at ?? new Date().toISOString();
  return {
    id: session.session_id,
    title: session.workspace_name ?? null,
    createdAt: timestamp,
    updatedAt: timestamp,
  };
}

function toQueryResponse(
  sessionId: string,
  projectId: string | undefined,
  updatedAt: string,
  turn: V3SessionTurnResponse,
): QueryResponse {
  return {
    id: `${sessionId}-turn-${turn.turn_number}`,
    userId: '',
    projectId,
    conversationId: sessionId,
    queryText: turn.user,
    responseText: turn.response,
    displayTitle: turn.user.trim().slice(0, 80) || null,
    sequenceOrder: turn.turn_number,
    trace: [],
    pages: [],
    createdAt: updatedAt,
  };
}

/**
 * Hook for managing workspace session binding in Maestro Mode.
 */
export function useConversation(projectId: string | undefined) {
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);

  const {
    data: conversations,
    isLoading: isLoadingConversations,
  } = useQuery({
    queryKey: [SESSION_QUERY_KEY, projectId],
    queryFn: async () => {
      const sessions = await api.v3Sessions.list(projectId!, {
        sessionType: 'workspace',
        status: 'active',
      });
      return sessions.map(toWorkspaceConversation);
    },
    enabled: !!projectId,
    staleTime: 60 * 1000,
  });

  const activeConversation = activeConversationId
    ? (conversations?.find((conversation) => conversation.id === activeConversationId) ?? null)
    : null;

  const bindToConversation = useCallback((conversationId: string) => {
    setActiveConversationId(conversationId);
  }, []);

  const startNewConversation = useCallback(() => {
    setActiveConversationId(null);
  }, []);

  return {
    activeConversationId,
    activeConversation,
    conversations,
    isLoading: isLoadingConversations,
    bindToConversation,
    startNewConversation,
  };
}

/**
 * Hook to fetch a workspace session history mapped into query-shaped rows.
 */
export function useConversationWithQueries(conversationId: string | undefined, projectId?: string) {
  return useQuery({
    queryKey: ['workspace-session-history', conversationId, projectId],
    queryFn: async (): Promise<WorkspaceConversationWithQueries> => {
      const [session, history] = await Promise.all([
        api.v3Sessions.get(conversationId!),
        api.v3Sessions.history(conversationId!),
      ]);

      const updatedAt = session.last_active_at ?? new Date().toISOString();
      return {
        id: session.session_id,
        title: session.workspace_name ?? null,
        createdAt: updatedAt,
        updatedAt,
        queries: history.turns.map((turn) =>
          toQueryResponse(session.session_id, projectId, updatedAt, turn),
        ),
      };
    },
    enabled: !!conversationId,
    staleTime: 30 * 1000,
  });
}

/**
 * Hook to invalidate workspace session cache when data changes.
 */
export function useInvalidateConversations() {
  const queryClient = useQueryClient();

  return useCallback((projectId: string) => {
    queryClient.invalidateQueries({ queryKey: [SESSION_QUERY_KEY, projectId] });
  }, [queryClient]);
}
