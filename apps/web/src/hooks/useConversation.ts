import { useCallback, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ConversationResponse } from '../lib/api';

/**
 * Hook for managing the current conversation.
 *
 * Conversations group related queries together and enable features like:
 * - Query history within a conversation
 * - "New conversation" via clearConversation
 * - Restoring previous conversations
 */
export function useConversation(projectId: string | undefined) {
  const queryClient = useQueryClient();

  // Query for the current conversation (most recent for this project)
  const {
    data: conversations,
    isLoading: isLoadingConversations,
  } = useQuery({
    queryKey: ['conversations', projectId],
    queryFn: () => api.conversations.list(projectId!),
    enabled: !!projectId,
    staleTime: 60 * 1000, // 1 minute
  });

  // The current conversation is the most recent one (first in list, ordered by updated_at desc)
  const currentConversation = conversations?.[0] ?? null;

  // Mutation to create a new conversation
  const createConversationMutation = useMutation({
    mutationFn: (projId: string) => api.conversations.create(projId),
    onSuccess: (newConversation) => {
      // Add the new conversation to the cache at the front of the list
      queryClient.setQueryData<ConversationResponse[]>(
        ['conversations', projectId],
        (old) => [newConversation, ...(old ?? [])]
      );
    },
  });

  // Create conversation function
  const createConversation = useCallback(async () => {
    if (!projectId) {
      console.warn('Cannot create conversation: no projectId');
      return null;
    }
    return createConversationMutation.mutateAsync(projectId);
  }, [projectId, createConversationMutation]);

  // Clear conversation (create new one) - called when "+" is tapped
  const clearConversation = useCallback(async () => {
    if (!projectId) {
      console.warn('Cannot clear conversation: no projectId');
      return null;
    }
    return createConversationMutation.mutateAsync(projectId);
  }, [projectId, createConversationMutation]);

  // Auto-create conversation on load if none exists
  useEffect(() => {
    if (
      projectId &&
      !isLoadingConversations &&
      conversations !== undefined &&
      conversations.length === 0 &&
      !createConversationMutation.isPending
    ) {
      createConversation();
    }
  }, [projectId, isLoadingConversations, conversations, createConversation, createConversationMutation.isPending]);

  return {
    currentConversation,
    conversations,
    isLoading: isLoadingConversations,
    isCreating: createConversationMutation.isPending,
    createConversation,
    clearConversation,
  };
}

/**
 * Hook to get a conversation with all its queries.
 */
export function useConversationWithQueries(conversationId: string | undefined) {
  return useQuery({
    queryKey: ['conversation', conversationId],
    queryFn: () => api.conversations.get(conversationId!),
    enabled: !!conversationId,
    staleTime: 30 * 1000, // 30 seconds
  });
}

/**
 * Hook to invalidate conversation cache when data changes.
 */
export function useInvalidateConversations() {
  const queryClient = useQueryClient();

  return useCallback((projectId: string) => {
    queryClient.invalidateQueries({ queryKey: ['conversations', projectId] });
  }, [queryClient]);
}
