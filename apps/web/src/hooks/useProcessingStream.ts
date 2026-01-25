import { useState, useEffect, useCallback, useRef } from 'react';
import { supabase } from '../lib/supabase';

export type ProcessingStatus = 'idle' | 'pending' | 'processing' | 'completed' | 'failed' | 'paused';

export interface ProcessingProgress {
  current: number;
  total: number;
}

export interface CompletedPage {
  pageId: string;
  pageName: string;
  details: Detail[];
}

export interface Detail {
  title: string;
  number: string | null;
  shows: string | null;
  materials: string[];
  dimensions: string[];
  notes: string | null;
}

interface ProcessingState {
  status: ProcessingStatus;
  jobId: string | null;
  currentPage: { id: string; name: string } | null;
  progress: ProcessingProgress;
  completedPages: Map<string, CompletedPage>;
  lastCompletedPage: CompletedPage | null;
  error: string | null;
}

const initialState: ProcessingState = {
  status: 'idle',
  jobId: null,
  currentPage: null,
  progress: { current: 0, total: 0 },
  completedPages: new Map(),
  lastCompletedPage: null,
  error: null,
};

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * Hook for connecting to the processing SSE stream.
 * Tracks real-time progress of sheet-analyzer pipeline.
 */
export function useProcessingStream(projectId: string | null) {
  const [state, setState] = useState<ProcessingState>(initialState);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Handle SSE events
  const handleEvent = useCallback((event: Record<string, unknown>) => {
    const eventType = event.type as string;

    switch (eventType) {
      case 'init':
        setState(prev => ({
          ...prev,
          status: event.status === 'completed' ? 'completed' :
                  event.status === 'failed' ? 'failed' : 'processing',
          progress: {
            current: (event.processed_pages as number) || 0,
            total: (event.total_pages as number) || 0,
          },
          currentPage: event.current_page_name ? {
            id: '',
            name: event.current_page_name as string,
          } : null,
        }));
        break;

      case 'job_started':
        setState(prev => ({
          ...prev,
          status: 'processing',
          jobId: event.job_id as string,
        }));
        break;

      case 'page_started':
        setState(prev => ({
          ...prev,
          currentPage: {
            id: event.page_id as string,
            name: event.page_name as string,
          },
          progress: {
            current: (event.current as number) - 1,
            total: event.total as number,
          },
        }));
        break;

      case 'page_completed': {
        const completedPage: CompletedPage = {
          pageId: event.page_id as string,
          pageName: event.page_name as string,
          details: (event.details as Detail[]) || [],
        };

        setState(prev => {
          const newCompletedPages = new Map(prev.completedPages);
          newCompletedPages.set(completedPage.pageId, completedPage);

          return {
            ...prev,
            progress: {
              current: event.current as number,
              total: event.total as number,
            },
            completedPages: newCompletedPages,
            lastCompletedPage: completedPage,
          };
        });
        break;
      }

      case 'page_failed':
        console.warn(`Page processing failed: ${event.page_name}`, event.error);
        setState(prev => ({
          ...prev,
          progress: {
            current: prev.progress.current,
            total: event.total as number,
          },
        }));
        break;

      case 'page_progress':
        // Intermediate progress events keep the connection alive
        // Optionally update UI with detailed progress stage info
        // Stages: ocr_tile, ocr_stitch, ocr_gemini, ai_semantic_start, ai_semantic_complete, ai_markdown_start, ai_markdown_complete
        break;

      case 'job_completed':
        setState(prev => ({
          ...prev,
          status: 'completed',
          currentPage: null,
          progress: {
            current: event.processed_pages as number,
            total: event.total_pages as number,
          },
        }));
        break;

      case 'job_failed':
        setState(prev => ({
          ...prev,
          status: 'failed',
          error: event.error as string,
          currentPage: null,
        }));
        break;

      case 'job_paused':
        setState(prev => ({
          ...prev,
          status: 'paused',
          currentPage: null,
          progress: {
            current: event.processed_pages as number,
            total: event.total_pages as number,
          },
        }));
        break;

      case 'error':
        setState(prev => ({
          ...prev,
          status: 'failed',
          error: event.message as string,
        }));
        break;
    }
  }, []);

  // Connect to SSE stream (defined before functions that use it)
  const connectToStream = useCallback(async (jobId: string) => {
    if (!projectId || eventSourceRef.current) return;

    try {
      const { data: { session } } = await supabase.auth.getSession();

      const url = `${API_URL}/projects/${projectId}/process/stream?job_id=${jobId}`;

      const response = await fetch(url, {
        headers: {
          'Accept': 'text/event-stream',
          ...(session?.access_token ? { 'Authorization': `Bearer ${session.access_token}` } : {}),
        },
      });

      if (!response.ok) {
        throw new Error('Failed to connect to processing stream');
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      const processStream = async () => {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith(':')) continue;

            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                handleEvent(data);
              } catch (parseErr) {
                console.error('Failed to parse SSE event:', parseErr);
              }
            }
          }
        }
      };

      processStream().catch(async err => {
        console.error('Stream processing error:', err);
        if (state.status === 'processing') {
          // Fetch fresh progress from server before reconnecting
          try {
            const { data: { session } } = await supabase.auth.getSession();
            const statusResponse = await fetch(`${API_URL}/projects/${projectId}/process/status`, {
              headers: session?.access_token ? { 'Authorization': `Bearer ${session.access_token}` } : {},
            });
            if (statusResponse.ok) {
              const statusData = await statusResponse.json();
              if (statusData.status === 'processing' || statusData.status === 'pending') {
                setState(prev => ({
                  ...prev,
                  progress: {
                    current: statusData.processed_pages ?? prev.progress.current,
                    total: statusData.total_pages ?? prev.progress.total,
                  },
                }));
              } else if (statusData.status === 'completed') {
                // Job finished while we were disconnected
                setState(prev => ({
                  ...prev,
                  status: 'completed',
                  progress: {
                    current: statusData.processed_pages ?? prev.progress.current,
                    total: statusData.total_pages ?? prev.progress.total,
                  },
                }));
                return; // Don't reconnect
              } else if (statusData.status === 'failed') {
                setState(prev => ({
                  ...prev,
                  status: 'failed',
                  error: statusData.error || 'Processing failed',
                }));
                return; // Don't reconnect
              }
            }
          } catch (statusErr) {
            console.error('Failed to fetch status before reconnect:', statusErr);
          }

          reconnectTimeoutRef.current = setTimeout(() => {
            connectToStream(jobId);
          }, 3000);
        }
      });

    } catch (err) {
      console.error('Failed to connect to SSE stream:', err);
      setState(prev => ({
        ...prev,
        status: 'failed',
        error: err instanceof Error ? err.message : 'Connection failed',
      }));
    }
  }, [projectId, state.status, handleEvent]);

  // Start processing job
  const startProcessing = useCallback(async () => {
    if (!projectId) return null;

    try {
      const { data: { session } } = await supabase.auth.getSession();

      const response = await fetch(`${API_URL}/projects/${projectId}/process`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(session?.access_token ? { 'Authorization': `Bearer ${session.access_token}` } : {}),
        },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to start processing' }));
        throw new Error(errorData.detail || 'Failed to start processing');
      }

      const data = await response.json();

      setState(prev => ({
        ...prev,
        status: 'pending',
        jobId: data.job_id,
        progress: { current: 0, total: data.total_pages },
        error: null,
      }));

      return data.job_id;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to start processing';
      setState(prev => ({ ...prev, status: 'failed', error: message }));
      return null;
    }
  }, [projectId]);

  // Pause processing job
  const pauseProcessing = useCallback(async () => {
    if (!projectId) return false;

    try {
      const { data: { session } } = await supabase.auth.getSession();

      const response = await fetch(`${API_URL}/projects/${projectId}/process/pause`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(session?.access_token ? { 'Authorization': `Bearer ${session.access_token}` } : {}),
        },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to pause processing' }));
        throw new Error(errorData.detail || 'Failed to pause processing');
      }

      setState(prev => ({
        ...prev,
        status: 'paused',
      }));

      return true;
    } catch (err) {
      console.error('Failed to pause processing:', err);
      return false;
    }
  }, [projectId]);

  // Resume processing job (connectToStream is now defined above)
  const resumeProcessing = useCallback(async () => {
    if (!projectId) return null;

    try {
      const { data: { session } } = await supabase.auth.getSession();

      const response = await fetch(`${API_URL}/projects/${projectId}/process/resume`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(session?.access_token ? { 'Authorization': `Bearer ${session.access_token}` } : {}),
        },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to resume processing' }));
        throw new Error(errorData.detail || 'Failed to resume processing');
      }

      const data = await response.json();

      setState(prev => ({
        ...prev,
        status: 'processing',
        jobId: data.job_id,
        progress: {
          current: data.processed_pages ?? prev.progress.current,
          total: data.total_pages ?? prev.progress.total,
        },
      }));

      // Reconnect to the stream
      await connectToStream(data.job_id);

      return data.job_id;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to resume processing';
      setState(prev => ({ ...prev, error: message }));
      return null;
    }
  }, [projectId, connectToStream]);

  // Check for active job on mount
  useEffect(() => {
    if (!projectId) return;

    const checkActiveJob = async () => {
      try {
        const { data: { session } } = await supabase.auth.getSession();

        const response = await fetch(`${API_URL}/projects/${projectId}/process/status`, {
          headers: {
            ...(session?.access_token ? { 'Authorization': `Bearer ${session.access_token}` } : {}),
          },
        });

        if (response.ok) {
          const data = await response.json();

          if (data.status === 'processing' || data.status === 'pending') {
            setState(prev => ({
              ...prev,
              status: data.status,
              jobId: data.job_id,
              progress: {
                current: data.processed_pages || 0,
                total: data.total_pages || 0,
              },
              currentPage: data.current_page_name ? {
                id: data.current_page_id || '',
                name: data.current_page_name,
              } : null,
            }));

            // Connect to stream to resume watching
            if (data.job_id) {
              connectToStream(data.job_id);
            }
          } else if (data.status === 'paused') {
            // Show paused state so user can resume
            setState(prev => ({
              ...prev,
              status: 'paused',
              jobId: data.job_id,
              progress: {
                current: data.processed_pages || 0,
                total: data.total_pages || 0,
              },
              currentPage: null,
            }));
          }
        }
      } catch (err) {
        console.error('Failed to check processing status:', err);
      }
    };

    checkActiveJob();
  }, [projectId, connectToStream]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, []);

  // Start processing and connect to stream
  const start = useCallback(async () => {
    const jobId = await startProcessing();
    if (jobId) {
      await connectToStream(jobId);
    }
    return jobId;
  }, [startProcessing, connectToStream]);

  // Reset state
  const reset = useCallback(() => {
    setState(initialState);
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, []);

  // Clear last completed notification
  const clearLastCompleted = useCallback(() => {
    setState(prev => ({ ...prev, lastCompletedPage: null }));
  }, []);

  return {
    ...state,
    isProcessing: state.status === 'processing' || state.status === 'pending',
    isComplete: state.status === 'completed',
    isPaused: state.status === 'paused',
    start,
    pause: pauseProcessing,
    resume: resumeProcessing,
    reset,
    clearLastCompleted,
    connectToStream,
  };
}
