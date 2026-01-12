import { useCallback, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ConversationResponse } from '../lib/api';

/**
 * Hook for managing conversation state with explicit binding.
 *
 * Key concepts:
 * - `activeConversationId`: The conversation the user is currently bound to (null = ready for new)
 * - `activeConversation`: The full conversation object if bound, null otherwise
 * - Fresh load starts with null binding (welcome state)
 * - First query creates a new conversation and binds to it
 * - Plus button clears binding (returns to null/welcome state)
 * - History restore binds to the selected conversation
 */
export function useConversation(projectId: string | undefined) {
  const queryClient = useQueryClient();

  // Explicit binding state: null means "ready for new conversation" (welcome state)
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);

  // Query for all conversations (for history panel, etc.)
  const {
    data: conversations,
    isLoading: isLoadingConversations,
  } = useQuery({
    queryKey: ['conversations', projectId],
    queryFn: () => api.conversations.list(projectId!),
    enabled: !!projectId,
    staleTime: 60 * 1000, // 1 minute
  });

  // Derive the active conversation from the binding
  const activeConversation = activeConversationId
    ? (conversations?.find(c => c.id === activeConversationId) ?? null)
    : null;

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

  // Bind to a specific conversation (used when restoring from history)
  const bindToConversation = useCallback((conversationId: string) => {
    setActiveConversationId(conversationId);
  }, []);

  // Start a new conversation: clears binding to null state (welcome screen)
  // Does NOT create a conversation - that happens on first query
  const startNewConversation = useCallback(() => {
    setActiveConversationId(null);
  }, []);

  // Create a new conversation AND bind to it (used on first query)
  const createAndBindConversation = useCallback(async () => {
    if (!projectId) {
      console.warn('Cannot create conversation: no projectId');
      return null;
    }
    const newConversation = await createConversationMutation.mutateAsync(projectId);
    setActiveConversationId(newConversation.id);
    return newConversation;
  }, [projectId, createConversationMutation]);

  return {
    // State
    activeConversationId,
    activeConversation,
    conversations,
    isLoading: isLoadingConversations,
    isCreating: createConversationMutation.isPending,

    // Actions
    bindToConversation,
    startNewConversation,
    createAndBindConversation,
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
