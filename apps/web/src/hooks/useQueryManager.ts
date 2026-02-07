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
import { supabase } from '../lib/supabase'
import { api } from '../lib/api'
import {
  FieldResponse,
  ContextPointer,
  AgentTraceStep,
  OcrWord,
  AgentConceptResponse,
  AgentFinding,
  AnnotatedImage,
  V3SessionSummary,
  V3SessionDetails,
  V3WorkspaceState,
} from '../types'
import { transformAgentResponse, extractLatestThinking } from '../components/maestro/transformResponse'
import { useAgentToast } from '../contexts/AgentToastContext'
import type { BoundingBox } from '../components/maestro/PageWorkspace'

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

// Page with its selected pointers and highlights
export interface AgentSelectedPage {
  pageId: string
  pageName: string
  filePath: string
  disciplineId: string
  pointers: AgentSelectedPointer[]
  highlights?: OcrWord[]            // Text highlighting from agent
  imageWidth?: number               // For normalizing OCR coordinates
  imageHeight?: number
  // Brain Mode: processing status for graceful degradation
  processingStatus?: 'pending' | 'processing' | 'completed' | 'failed'
}

export interface CompletedQuery {
  queryId: string
  queryText: string
  mode: 'fast' | 'med' | 'deep'
  displayTitle: string | null
  conversationTitle: string | null
  pages: AgentSelectedPage[]
  finalAnswer: string
  annotatedImages: AnnotatedImage[]
  trace: AgentTraceStep[]
  elapsedTime: number
  conceptResponse?: AgentConceptResponse
}

export type QueryStatus = 'streaming' | 'complete' | 'error'
export type QueryMode = 'fast' | 'med' | 'deep'

export interface PageAgentState {
  pageId: string
  pageName: string
  state: 'queued' | 'processing' | 'done'
}

export interface LearningNote {
  text: string
  classification?: string
  fileUpdated?: string
}

export interface QueryState {
  id: string
  queryText: string
  mode: QueryMode
  sessionId: string | null
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
  conceptResponse?: AgentConceptResponse
  annotatedImages: AnnotatedImage[]
  // Orchestrator-specific fields
  pageAgentStates: PageAgentState[]
  evolvedResponseText: string
  evolvedResponseVersion: number
  learningNotes: LearningNote[]
  codeBboxes: Record<string, BoundingBox[]>
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
  submitQuery: (
    query: string,
    viewingPageId?: string | null,
    mode?: QueryMode
  ) => string | null

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

  // V3 workspace/session state
  sessionId: string | null
  workspaceState: V3WorkspaceState | null
  workspaces: V3SessionSummary[]
  workspacePages: AgentSelectedPage[]
  isSessionLoading: boolean
  sessionError: string | null
  createWorkspace: (name?: string) => Promise<string | null>
  switchWorkspace: (nextSessionId: string) => Promise<boolean>
  refreshWorkspaces: () => Promise<void>
}

// Internal type for tracking abort controllers
interface QueryController {
  abortController: AbortController
  timeoutId: NodeJS.Timeout
}

interface RawWorkspaceState {
  displayed_pages?: string[]
  highlighted_pointers?: string[]
  pinned_pages?: string[]
}

interface RawSessionSummary {
  session_id: string
  session_type: 'workspace' | 'telegram'
  workspace_name?: string | null
  status?: string
  last_active_at?: string | null
  last_message_preview?: string | null
}

interface RawSessionDetails extends RawSessionSummary {
  workspace_state?: RawWorkspaceState | null
}

interface RawCreateSessionResponse {
  session_id: string
  session_type: 'workspace' | 'telegram'
  workspace_name?: string | null
  workspace_state?: RawWorkspaceState | null
}

function normalizeWorkspaceState(
  state: RawWorkspaceState | null | undefined,
): V3WorkspaceState | null {
  if (!state) return null
  return {
    displayedPages: Array.isArray(state.displayed_pages) ? state.displayed_pages : [],
    highlightedPointers: Array.isArray(state.highlighted_pointers) ? state.highlighted_pointers : [],
    pinnedPages: Array.isArray(state.pinned_pages) ? state.pinned_pages : [],
  }
}

function toSessionSummary(raw: RawSessionSummary): V3SessionSummary {
  return {
    sessionId: raw.session_id,
    sessionType: raw.session_type,
    workspaceName: raw.workspace_name ?? null,
    status: raw.status,
    lastActiveAt: raw.last_active_at ?? null,
    lastMessagePreview: raw.last_message_preview ?? null,
  }
}

function toSessionDetails(raw: RawSessionDetails): V3SessionDetails {
  return {
    ...toSessionSummary(raw),
    workspaceState: normalizeWorkspaceState(raw.workspace_state),
  }
}

function cloneSelectedPages(pages: AgentSelectedPage[]): AgentSelectedPage[] {
  return pages.map((page) => ({
    ...page,
    pointers: page.pointers.map((pointer) => ({ ...pointer })),
    highlights: page.highlights ? [...page.highlights] : undefined,
  }))
}

