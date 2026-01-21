/**
 * Multi-query manager for concurrent background queries.
 *
 * Unlike useFieldStream which only supports one query at a time (aborting previous),
 * this manager tracks multiple concurrent queries, each with its own state.
 *
 * Features:
 * - Multiple queries can run simultaneously
 * - Each query has its own trace, pages, answer, and status
 * - Toasts are properly linked to queries
 * - An "active" query is displayed in the main UI
 * - Per-query fetch timeout (90 seconds)
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { supabase } from '../../lib/supabase'
import { FieldResponse, ContextPointer, AgentTraceStep } from '../../types'
import { transformAgentResponse, extractLatestThinking } from './transformResponse'
import { useAgentToast } from '../../contexts/AgentToastContext'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Timeout for each query (90 seconds)
const QUERY_TIMEOUT_MS = 90000

// Maximum concurrent queries
const MAX_CONCURRENT_QUERIES = 3

// Pointer data from select_pointers tool result
export interface AgentSelectedPointer {
  pointerId: string
  title: string
  bboxX: number
  bboxY: number
  bboxWidth: number
  bboxHeight: number
}

// Page with its selected pointers
export interface AgentSelectedPage {
  pageId: string
  pageName: string
  filePath: string
  disciplineId: string
  pointers: AgentSelectedPointer[]
  // Brain Mode: processing status for graceful degradation
  processingStatus?: 'pending' | 'processing' | 'completed' | 'failed'
}

export interface CompletedQuery {
  queryId: string
  queryText: string
  displayTitle: string | null
  conversationTitle: string | null
  pages: AgentSelectedPage[]
  finalAnswer: string
  trace: AgentTraceStep[]
  elapsedTime: number
}

export type QueryStatus = 'streaming' | 'complete' | 'error'

export interface QueryState {
  id: string
  queryText: string
  conversationId: string | null
  viewingPageId: string | null
  toastId: string
  status: QueryStatus
  trace: AgentTraceStep[]
  selectedPages: AgentSelectedPage[]
  thinkingText: string
  finalAnswer: string
  displayTitle: string | null
  conversationTitle: string | null
  currentTool: string | null
  error: string | null
  startTime: number
  response: FieldResponse | null
}

interface UseQueryManagerOptions {
  projectId: string
  renderedPages: Map<string, string>
  pageMetadata: Map<string, { title: string; pageNumber: number }>
  contextPointers: Map<string, ContextPointer[]>
  onQueryComplete?: (query: CompletedQuery) => void
}

interface UseQueryManagerReturn {
  // Submit a new query (doesn't abort existing ones)
  submitQuery: (query: string, conversationId?: string, viewingPageId?: string | null) => string | null

  // The "active" query being displayed in main UI
  activeQueryId: string | null
  setActiveQueryId: (id: string | null) => void

  // Get state of a specific query
  getQueryState: (queryId: string) => QueryState | null

  // Convenience: get active query state
  activeQuery: QueryState | null

  // All queries (for debugging/display)
  queries: Map<string, QueryState>

  // Count of running queries
  runningCount: number

  // Abort a specific query
  abortQuery: (queryId: string) => void

  // Reset everything
  reset: () => void

  // Restore state for a completed query (for QueryStack navigation)
  restore: (trace: AgentTraceStep[], finalAnswer: string, displayTitle: string | null, pages?: AgentSelectedPage[]) => void

  // Load pages directly (for restoring from QueryStack)
  loadPages: (pages: AgentSelectedPage[]) => void
}

// Internal type for tracking abort controllers
interface QueryController {
  abortController: AbortController
  timeoutId: NodeJS.Timeout
}

export function useQueryManager(options: UseQueryManagerOptions): UseQueryManagerReturn {
  const { projectId, renderedPages, pageMetadata, contextPointers, onQueryComplete } = options
  const { addToast, markComplete, dismissToast } = useAgentToast()

  // State: Map of query ID -> query state
  const [queries, setQueries] = useState<Map<string, QueryState>>(new Map())
  const [activeQueryId, setActiveQueryId] = useState<string | null>(null)

  // Refs for abort controllers (don't need to be in state)
  const controllersRef = useRef<Map<string, QueryController>>(new Map())
  const onQueryCompleteRef = useRef(onQueryComplete)
  onQueryCompleteRef.current = onQueryComplete

  // Cache for page data from search results
  const pageDataCacheRef = useRef<Map<string, { filePath: string; pageName: string; disciplineId: string }>>(new Map())

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      // Abort all running queries
      controllersRef.current.forEach((controller) => {
        controller.abortController.abort()
        clearTimeout(controller.timeoutId)
      })
    }
  }, [])

  // Helper to update a specific query's state
  const updateQuery = useCallback((queryId: string, updates: Partial<QueryState>) => {
    setQueries((prev) => {
      const query = prev.get(queryId)
      if (!query) return prev
      const newMap = new Map(prev)
      newMap.set(queryId, { ...query, ...updates })
      return newMap
    })
  }, [])

  // Abort a specific query
  const abortQuery = useCallback((queryId: string) => {
    const controller = controllersRef.current.get(queryId)
    if (controller) {
      controller.abortController.abort()
      clearTimeout(controller.timeoutId)
      controllersRef.current.delete(queryId)
    }

    const query = queries.get(queryId)
    if (query?.toastId) {
      dismissToast(query.toastId)
    }

    // Remove from state
    setQueries((prev) => {
      const newMap = new Map(prev)
      newMap.delete(queryId)
      return newMap
    })

    // If this was the active query, clear active
    if (activeQueryId === queryId) {
      setActiveQueryId(null)
    }
  }, [queries, activeQueryId, dismissToast])

  // Stream a query (internal function)
  const streamQuery = useCallback(async (queryId: string, queryState: QueryState) => {
    const abortController = new AbortController()

    // Set up timeout
    const timeoutId = setTimeout(() => {
      abortController.abort()
      updateQuery(queryId, {
        status: 'error',
        error: 'Request timed out after 90 seconds',
      })
      const query = queries.get(queryId)
      if (query?.toastId) {
        dismissToast(query.toastId)
      }
    }, QUERY_TIMEOUT_MS)

    controllersRef.current.set(queryId, { abortController, timeoutId })

    // Accumulator for this query
    const accumulator = {
      reasoning: [] as string[],
      trace: [] as AgentTraceStep[],
      selectedPages: [] as AgentSelectedPage[],
      lastToolResultIndex: -1,
    }

    try {
      // Get auth token
      const { data: { session } } = await supabase.auth.getSession()

      const res = await fetch(`${API_URL}/projects/${projectId}/queries/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(session?.access_token && {
            Authorization: `Bearer ${session.access_token}`,
          }),
        },
        body: JSON.stringify({
          query: queryState.queryText,
          conversationId: queryState.conversationId,
          viewingPageId: queryState.viewingPageId,
        }),
        signal: abortController.signal,
      })

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errorData.detail || `HTTP ${res.status}`)
      }

      if (!res.body) {
        throw new Error('No response body')
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // Process complete SSE messages
        const parts = buffer.split('\n\n')
        buffer = parts.pop() || ''

        for (const part of parts) {
          if (!part.trim()) continue

          const lines = part.split('\n')
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const jsonStr = line.slice(6).trim()
              if (jsonStr) {
                try {
                  const data = JSON.parse(jsonStr)
                  processEvent(queryId, data, accumulator)
                } catch {
                  console.warn('Failed to parse SSE event:', jsonStr)
                }
              }
            }
          }
        }
      }

      // Process remaining buffer
      if (buffer.trim()) {
        const lines = buffer.split('\n')
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const jsonStr = line.slice(6).trim()
            if (jsonStr) {
              try {
                const data = JSON.parse(jsonStr)
                processEvent(queryId, data, accumulator)
              } catch {
                console.warn('Failed to parse remaining SSE event:', jsonStr)
              }
            }
          }
        }
      }

    } catch (err) {
      // Don't report abort errors
      if (err instanceof Error && err.name === 'AbortError') {
        return
      }

      const message = err instanceof Error ? err.message : 'Unknown error'
      updateQuery(queryId, {
        status: 'error',
        error: message,
      })

      const query = queries.get(queryId)
      if (query?.toastId) {
        dismissToast(query.toastId)
      }
    } finally {
      // Cleanup
      clearTimeout(timeoutId)
      controllersRef.current.delete(queryId)
    }
  }, [projectId, queries, updateQuery, dismissToast])

  // Process SSE events for a specific query
  const processEvent = useCallback((
    queryId: string,
    data: Record<string, unknown>,
    accumulator: {
      reasoning: string[]
      trace: AgentTraceStep[]
      selectedPages: AgentSelectedPage[]
      lastToolResultIndex: number
    }
  ) => {
    switch (data.type) {
      case 'text': {
        if (typeof data.content === 'string') {
          accumulator.reasoning.push(data.content)

          const lastStep = accumulator.trace[accumulator.trace.length - 1]
          if (lastStep && lastStep.type === 'reasoning') {
            lastStep.content = (lastStep.content || '') + data.content
          } else {
            accumulator.trace.push({ type: 'reasoning', content: data.content })
          }

          updateQuery(queryId, {
            trace: [...accumulator.trace],
            thinkingText: extractLatestThinking(accumulator.trace),
          })
        }
        break
      }

      case 'tool_call': {
        if (typeof data.tool === 'string') {
          const newStep: AgentTraceStep = {
            type: 'tool_call',
            tool: data.tool,
            input: data.input as Record<string, unknown>,
          }
          accumulator.trace.push(newStep)

          updateQuery(queryId, {
            trace: [...accumulator.trace],
            currentTool: data.tool,
          })

          // Cache page data from search_pages for prefetching
          if (data.tool === 'select_pages') {
            const input = data.input as { page_ids?: string[] }
            if (input?.page_ids) {
              const pagesToPrefetch: AgentSelectedPage[] = []
              for (const pageId of input.page_ids) {
                const cached = pageDataCacheRef.current.get(pageId)
                if (cached) {
                  pagesToPrefetch.push({
                    pageId,
                    pageName: cached.pageName,
                    filePath: cached.filePath,
                    disciplineId: cached.disciplineId,
                    pointers: [],
                  })
                }
              }
              if (pagesToPrefetch.length > 0) {
                accumulator.selectedPages = pagesToPrefetch
                updateQuery(queryId, { selectedPages: [...pagesToPrefetch] })
              }
            }
          }
        }
        break
      }

      case 'tool_result': {
        if (typeof data.tool === 'string') {
          const newStep: AgentTraceStep = {
            type: 'tool_result',
            tool: data.tool,
            result: data.result as Record<string, unknown>,
          }
          accumulator.trace.push(newStep)
          accumulator.lastToolResultIndex = accumulator.trace.length - 1

          updateQuery(queryId, {
            trace: [...accumulator.trace],
          })

          // Cache page data from search_pages
          if (data.tool === 'search_pages') {
            const result = data.result as { pages?: Array<{ page_id: string; page_name: string; file_path: string; discipline_id: string }> }
            if (result?.pages) {
              for (const p of result.pages) {
                pageDataCacheRef.current.set(p.page_id, {
                  filePath: p.file_path,
                  pageName: p.page_name,
                  disciplineId: p.discipline_id,
                })
              }
            }
          }

          // Process select_pages results
          if (data.tool === 'select_pages') {
            const result = data.result as {
              pages?: Array<{
                page_id: string
                page_name: string
                file_path: string
                discipline_id: string
              }>
            }

            if (result?.pages) {
              // Find ordered page IDs from the tool_call
              let orderedPageIds: string[] | null = null
              for (let i = accumulator.trace.length - 1; i >= 0; i--) {
                const step = accumulator.trace[i]
                if (step.type === 'tool_call' && step.tool === 'select_pages') {
                  const input = step.input as { page_ids?: string[] }
                  orderedPageIds = input?.page_ids || null
                  break
                }
              }

              const pageDataMap = new Map(result.pages.map(p => [p.page_id, p]))
              const pageOrder = orderedPageIds || result.pages.map(p => p.page_id)
              const newPages: AgentSelectedPage[] = []

              for (const pageId of pageOrder) {
                const p = pageDataMap.get(pageId)
                if (p) {
                  newPages.push({
                    pageId: p.page_id,
                    pageName: p.page_name || 'Unknown',
                    filePath: p.file_path,
                    disciplineId: p.discipline_id || '',
                    pointers: [],
                  })
                }
              }

              // Merge with existing
              const existingIds = new Set(accumulator.selectedPages.map(p => p.pageId))
              const uniqueNew = newPages.filter(p => !existingIds.has(p.pageId))
              if (uniqueNew.length > 0) {
                accumulator.selectedPages = [...accumulator.selectedPages, ...uniqueNew]
                updateQuery(queryId, { selectedPages: [...accumulator.selectedPages] })
              }
            }
          }

          // Process select_pointers results
          if (data.tool === 'select_pointers') {
            const result = data.result as {
              pointers?: Array<{
                pointer_id: string
                title: string
                page_id: string
                page_name: string
                file_path: string
                discipline_id: string
                bbox_x: number
                bbox_y: number
                bbox_width: number
                bbox_height: number
              }>
            }

            if (result?.pointers) {
              // Find ordered pointer IDs from tool_call
              let orderedPointerIds: string[] | null = null
              for (let i = accumulator.trace.length - 1; i >= 0; i--) {
                const step = accumulator.trace[i]
                if (step.type === 'tool_call' && step.tool === 'select_pointers') {
                  const input = step.input as { pointer_ids?: string[] }
                  orderedPointerIds = input?.pointer_ids || null
                  break
                }
              }

              const pointerDataMap = new Map(result.pointers.map(p => [p.pointer_id, p]))
              const pointerOrder = orderedPointerIds || result.pointers.map(p => p.pointer_id)

              // Group by page
              const pageMap = new Map<string, AgentSelectedPage>()
              const pageOrder: string[] = []

              for (const pointerId of pointerOrder) {
                const p = pointerDataMap.get(pointerId)
                if (!p) continue

                let page = pageMap.get(p.page_id)
                if (!page) {
                  page = {
                    pageId: p.page_id,
                    pageName: p.page_name || 'Unknown',
                    filePath: p.file_path,
                    disciplineId: p.discipline_id || '',
                    pointers: [],
                  }
                  pageMap.set(p.page_id, page)
                  pageOrder.push(p.page_id)
                }

                page.pointers.push({
                  pointerId: p.pointer_id,
                  title: p.title,
                  bboxX: p.bbox_x,
                  bboxY: p.bbox_y,
                  bboxWidth: p.bbox_width,
                  bboxHeight: p.bbox_height,
                })
              }

              // Merge pointers into existing pages or add new
              const existingPageMap = new Map(accumulator.selectedPages.map(p => [p.pageId, p]))
              let hasChanges = false

              for (const pageId of pageOrder) {
                const newPageData = pageMap.get(pageId)!
                const existingPage = existingPageMap.get(pageId)

                if (existingPage) {
                  const existingPointerIds = new Set(existingPage.pointers.map(p => p.pointerId))
                  for (const pointer of newPageData.pointers) {
                    if (!existingPointerIds.has(pointer.pointerId)) {
                      existingPage.pointers.push(pointer)
                      hasChanges = true
                    }
                  }
                } else {
                  accumulator.selectedPages.push(newPageData)
                  existingPageMap.set(pageId, newPageData)
                  hasChanges = true
                }
              }

              if (hasChanges) {
                updateQuery(queryId, { selectedPages: [...accumulator.selectedPages] })
              }
            }
          }
        }
        break
      }

      case 'done': {
        const displayTitle = typeof data.displayTitle === 'string' ? data.displayTitle : null
        const conversationTitle = typeof data.conversationTitle === 'string' ? data.conversationTitle : null

        // Extract final answer
        let extractedAnswer = ''
        let lastToolResultIndex = -1
        for (let i = accumulator.trace.length - 1; i >= 0; i--) {
          if (accumulator.trace[i].type === 'tool_result') {
            lastToolResultIndex = i
            break
          }
        }

        const answerParts: string[] = []
        for (let i = lastToolResultIndex + 1; i < accumulator.trace.length; i++) {
          if (accumulator.trace[i].type === 'reasoning' && accumulator.trace[i].content) {
            answerParts.push(accumulator.trace[i].content!)
          }
        }
        extractedAnswer = answerParts.join('')

        if (lastToolResultIndex === -1) {
          extractedAnswer = accumulator.reasoning.join('')
        }

        // Get the query state to access other data
        setQueries((prev) => {
          const query = prev.get(queryId)
          if (!query) return prev

          // Create FieldResponse
          const fieldResponse = transformAgentResponse(
            {
              id: `msg-${query.startTime}`,
              role: 'agent',
              timestamp: new Date(query.startTime),
              reasoning: accumulator.reasoning,
              finalAnswer: extractedAnswer,
              displayTitle,
              trace: accumulator.trace,
              pagesVisited: [],
              isComplete: true,
            },
            renderedPages,
            pageMetadata,
            contextPointers,
            query.queryText
          )

          // Notify completion
          if (onQueryCompleteRef.current) {
            onQueryCompleteRef.current({
              queryId,
              queryText: query.queryText,
              displayTitle,
              conversationTitle,
              pages: [...accumulator.selectedPages],
              finalAnswer: extractedAnswer,
              trace: [...accumulator.trace],
              elapsedTime: Date.now() - query.startTime,
            })
          }

          // Mark toast complete
          if (query.toastId) {
            markComplete(query.toastId)
          }

          const newMap = new Map(prev)
          newMap.set(queryId, {
            ...query,
            status: 'complete',
            displayTitle,
            conversationTitle,
            finalAnswer: extractedAnswer,
            trace: [...accumulator.trace],
            selectedPages: [...accumulator.selectedPages],
            currentTool: null,
            response: fieldResponse,
          })
          return newMap
        })
        break
      }

      case 'error': {
        const message = typeof data.message === 'string' ? data.message : 'An error occurred'

        setQueries((prev) => {
          const query = prev.get(queryId)
          if (!query) return prev

          // Dismiss toast on error
          if (query.toastId) {
            dismissToast(query.toastId)
          }

          const newMap = new Map(prev)
          newMap.set(queryId, {
            ...query,
            status: 'error',
            error: message,
            currentTool: null,
          })
          return newMap
        })
        break
      }
    }
  }, [updateQuery, markComplete, dismissToast, renderedPages, pageMetadata, contextPointers])

  // Submit a new query
  const submitQuery = useCallback((
    queryText: string,
    conversationId?: string,
    viewingPageId?: string | null
  ): string | null => {
    // Check concurrent limit
    const runningCount = Array.from(queries.values()).filter(q => q.status === 'streaming').length
    if (runningCount >= MAX_CONCURRENT_QUERIES) {
      console.warn(`Max concurrent queries (${MAX_CONCURRENT_QUERIES}) reached`)
      return null
    }

    // Generate IDs
    const queryId = `query-${Date.now()}-${Math.random().toString(36).slice(2)}`
    const toastId = addToast(queryText, conversationId ?? null)

    // Create initial state
    const queryState: QueryState = {
      id: queryId,
      queryText,
      conversationId: conversationId ?? null,
      viewingPageId: viewingPageId ?? null,
      toastId,
      status: 'streaming',
      trace: [],
      selectedPages: [],
      thinkingText: '',
      finalAnswer: '',
      displayTitle: null,
      conversationTitle: null,
      currentTool: null,
      error: null,
      startTime: Date.now(),
      response: null,
    }

    // Add to state
    setQueries((prev) => new Map(prev).set(queryId, queryState))

    // Set as active query
    setActiveQueryId(queryId)

    // Start streaming (async, non-blocking)
    streamQuery(queryId, queryState)

    return queryId
  }, [queries, addToast, streamQuery])

  // Get state of a specific query
  const getQueryState = useCallback((queryId: string): QueryState | null => {
    return queries.get(queryId) ?? null
  }, [queries])

  // Active query state
  const activeQuery = activeQueryId ? queries.get(activeQueryId) ?? null : null

  // Running count
  const runningCount = Array.from(queries.values()).filter(q => q.status === 'streaming').length

  // Reset everything
  const reset = useCallback(() => {
    // Abort all running queries
    controllersRef.current.forEach((controller) => {
      controller.abortController.abort()
      clearTimeout(controller.timeoutId)
    })
    controllersRef.current.clear()

    // Dismiss all toasts
    queries.forEach((query) => {
      if (query.toastId) {
        dismissToast(query.toastId)
      }
    })

    setQueries(new Map())
    setActiveQueryId(null)
    pageDataCacheRef.current.clear()
  }, [queries, dismissToast])

  // Restore state for a completed query (for QueryStack navigation)
  const restore = useCallback((
    trace: AgentTraceStep[],
    finalAnswer: string,
    displayTitle: string | null,
    pages?: AgentSelectedPage[]
  ) => {
    // Create a "restored" query state
    const queryId = `restored-${Date.now()}`
    const queryState: QueryState = {
      id: queryId,
      queryText: '',
      conversationId: null,
      viewingPageId: null,
      toastId: '',
      status: 'complete',
      trace,
      selectedPages: pages || [],
      thinkingText: '',
      finalAnswer,
      displayTitle,
      conversationTitle: null,
      currentTool: null,
      error: null,
      startTime: Date.now(),
      response: null,
    }

    setQueries((prev) => new Map(prev).set(queryId, queryState))
    setActiveQueryId(queryId)
  }, [])

  // Load pages directly
  const loadPages = useCallback((pages: AgentSelectedPage[]) => {
    if (activeQueryId) {
      updateQuery(activeQueryId, { selectedPages: pages })
    }
  }, [activeQueryId, updateQuery])

  return {
    submitQuery,
    activeQueryId,
    setActiveQueryId,
    getQueryState,
    activeQuery,
    queries,
    runningCount,
    abortQuery,
    reset,
    restore,
    loadPages,
  }
}
