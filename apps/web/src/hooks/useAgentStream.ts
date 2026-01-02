import { useState, useCallback, useRef } from 'react';
import { supabase } from '../lib/supabase';
import type { AgentEvent } from '../types';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface UseAgentStreamOptions {
  projectId: string;
}

interface UseAgentStreamReturn {
  sendQuery: (query: string, onEvent: (event: AgentEvent) => void) => Promise<void>;
  isStreaming: boolean;
  error: string | null;
  abort: () => void;
}

export function useAgentStream({ projectId }: UseAgentStreamOptions): UseAgentStreamReturn {
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const abort = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsStreaming(false);
    }
  }, []);

  const sendQuery = useCallback(async (
    query: string,
    onEvent: (event: AgentEvent) => void
  ) => {
    // Abort any existing stream
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    setIsStreaming(true);
    setError(null);

    // Create new abort controller
    abortControllerRef.current = new AbortController();

    try {
      // Get auth token
      const { data: { session } } = await supabase.auth.getSession();

      const response = await fetch(
        `${API_URL}/projects/${projectId}/queries/stream`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(session?.access_token && {
              'Authorization': `Bearer ${session.access_token}`,
            }),
          },
          body: JSON.stringify({ query }),
          signal: abortControllerRef.current.signal,
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      if (!response.body) {
        throw new Error('No response body');
      }

      // Read SSE stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          break;
        }

        // Decode chunk and add to buffer
        buffer += decoder.decode(value, { stream: true });

        // Process complete SSE messages (separated by double newlines)
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || ''; // Keep incomplete part in buffer

        for (const part of parts) {
          if (!part.trim()) continue;

          // Parse SSE format: "data: {...}"
          const lines = part.split('\n');
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const jsonStr = line.slice(6).trim();
              if (jsonStr) {
                try {
                  const event = JSON.parse(jsonStr) as AgentEvent;
                  onEvent(event);
                } catch (parseError) {
                  console.warn('Failed to parse SSE event:', jsonStr, parseError);
                }
              }
            }
          }
        }
      }

      // Process any remaining data in buffer
      if (buffer.trim()) {
        const lines = buffer.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const jsonStr = line.slice(6).trim();
            if (jsonStr) {
              try {
                const event = JSON.parse(jsonStr) as AgentEvent;
                onEvent(event);
              } catch (parseError) {
                console.warn('Failed to parse remaining SSE event:', jsonStr, parseError);
              }
            }
          }
        }
      }
    } catch (err) {
      // Don't report abort errors
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }

      const message = err instanceof Error ? err.message : 'Stream failed';
      setError(message);

      // Send error event to handler
      onEvent({
        type: 'error',
        message,
      });
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  }, [projectId]);

  return {
    sendQuery,
    isStreaming,
    error,
    abort,
  };
}