export function useQueryManager(options: UseQueryManagerOptions): UseQueryManagerReturn {
  const { projectId, renderedPages, pageMetadata, contextPointers, onQueryComplete } = options
  const { addToast, markComplete, dismissToast } = useAgentToast()

  // State: Map of query ID -> query state
  const [queries, setQueries] = useState<Map<string, QueryState>>(new Map())
  const [activeQueryId, setActiveQueryId] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [workspaceState, setWorkspaceState] = useState<V3WorkspaceState | null>(null)
  const [workspaces, setWorkspaces] = useState<V3SessionSummary[]>([])
  const [workspacePages, setWorkspacePages] = useState<AgentSelectedPage[]>([])
  const [isSessionLoading, setIsSessionLoading] = useState<boolean>(true)
  const [sessionError, setSessionError] = useState<string | null>(null)

  // Refs for abort controllers (don't need to be in state)
  const controllersRef = useRef<Map<string, QueryController>>(new Map())
  const onQueryCompleteRef = useRef(onQueryComplete)
  onQueryCompleteRef.current = onQueryComplete

  // Cache for page data from search results
  const pageDataCacheRef = useRef<Map<string, { filePath: string; pageName: string; disciplineId: string }>>(new Map())

  const getAuthHeaders = useCallback(async () => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }

    if (import.meta.env.VITE_DEV_MODE !== 'true') {
      const { data: { session } } = await supabase.auth.getSession()
      if (session?.access_token) {
        headers.Authorization = `Bearer ${session.access_token}`
      }
    }

    return headers
  }, [])

  const fetchWorkspaceSessions = useCallback(async (): Promise<V3SessionSummary[]> => {
    const headers = await getAuthHeaders()
    const params = new URLSearchParams({
      project_id: projectId,
      session_type: 'workspace',
      status: 'active',
    })

    const response = await fetch(`${API_URL}/v3/sessions?${params.toString()}`, {
      method: 'GET',
      headers,
    })
    if (!response.ok) {
      const detail = await response.json().catch(() => ({ detail: 'Failed to load workspaces' }))
      throw new Error(detail.detail || `HTTP ${response.status}`)
    }

    const data = (await response.json()) as RawSessionSummary[]
    return data.map(toSessionSummary)
  }, [getAuthHeaders, projectId])

  const createWorkspaceSession = useCallback(async (name?: string): Promise<V3SessionDetails> => {
    const headers = await getAuthHeaders()
    const response = await fetch(`${API_URL}/v3/sessions`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        project_id: projectId,
        session_type: 'workspace',
        workspace_name: name && name.trim().length > 0 ? name.trim() : undefined,
      }),
    })

    if (!response.ok) {
      const detail = await response.json().catch(() => ({ detail: 'Failed to create workspace' }))
      throw new Error(detail.detail || `HTTP ${response.status}`)
    }

    const data = (await response.json()) as RawCreateSessionResponse
    return {
      sessionId: data.session_id,
      sessionType: data.session_type,
      workspaceName: data.workspace_name ?? null,
      status: 'active',
      workspaceState: normalizeWorkspaceState(data.workspace_state),
    }
  }, [getAuthHeaders, projectId])

  const getSessionDetails = useCallback(async (targetSessionId: string): Promise<V3SessionDetails> => {
    const headers = await getAuthHeaders()
    const response = await fetch(`${API_URL}/v3/sessions/${targetSessionId}`, {
      method: 'GET',
      headers,
    })

    if (!response.ok) {
      const detail = await response.json().catch(() => ({ detail: 'Failed to load workspace' }))
      throw new Error(detail.detail || `HTTP ${response.status}`)
    }

    const data = (await response.json()) as RawSessionDetails
    return toSessionDetails(data)
  }, [getAuthHeaders])

  const getPageMeta = useCallback(async (pageId: string) => {
    const cached = pageDataCacheRef.current.get(pageId)
    if (cached) return cached

    try {
      const page = await api.pages.get(pageId)
      const pageMeta = {
        filePath: page.pageImagePath || page.filePath || '',
        pageName: page.pageName || 'Unknown',
        disciplineId: page.disciplineId || '',
      }
      if (pageMeta.filePath) {
        pageDataCacheRef.current.set(pageId, pageMeta)
      }
      return pageMeta
    } catch (error) {
      console.warn(`Failed to resolve page ${pageId}:`, error)
      return null
    }
  }, [])

  const applyWorkspacePageAdditions = useCallback(async (
    pages: Array<{
      page_id: string
      page_name?: string
      file_path?: string
      discipline_id?: string
    }>,
    currentPages: AgentSelectedPage[],
  ): Promise<AgentSelectedPage[]> => {
    if (pages.length === 0) return currentPages

    const next = cloneSelectedPages(currentPages)
    const existingById = new Map(next.map((page) => [page.pageId, page]))

    for (const page of pages) {
      const pageId = page.page_id
      if (!pageId) continue

      let filePath = page.file_path || ''
      let pageName = page.page_name || 'Unknown'
      let disciplineId = page.discipline_id || ''

      if (!filePath || !disciplineId) {
        const resolved = await getPageMeta(pageId)
        if (resolved) {
          filePath = filePath || resolved.filePath
          pageName = page.page_name || resolved.pageName
          disciplineId = disciplineId || resolved.disciplineId
        }
      }

      const existing = existingById.get(pageId)
      if (existing) {
        existing.pageName = pageName || existing.pageName
        existing.filePath = filePath || existing.filePath
        existing.disciplineId = disciplineId || existing.disciplineId
      } else {
        const nextPage: AgentSelectedPage = {
          pageId,
          pageName: pageName || 'Unknown',
          filePath,
          disciplineId,
          pointers: [],
          highlights: [],
        }
        next.push(nextPage)
        existingById.set(pageId, nextPage)
      }

      if (filePath && disciplineId) {
        pageDataCacheRef.current.set(pageId, { filePath, pageName, disciplineId })
      }
    }

    return next
  }, [getPageMeta])

  const applyPointerHighlights = useCallback(async (
    pointers: Array<{
      pointer_id: string
      title?: string
      page_id: string
      page_name?: string
      file_path?: string
      discipline_id?: string
      bbox_x?: number
      bbox_y?: number
      bbox_width?: number
      bbox_height?: number
    }>,
    currentPages: AgentSelectedPage[],
  ): Promise<AgentSelectedPage[]> => {
    if (pointers.length === 0) return currentPages

    const next = cloneSelectedPages(currentPages)
    const pageMap = new Map(next.map((page) => [page.pageId, page]))

    for (const pointer of pointers) {
      if (!pointer.pointer_id || !pointer.page_id) continue

      let page = pageMap.get(pointer.page_id)
      if (!page) {
        const resolved = await getPageMeta(pointer.page_id)
        page = {
          pageId: pointer.page_id,
          pageName: pointer.page_name || resolved?.pageName || 'Unknown',
          filePath: pointer.file_path || resolved?.filePath || '',
          disciplineId: pointer.discipline_id || resolved?.disciplineId || '',
          pointers: [],
          highlights: [],
        }
        next.push(page)
        pageMap.set(pointer.page_id, page)
      } else {
        if (pointer.page_name && !page.pageName) {
          page.pageName = pointer.page_name
        }
        if (pointer.file_path && !page.filePath) {
          page.filePath = pointer.file_path
        }
        if (pointer.discipline_id && !page.disciplineId) {
          page.disciplineId = pointer.discipline_id
        }
      }

      if (page.filePath && page.disciplineId) {
        pageDataCacheRef.current.set(page.pageId, {
          filePath: page.filePath,
          pageName: page.pageName,
          disciplineId: page.disciplineId,
        })
      }

      const alreadyExists = page.pointers.some((existing) => existing.pointerId === pointer.pointer_id)
      if (alreadyExists) continue

      page.pointers.push({
        pointerId: pointer.pointer_id,
        title: pointer.title || '',
        bboxX: typeof pointer.bbox_x === 'number' ? pointer.bbox_x : 0,
        bboxY: typeof pointer.bbox_y === 'number' ? pointer.bbox_y : 0,
        bboxWidth: typeof pointer.bbox_width === 'number' ? pointer.bbox_width : 0,
        bboxHeight: typeof pointer.bbox_height === 'number' ? pointer.bbox_height : 0,
      })
    }

    return next
  }, [getPageMeta])

  const removeWorkspacePages = useCallback((
    pageIds: string[],
    currentPages: AgentSelectedPage[],
  ): AgentSelectedPage[] => {
    if (pageIds.length === 0) return currentPages
    const toRemove = new Set(pageIds)
    return currentPages.filter((page) => !toRemove.has(page.pageId))
  }, [])

  const hydrateWorkspacePages = useCallback(async (
    state: V3WorkspaceState | null,
  ): Promise<AgentSelectedPage[]> => {
    if (!state || state.displayedPages.length === 0) return []

    const seedPages = state.displayedPages.map((pageId) => ({ page_id: pageId }))
    let nextPages = await applyWorkspacePageAdditions(seedPages, [])

    if (state.highlightedPointers.length > 0) {
      const pointerResults = await Promise.all(
        state.highlightedPointers.map(async (pointerId) => {
          try {
            const pointer = await api.pointers.get(pointerId)
            return {
              pointer_id: pointer.id,
              title: pointer.title,
              page_id: pointer.pageId,
              bbox_x: pointer.bboxX,
              bbox_y: pointer.bboxY,
              bbox_width: pointer.bboxWidth,
              bbox_height: pointer.bboxHeight,
            }
          } catch {
            return null
          }
        }),
      )

      const validPointers = pointerResults.filter((pointer): pointer is NonNullable<typeof pointer> => pointer !== null)
      nextPages = await applyPointerHighlights(validPointers, nextPages)
    }

    return nextPages
  }, [applyPointerHighlights, applyWorkspacePageAdditions])

  const abortAllQueries = useCallback(() => {
    controllersRef.current.forEach((controller) => {
      controller.abortController.abort()
      clearTimeout(controller.timeoutId)
    })
    controllersRef.current.clear()
  }, [])

  const clearAllQueriesState = useCallback(() => {
    abortAllQueries()
    setQueries((prev) => {
      prev.forEach((query) => {
        if (query.toastId) {
          dismissToast(query.toastId)
        }
      })
      return new Map()
    })
    setActiveQueryId(null)
  }, [abortAllQueries, dismissToast])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortAllQueries()
    }
  }, [abortAllQueries])

  const refreshWorkspaces = useCallback(async () => {
    setIsSessionLoading(true)
    setSessionError(null)
    try {
      const sessions = await fetchWorkspaceSessions()
      setWorkspaces(sessions)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to refresh workspaces'
      setSessionError(message)
    } finally {
      setIsSessionLoading(false)
    }
  }, [fetchWorkspaceSessions])

  const switchWorkspace = useCallback(async (nextSessionId: string): Promise<boolean> => {
    if (!nextSessionId) return false

    setIsSessionLoading(true)
    setSessionError(null)

    try {
      const details = await getSessionDetails(nextSessionId)
      const hydratedPages = await hydrateWorkspacePages(details.workspaceState)

      clearAllQueriesState()
      setSessionId(details.sessionId)
      setWorkspaceState(details.workspaceState)
      setWorkspacePages(hydratedPages)
      setWorkspaces((prev) => {
        const existing = prev.find((session) => session.sessionId === details.sessionId)
        if (existing) return prev
        return [{
          sessionId: details.sessionId,
          sessionType: details.sessionType,
          workspaceName: details.workspaceName,
          status: details.status,
          lastActiveAt: details.lastActiveAt,
          lastMessagePreview: details.lastMessagePreview,
        }, ...prev]
      })

      return true
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to switch workspace'
      setSessionError(message)
      return false
    } finally {
      setIsSessionLoading(false)
    }
  }, [clearAllQueriesState, getSessionDetails, hydrateWorkspacePages])

  const createWorkspace = useCallback(async (name?: string): Promise<string | null> => {
    try {
      setIsSessionLoading(true)
      setSessionError(null)

      const created = await createWorkspaceSession(name)
      const summary: V3SessionSummary = {
        sessionId: created.sessionId,
        sessionType: created.sessionType,
        workspaceName: created.workspaceName,
        status: 'active',
      }
      setWorkspaces((prev) => [summary, ...prev.filter((session) => session.sessionId !== summary.sessionId)])

      const hydratedPages = await hydrateWorkspacePages(created.workspaceState)
      clearAllQueriesState()
      setSessionId(created.sessionId)
      setWorkspaceState(created.workspaceState)
      setWorkspacePages(hydratedPages)

      return created.sessionId
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to create workspace'
      setSessionError(message)
      return null
    } finally {
      setIsSessionLoading(false)
    }
  }, [clearAllQueriesState, createWorkspaceSession, hydrateWorkspacePages])

  // Initialize V3 workspace session when project changes.
  useEffect(() => {
    let cancelled = false

    const initializeSession = async () => {
      setIsSessionLoading(true)
      setSessionError(null)

      try {
        const sessions = await fetchWorkspaceSessions()
        if (cancelled) return

        setWorkspaces(sessions)

        // Always start fresh on app load/refresh.
        // Keep older active workspaces available in the panel, but don't auto-restore them.
        const defaultName = `Workspace ${sessions.length + 1}`
        const createdSessionId = await createWorkspace(defaultName)
        if (!createdSessionId) {
          throw new Error('Failed to create initial workspace')
        }
      } catch (error) {
        if (cancelled) return
        const message = error instanceof Error ? error.message : 'Failed to initialize workspace session'
        setSessionError(message)
      } finally {
        if (!cancelled) {
          setIsSessionLoading(false)
        }
      }
    }

    initializeSession()

    return () => {
      cancelled = true
    }
  }, [projectId, fetchWorkspaceSessions, createWorkspace])

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
      selectedPages: cloneSelectedPages(queryState.selectedPages),
      annotatedImages: [] as AnnotatedImage[],
      codeBboxes: {} as Record<string, BoundingBox[]>,
      lastToolResultIndex: -1,
    }
    let receivedAnyEvent = false
    let receivedTerminalEvent = false

    try {
      if (!queryState.sessionId) {
        throw new Error('No active V3 workspace session')
      }

      const headers = await getAuthHeaders()

      const res = await fetch(`${API_URL}/v3/sessions/${queryState.sessionId}/query`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          message: queryState.queryText,
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
                  if (typeof data?.type === 'string') {
                    receivedAnyEvent = true
                    if (data.type === 'done' || data.type === 'error') {
                      receivedTerminalEvent = true
                    }
                  }
                  await processEvent(queryId, data, accumulator)
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
                if (typeof data?.type === 'string') {
                  receivedAnyEvent = true
                  if (data.type === 'done' || data.type === 'error') {
                    receivedTerminalEvent = true
                  }
                }
                await processEvent(queryId, data, accumulator)
              } catch {
                console.warn('Failed to parse remaining SSE event:', jsonStr)
              }
            }
          }
        }
      }
      if (!receivedTerminalEvent) {
        const message = receivedAnyEvent
          ? 'Stream ended before completion. Please retry.'
          : 'No response events received. Please retry.'
        throw new Error(message)
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
  }, [queries, updateQuery, dismissToast, getAuthHeaders])

  // Process SSE events for a specific query
  const processEvent = useCallback(async (
    queryId: string,
    data: Record<string, unknown>,
    accumulator: {
      reasoning: string[]
      trace: AgentTraceStep[]
      selectedPages: AgentSelectedPage[]
      annotatedImages: AnnotatedImage[]
      codeBboxes: Record<string, BoundingBox[]>
      lastToolResultIndex: number
    }
  ) => {
    switch (data.type) {
      case 'thinking': {
        if (typeof data.content === 'string') {
          const panel = data.panel === 'learning' || data.panel === 'knowledge_update'
            ? data.panel
            : 'workspace_assembly'

          accumulator.trace.push({ type: 'thinking', content: data.content, panel })

          if (panel === 'workspace_assembly') {
            updateQuery(queryId, {
              trace: [...accumulator.trace],
              thinkingText: data.content,
            })
          } else {
            updateQuery(queryId, {
              trace: [...accumulator.trace],
            })
          }
        }
        break
      }

      case 'token':
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
          const toolInput = (
            (data.input as Record<string, unknown> | undefined)
            || (data.arguments as Record<string, unknown> | undefined)
            || {}
          )
          const newStep: AgentTraceStep = {
            type: 'tool_call',
            tool: data.tool,
            input: toolInput,
          }
          accumulator.trace.push(newStep)

          updateQuery(queryId, {
            trace: [...accumulator.trace],
            currentTool: data.tool,
          })

          // Cache page data from search_pages for prefetching
          if (data.tool === 'select_pages' || data.tool === 'add_pages') {
            const input = toolInput as { page_ids?: string[] }
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
            const result = data.result as
              | { pages?: Array<{ page_id: string; page_name: string; file_path?: string; discipline_id?: string }> }
              | Array<{ page_id: string; page_name: string; file_path?: string; discipline_id?: string }>
            const pages = Array.isArray(result) ? result : result?.pages
            if (pages) {
              for (const p of pages) {
                if (!p.file_path || !p.discipline_id) continue
                pageDataCacheRef.current.set(p.page_id, {
                  filePath: p.file_path,
                  pageName: p.page_name,
                  disciplineId: p.discipline_id,
                })
              }
            }
          }

          // Process page additions from legacy + V3 tool results.
          if (data.tool === 'select_pages' || data.tool === 'add_pages') {
            const result = data.result as {
              pages?: Array<{
                page_id: string
                page_name?: string
                file_path?: string
                discipline_id?: string
              }>
            }

            if (result?.pages && result.pages.length > 0) {
              const pageDataMap = new Map(result.pages.map((page) => [page.page_id, page]))
              let orderedPageIds: string[] = []

              for (let i = accumulator.trace.length - 1; i >= 0; i--) {
                const step = accumulator.trace[i]
                if (
                  step.type === 'tool_call'
                  && step.tool === data.tool
                  && Array.isArray((step.input as { page_ids?: unknown })?.page_ids)
                ) {
                  orderedPageIds = (step.input as { page_ids: string[] }).page_ids
                  break
                }
              }

              const orderedPages = (orderedPageIds.length > 0 ? orderedPageIds : result.pages.map((page) => page.page_id))
                .map((pageId) => pageDataMap.get(pageId))
                .filter((page): page is NonNullable<typeof page> => Boolean(page))

              accumulator.selectedPages = await applyWorkspacePageAdditions(orderedPages, accumulator.selectedPages)
              updateQuery(queryId, { selectedPages: [...accumulator.selectedPages] })
              setWorkspacePages(cloneSelectedPages(accumulator.selectedPages))
            }
          }

          // Process pointer highlights from legacy + V3 tool results.
          if (data.tool === 'select_pointers' || data.tool === 'highlight_pointers') {
            const result = data.result as {
              pointers?: Array<{
                pointer_id: string
                title?: string
                page_id: string
                page_name?: string
                file_path?: string
                discipline_id?: string
                bbox_x?: number
                bbox_y?: number
                bbox_width?: number
                bbox_height?: number
              }>
            }

            if (result?.pointers && result.pointers.length > 0) {
              const pointerDataMap = new Map(result.pointers.map((pointer) => [pointer.pointer_id, pointer]))
              let orderedPointerIds: string[] = []

              for (let i = accumulator.trace.length - 1; i >= 0; i--) {
                const step = accumulator.trace[i]
                if (
                  step.type === 'tool_call'
                  && step.tool === data.tool
                  && Array.isArray((step.input as { pointer_ids?: unknown })?.pointer_ids)
                ) {
                  orderedPointerIds = (step.input as { pointer_ids: string[] }).pointer_ids
                  break
                }
              }

              const orderedPointers = (orderedPointerIds.length > 0 ? orderedPointerIds : result.pointers.map((pointer) => pointer.pointer_id))
                .map((pointerId) => pointerDataMap.get(pointerId))
                .filter((pointer): pointer is NonNullable<typeof pointer> => Boolean(pointer))

              accumulator.selectedPages = await applyPointerHighlights(orderedPointers, accumulator.selectedPages)
              updateQuery(queryId, { selectedPages: [...accumulator.selectedPages] })
              setWorkspacePages(cloneSelectedPages(accumulator.selectedPages))
            }
          }

          // Handle resolve_highlights - merge highlights into existing pages
          if (data.tool === 'resolve_highlights') {
            const result = data.result as {
              highlights?: Array<{
                page_id: string
                words: OcrWord[]
              }>
            }

            if (result?.highlights && Array.isArray(result.highlights)) {
              const pageMap = new Map(accumulator.selectedPages.map(p => [p.pageId, p]))
              let hasChanges = false

              for (const highlight of result.highlights) {
                const page = pageMap.get(highlight.page_id)
                if (page && highlight.words && highlight.words.length > 0) {
                  page.highlights = highlight.words
                  hasChanges = true
                }
              }

              if (hasChanges) {
                updateQuery(queryId, { selectedPages: [...accumulator.selectedPages] })
                setWorkspacePages(cloneSelectedPages(accumulator.selectedPages))
              }
            }
          }
        }
        break
      }

      case 'workspace_update': {
        const action = typeof data.action === 'string' ? data.action : ''
        const incomingWorkspaceState = normalizeWorkspaceState(
          (data.workspace_state as RawWorkspaceState | null | undefined),
        )
        if (incomingWorkspaceState) {
          setWorkspaceState(incomingWorkspaceState)
        }

        if (action === 'add_pages') {
          const resultPages = Array.isArray(data.pages)
            ? data.pages as Array<{
              page_id: string
              page_name?: string
              file_path?: string
              discipline_id?: string
            }>
            : []

          let pagesToApply = resultPages
          if (pagesToApply.length === 0 && Array.isArray(data.page_ids)) {
            pagesToApply = (data.page_ids as unknown[])
              .filter((pageId): pageId is string => typeof pageId === 'string')
              .map((pageId) => ({ page_id: pageId }))
          }

          if (pagesToApply.length > 0) {
            accumulator.selectedPages = await applyWorkspacePageAdditions(pagesToApply, accumulator.selectedPages)
          }
        } else if (action === 'remove_pages') {
          const pageIds = Array.isArray(data.page_ids)
            ? (data.page_ids as unknown[]).filter((pageId): pageId is string => typeof pageId === 'string')
            : []
          accumulator.selectedPages = removeWorkspacePages(pageIds, accumulator.selectedPages)
        } else if (action === 'highlight_pointers') {
          const resultPointers = Array.isArray(data.pointers)
            ? data.pointers as Array<{
              pointer_id: string
              title?: string
              page_id: string
              bbox_x?: number
              bbox_y?: number
              bbox_width?: number
              bbox_height?: number
            }>
            : []

          let pointersToApply = resultPointers
          if (pointersToApply.length === 0 && Array.isArray(data.pointer_ids)) {
            const pointerIds = (data.pointer_ids as unknown[]).filter((pointerId): pointerId is string => typeof pointerId === 'string')
            const resolvedPointers = await Promise.all(
              pointerIds.map(async (pointerId) => {
                try {
                  const pointer = await api.pointers.get(pointerId)
                  return {
                    pointer_id: pointer.id,
                    title: pointer.title,
                    page_id: pointer.pageId,
                    bbox_x: pointer.bboxX,
                    bbox_y: pointer.bboxY,
                    bbox_width: pointer.bboxWidth,
                    bbox_height: pointer.bboxHeight,
                  }
                } catch {
                  return null
                }
              }),
            )
            pointersToApply = resolvedPointers.filter((pointer): pointer is NonNullable<typeof pointer> => pointer !== null)
          }

          if (pointersToApply.length > 0) {
            accumulator.selectedPages = await applyPointerHighlights(pointersToApply, accumulator.selectedPages)
          }
        }

        if (incomingWorkspaceState?.displayedPages?.length) {
          const order = incomingWorkspaceState.displayedPages
          const pageMap = new Map(accumulator.selectedPages.map((page) => [page.pageId, page]))
          const ordered = order
            .map((pageId) => pageMap.get(pageId))
            .filter((page): page is AgentSelectedPage => Boolean(page))
          const extras = accumulator.selectedPages.filter((page) => !order.includes(page.pageId))
          accumulator.selectedPages = [...ordered, ...extras]
        }

        updateQuery(queryId, { selectedPages: [...accumulator.selectedPages] })
        setWorkspacePages(cloneSelectedPages(accumulator.selectedPages))
        break
      }

      case 'code_execution': {
        if (typeof data.content === 'string') {
          accumulator.trace.push({ type: 'code_execution', content: data.content })
          updateQuery(queryId, {
            trace: [...accumulator.trace],
            thinkingText: '🔍 Running code...',
          })
        }
        break
      }

      case 'code_result': {
        if (typeof data.content === 'string') {
          accumulator.trace.push({ type: 'code_result', content: data.content })
          updateQuery(queryId, {
            trace: [...accumulator.trace],
          })
        }
        break
      }

      case 'code_bboxes': {
        const pageId = typeof data.page_id === 'string' ? data.page_id : ''
        const rawBboxes = Array.isArray(data.bboxes) ? data.bboxes : []
        if (pageId && rawBboxes.length > 0) {
          const bboxes: BoundingBox[] = rawBboxes
            .filter((bbox): bbox is { bbox: [number, number, number, number]; label?: string } => {
              if (typeof bbox !== 'object' || bbox === null) return false
              const coords = (bbox as { bbox?: unknown }).bbox
              return (
                Array.isArray(coords) &&
                coords.length === 4 &&
                coords.every((value) => typeof value === 'number' && Number.isFinite(value))
              )
            })
            .map((bbox) => ({
              x: bbox.bbox[0],
              y: bbox.bbox[1],
              width: bbox.bbox[2] - bbox.bbox[0],
              height: bbox.bbox[3] - bbox.bbox[1],
              label: typeof bbox.label === 'string' ? bbox.label : undefined,
            }))
            .filter((bbox) => bbox.width > 0 && bbox.height > 0)

          if (bboxes.length > 0) {
            if (!accumulator.codeBboxes[pageId]) {
              accumulator.codeBboxes[pageId] = []
            }
            accumulator.codeBboxes[pageId].push(...bboxes)
            updateQuery(queryId, {
              codeBboxes: { ...accumulator.codeBboxes },
            })
          }
        }
        break
      }

      case 'annotated_image': {
        const imageBase64 = data.image_base64
        const mimeType = typeof data.mime_type === 'string' ? data.mime_type : 'image/png'
        if (typeof imageBase64 === 'string' && imageBase64.length > 0) {
          accumulator.annotatedImages.push({ imageBase64, mimeType })
          updateQuery(queryId, {
            annotatedImages: [...accumulator.annotatedImages],
          })
        }
        break
      }

      case 'done': {
        const displayTitle = typeof data.displayTitle === 'string' ? data.displayTitle : null
        const conversationTitle = typeof data.conversationTitle === 'string' ? data.conversationTitle : null
        const conceptName = typeof data.conceptName === 'string' ? data.conceptName : null
        const summary = typeof data.summary === 'string' ? data.summary : null
        const gaps = Array.isArray((data as { gaps?: unknown }).gaps) ? (data as { gaps?: string[] }).gaps : []
        const rawCrossReferences = Array.isArray((data as { crossReferences?: unknown }).crossReferences)
          ? (data as { crossReferences?: Array<Record<string, unknown>> }).crossReferences
          : []
        const findingsRaw = Array.isArray((data as { findings?: unknown }).findings)
          ? (data as { findings?: Array<Record<string, unknown>> }).findings
          : []

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

        // Normalize findings and attach page names for UI
        const pageNameLookup = new Map(accumulator.selectedPages.map(p => [p.pageId, p.pageName]))
        const findings: AgentFinding[] = findingsRaw
          .map((f) => {
            const raw = f as Record<string, any>
            const pageId = String(raw.page_id || raw.pageId || '')
            return {
              category: String(raw.category || ''),
              content: String(raw.content || ''),
              pageId,
              semanticRefs: Array.isArray(raw.semantic_refs) ? raw.semantic_refs as number[] : undefined,
              bbox: Array.isArray(raw.bbox) ? raw.bbox as [number, number, number, number] : undefined,
              confidence: typeof raw.confidence === 'string' ? raw.confidence : undefined,
              sourceText: typeof raw.source_text === 'string' ? raw.source_text : undefined,
              pageName: pageNameLookup.get(pageId) || undefined,
            }
          })
          .filter((f) => f.pageId && f.content)

        const resolvePageLabel = (value: string) => pageNameLookup.get(value) || value
        const crossReferences = rawCrossReferences
          .map((ref) => {
            const raw = ref as Record<string, any>
            const fromRaw = String(raw.fromPageName || raw.from_page_name || raw.fromPage || raw.from_page || '')
            const toRaw = String(raw.toPageName || raw.to_page_name || raw.toPage || raw.to_page || '')
            return {
              fromPage: resolvePageLabel(fromRaw),
              toPage: resolvePageLabel(toRaw),
              relationship: String(raw.relationship || ''),
            }
          })
          .filter((ref) => ref.fromPage && ref.toPage && ref.relationship)

        const conceptResponse: AgentConceptResponse = {
          conceptName,
          summary,
          findings,
          crossReferences,
          gaps,
        }
        const hasStructuredContent = findings.length > 0
          || crossReferences.length > 0
          || gaps.length > 0
          || Boolean(summary)
          || Boolean(conceptName)

        if (!extractedAnswer.trim() && !hasStructuredContent) {
          extractedAnswer = 'I could not generate a response this turn. Please try again.'
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
              mode: query.mode,
              displayTitle,
              conversationTitle,
              pages: [...accumulator.selectedPages],
              finalAnswer: extractedAnswer,
              annotatedImages: [...accumulator.annotatedImages],
              trace: [...accumulator.trace],
              elapsedTime: Date.now() - query.startTime,
              conceptResponse,
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
            annotatedImages: [...accumulator.annotatedImages],
            currentTool: null,
            response: fieldResponse,
            conceptResponse,
          })
          return newMap
        })
        setWorkspacePages(cloneSelectedPages(accumulator.selectedPages))
        break
      }

      case 'page_state': {
        const pageId = typeof data.page_id === 'string' ? data.page_id : ''
        const pageName = typeof data.page_name === 'string' ? data.page_name : pageId
        const pageState = typeof data.state === 'string' ? data.state as 'queued' | 'processing' | 'done' : 'queued'

        if (pageId) {
          setQueries((prev) => {
            const query = prev.get(queryId)
            if (!query) return prev

            const existing = query.pageAgentStates.findIndex(p => p.pageId === pageId)
            const newStates = [...query.pageAgentStates]
            if (existing >= 0) {
              newStates[existing] = { pageId, pageName: pageName || newStates[existing].pageName, state: pageState }
            } else {
              newStates.push({ pageId, pageName, state: pageState })
            }

            const newMap = new Map(prev)
            newMap.set(queryId, { ...query, pageAgentStates: newStates })
            return newMap
          })
        }
        break
      }

      case 'response_update': {
        const text = typeof data.text === 'string' ? data.text : ''
        const version = typeof data.version === 'number' ? data.version : 0

        updateQuery(queryId, {
          evolvedResponseText: text,
          evolvedResponseVersion: version,
        })
        break
      }

      case 'learning': {
        const text = typeof data.text === 'string' ? data.text : ''
        const classification = typeof data.classification === 'string' ? data.classification : undefined
        const fileUpdated = typeof data.file_updated === 'string' ? data.file_updated : undefined

        if (text) {
          setQueries((prev) => {
            const query = prev.get(queryId)
            if (!query) return prev

            const newNotes = [...query.learningNotes, { text, classification, fileUpdated }]
            const newMap = new Map(prev)
            newMap.set(queryId, { ...query, learningNotes: newNotes })
            return newMap
          })
        }
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
  }, [
    updateQuery,
    markComplete,
    dismissToast,
    renderedPages,
    pageMetadata,
    contextPointers,
    applyWorkspacePageAdditions,
    applyPointerHighlights,
    removeWorkspacePages,
  ])

  // Submit a new query
  const submitQuery = useCallback((
    queryText: string,
    viewingPageId?: string | null,
    mode: QueryMode = 'fast'
  ): string | null => {
    if (!sessionId) {
      console.warn('No active V3 workspace session')
      setSessionError('No active workspace session. Please create or switch to a workspace.')
      return null
    }

    // Check concurrent limit
    const runningCount = Array.from(queries.values()).filter(q => q.status === 'streaming').length
    if (runningCount >= MAX_CONCURRENT_QUERIES) {
      console.warn(`Max concurrent queries (${MAX_CONCURRENT_QUERIES}) reached`)
      return null
    }

    setSessionError(null)

    // Generate IDs
    const queryId = `query-${Date.now()}-${Math.random().toString(36).slice(2)}`
    const toastId = addToast(queryText, queryId)

    // Create initial state
    const queryState: QueryState = {
        id: queryId,
        queryText,
        mode,
        sessionId,
        viewingPageId: viewingPageId ?? null,
        toastId,
        status: 'streaming',
        trace: [],
        selectedPages: cloneSelectedPages(workspacePages),
        annotatedImages: [],
        thinkingText: '',
        finalAnswer: '',
        displayTitle: null,
        conversationTitle: null,
        currentTool: null,
        error: null,
        startTime: Date.now(),
        response: null,
        conceptResponse: undefined,
        pageAgentStates: [],
        evolvedResponseText: '',
        evolvedResponseVersion: 0,
        learningNotes: [],
        codeBboxes: {},
      }

    // Add to state
    setQueries((prev) => new Map(prev).set(queryId, queryState))

    // Set as active query
    setActiveQueryId(queryId)

    // Start streaming (async, non-blocking)
    streamQuery(queryId, queryState)

    return queryId
  }, [sessionId, queries, addToast, streamQuery, workspacePages])

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
    clearAllQueriesState()
  }, [clearAllQueriesState])

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
      mode: 'fast',
      sessionId,
      viewingPageId: null,
      toastId: '',
      status: 'complete',
      trace,
      selectedPages: pages || [],
      annotatedImages: [],
      thinkingText: '',
      finalAnswer,
      displayTitle,
      conversationTitle: null,
      currentTool: null,
      error: null,
      startTime: Date.now(),
      response: null,
      pageAgentStates: [],
      evolvedResponseText: '',
      evolvedResponseVersion: 0,
      learningNotes: [],
      codeBboxes: {},
    }

    setQueries((prev) => new Map(prev).set(queryId, queryState))
    setActiveQueryId(queryId)
    setWorkspacePages(cloneSelectedPages(queryState.selectedPages))
  }, [sessionId])

  // Load pages directly
  const loadPages = useCallback((pages: AgentSelectedPage[]) => {
    if (activeQueryId) {
      updateQuery(activeQueryId, { selectedPages: pages })
    }
    setWorkspacePages(cloneSelectedPages(pages))
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
    sessionId,
    workspaceState,
    workspaces,
    workspacePages,
    isSessionLoading,
    sessionError,
    createWorkspace,
    switchWorkspace,
    refreshWorkspaces,
  }
}
