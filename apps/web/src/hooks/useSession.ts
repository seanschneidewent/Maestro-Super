import { useCallback, useEffect, useRef, useState } from 'react'
import { supabase } from '../lib/supabase'
import { api } from '../lib/api'
import type { V3Event, V3WorkspaceUpdateEvent, V3ThinkingPanel, V3WorkspaceState } from '../types/v3'
import type { WorkspacePage, BoundingBox } from '../components/maestro/PageWorkspace'
import type { PageResponse, PointerResponse } from '../lib/api'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const DEFAULT_WORKSPACE_STATE: V3WorkspaceState = {
  displayed_pages: [],
  highlighted_pointers: [],
  pinned_pages: [],
}

export interface WorkspaceSessionSummary {
  session_id: string
  session_type: 'workspace' | 'telegram'
  workspace_name: string | null
  status: 'active' | 'idle' | 'closed'
  last_active_at: string | null
  last_message_preview?: string | null
}

export interface MaestroTurn {
  id: string
  turnNumber: number
  user: string
  response: string
  panels: Record<V3ThinkingPanel, string>
  toolEvents: string[]
  done: boolean
  learningStarted: boolean
  learningDone: boolean
}

interface UseSessionResult {
  activeSessionId: string | null
  activeWorkspaceName: string | null
  sessions: WorkspaceSessionSummary[]
  turns: MaestroTurn[]
  workspacePages: WorkspacePage[]
  isStreaming: boolean
  isLoadingSession: boolean
  isLoadingSessions: boolean
  refreshSessions: () => Promise<void>
  createWorkspace: (name?: string | null) => Promise<void>
  switchWorkspace: (sessionId: string) => Promise<void>
  closeWorkspace: (sessionId: string) => Promise<void>
  renameWorkspace: (sessionId: string, name: string) => Promise<void>
  sendMessage: (message: string) => Promise<void>
}

function createEmptyPanels(): Record<V3ThinkingPanel, string> {
  return {
    workspace_assembly: '',
    learning: '',
    knowledge_update: '',
  }
}

function normalizePanels(
  panels?: Partial<Record<V3ThinkingPanel, string>> | null,
): Record<V3ThinkingPanel, string> {
  return {
    workspace_assembly: panels?.workspace_assembly ?? '',
    learning: panels?.learning ?? '',
    knowledge_update: panels?.knowledge_update ?? '',
  }
}

function appendPanelText(current: string, incoming: string): string {
  if (!incoming) return current
  return current ? `${current}
${incoming}` : incoming
}

function parseTurnNumber(value: unknown, fallback: number): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const parsed = Number.parseInt(value, 10)
    if (Number.isFinite(parsed)) return parsed
  }
  return fallback
}

function buildTurnsFromMessages(messages: Array<Record<string, unknown>>): MaestroTurn[] {
  const turns: MaestroTurn[] = []
  let pendingUser: { content: string; turnNumber: number } | null = null
  let inferredTurn = 0

  for (const message of messages) {
    if (!message || typeof message !== 'object') continue
    const role = message.role
    if (role === 'user') {
      inferredTurn = parseTurnNumber(message.turn_number, inferredTurn + 1)
      pendingUser = {
        content: String(message.content ?? ''),
        turnNumber: inferredTurn,
      }
      continue
    }

    if (role !== 'assistant') continue
    if (!pendingUser) continue

    const turnNumber = parseTurnNumber(message.turn_number, pendingUser.turnNumber)
    const panels = normalizePanels(message.panels as Record<V3ThinkingPanel, string> | undefined)
    const hasLearning = panels.learning.trim().length > 0 || panels.knowledge_update.trim().length > 0

    turns.push({
      id: `turn-${turnNumber}-${turns.length}`,
      turnNumber,
      user: pendingUser.content,
      response: String(message.content ?? ''),
      panels,
      toolEvents: [],
      done: true,
      learningStarted: hasLearning,
      learningDone: hasLearning,
    })

    pendingUser = null
  }

  if (pendingUser) {
    turns.push({
      id: `turn-${pendingUser.turnNumber}-${turns.length}`,
      turnNumber: pendingUser.turnNumber,
      user: pendingUser.content,
      response: '',
      panels: createEmptyPanels(),
      toolEvents: [],
      done: false,
      learningStarted: false,
      learningDone: false,
    })
  }

  return turns
}

function buildWorkspacePages(
  pageIds: string[],
  pagesById: Map<string, PageResponse>,
  pointersByPage: Map<string, BoundingBox[]>,
  pinnedPages: Set<string>,
): WorkspacePage[] {
  return pageIds.map((pageId) => {
    const page = pagesById.get(pageId)
    const imageUrl = page?.pageImagePath || page?.filePath || ''
    return {
      pageId,
      pageName: page?.pageName || 'Unknown Page',
      imageUrl,
      state: 'done',
      pinned: pinnedPages.has(pageId),
      bboxes: pointersByPage.get(pageId) || [],
      findings: [],
    }
  })
}

function addPointerToMap(target: Map<string, BoundingBox[]>, pointer: PointerResponse) {
  const bbox: BoundingBox = {
    x: pointer.bboxX,
    y: pointer.bboxY,
    width: pointer.bboxWidth,
    height: pointer.bboxHeight,
    label: pointer.title,
  }
  const existing = target.get(pointer.pageId) ?? []
  existing.push(bbox)
  target.set(pointer.pageId, existing)
}

export function useSession(projectId: string | null): UseSessionResult {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [activeWorkspaceName, setActiveWorkspaceName] = useState<string | null>(null)
  const [sessions, setSessions] = useState<WorkspaceSessionSummary[]>([])
  const [turns, setTurns] = useState<MaestroTurn[]>([])
  const [workspacePages, setWorkspacePages] = useState<WorkspacePage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [isLoadingSession, setIsLoadingSession] = useState(false)
  const [isLoadingSessions, setIsLoadingSessions] = useState(false)
  const workspaceStateRef = useRef<V3WorkspaceState>({ ...DEFAULT_WORKSPACE_STATE })
  const activeSessionRef = useRef<string | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const loadCounterRef = useRef(0)

  const storageKey = projectId ? `maestro-v3-active-session:${projectId}` : null

  useEffect(() => {
    activeSessionRef.current = activeSessionId
  }, [activeSessionId])

  const getAuthHeaders = useCallback(async () => {
    const { data: { session } } = await supabase.auth.getSession()
    return {
      'Content-Type': 'application/json',
      ...(session?.access_token && { Authorization: `Bearer ${session.access_token}` }),
    }
  }, [])

  const refreshSessions = useCallback(async () => {
    if (!projectId) {
      setSessions([])
      return
    }

    setIsLoadingSessions(true)
    try {
      const headers = await getAuthHeaders()
      const params = new URLSearchParams({
        project_id: projectId,
        session_type: 'workspace',
        status: 'active,idle',
      })
      const res = await fetch(`${API_URL}/v3/sessions?${params.toString()}`, { headers })
      if (!res.ok) {
        throw new Error('Failed to load sessions')
      }
      const data = (await res.json()) as WorkspaceSessionSummary[]
      setSessions(data)
    } finally {
      setIsLoadingSessions(false)
    }
  }, [projectId, getAuthHeaders])

  const abortActiveStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
  }, [])

  const hydrateWorkspacePages = useCallback(async (state: V3WorkspaceState | null) => {
    if (!state) {
      setWorkspacePages([])
      return
    }

    const pageIds = state.displayed_pages ?? []
    if (pageIds.length === 0) {
      setWorkspacePages([])
      return
    }

    const pageResults = await Promise.allSettled(
      pageIds.map((pageId) => api.pages.get(pageId)),
    )

    const pagesById = new Map<string, PageResponse>()
    pageResults.forEach((result, index) => {
      if (result.status === 'fulfilled') {
        pagesById.set(pageIds[index], result.value)
      }
    })

    const pointerIds = state.highlighted_pointers ?? []
    const pointerResults = await Promise.allSettled(
      pointerIds.map((pointerId) => api.pointers.get(pointerId)),
    )

    const pointersByPage = new Map<string, BoundingBox[]>()
    pointerResults.forEach((result) => {
      if (result.status === 'fulfilled') {
        addPointerToMap(pointersByPage, result.value)
      }
    })

    const pinnedPages = new Set(state.pinned_pages ?? [])
    setWorkspacePages(buildWorkspacePages(pageIds, pagesById, pointersByPage, pinnedPages))
  }, [])

  const loadSession = useCallback(async (sessionId: string) => {
    if (!projectId) return

    abortActiveStream()
    setIsStreaming(false)
    setIsLoadingSession(true)
    setWorkspacePages([])

    const loadId = ++loadCounterRef.current

    try {
      const headers = await getAuthHeaders()
      const res = await fetch(`${API_URL}/v3/sessions/${sessionId}`, { headers })
      if (!res.ok) {
        throw new Error('Failed to load session')
      }
      const data = await res.json()
      if (loadId !== loadCounterRef.current) return

      setActiveSessionId(data.session_id)
      setActiveWorkspaceName(data.workspace_name ?? null)
      workspaceStateRef.current = data.workspace_state ?? { ...DEFAULT_WORKSPACE_STATE }
      setTurns(buildTurnsFromMessages(data.maestro_messages ?? []))
      await hydrateWorkspacePages(data.workspace_state ?? null)
      if (storageKey) {
        localStorage.setItem(storageKey, data.session_id)
      }
    } finally {
      if (loadId === loadCounterRef.current) {
        setIsLoadingSession(false)
      }
    }
  }, [projectId, getAuthHeaders, abortActiveStream, hydrateWorkspacePages, storageKey])

  const generateWorkspaceName = useCallback((requested?: string | null) => {
    const trimmed = requested?.trim() ?? ''
    if (trimmed) return trimmed

    let maxNumber = 0
    for (const session of sessions) {
      const name = session.workspace_name || ''
      const match = /^Workspace\s+(\d+)$/i.exec(name)
      if (match) {
        const value = Number.parseInt(match[1], 10)
        if (Number.isFinite(value)) {
          maxNumber = Math.max(maxNumber, value)
        }
      }
    }
    return `Workspace ${maxNumber + 1}`
  }, [sessions])

  const createWorkspace = useCallback(async (name?: string | null) => {
    if (!projectId) return

    const workspaceName = generateWorkspaceName(name)
    const headers = await getAuthHeaders()
    const res = await fetch(`${API_URL}/v3/sessions`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        project_id: projectId,
        session_type: 'workspace',
        workspace_name: workspaceName,
      }),
    })

    if (!res.ok) {
      throw new Error('Failed to create workspace')
    }

    const data = await res.json()
    await refreshSessions()
    await loadSession(data.session_id)
  }, [projectId, generateWorkspaceName, getAuthHeaders, refreshSessions, loadSession])

  const switchWorkspace = useCallback(async (sessionId: string) => {
    if (!sessionId || sessionId === activeSessionRef.current) return
    await loadSession(sessionId)
  }, [loadSession])

  const closeWorkspace = useCallback(async (sessionId: string) => {
    if (!sessionId) return

    abortActiveStream()
    const headers = await getAuthHeaders()
    const res = await fetch(`${API_URL}/v3/sessions/${sessionId}`, {
      method: 'DELETE',
      headers,
    })

    if (!res.ok) {
      throw new Error('Failed to close workspace')
    }

    if (sessionId === activeSessionRef.current) {
      setActiveSessionId(null)
      setActiveWorkspaceName(null)
      setTurns([])
      setWorkspacePages([])
      workspaceStateRef.current = { ...DEFAULT_WORKSPACE_STATE }
      if (storageKey) {
        localStorage.removeItem(storageKey)
      }
    }

    await refreshSessions()
  }, [abortActiveStream, getAuthHeaders, refreshSessions, storageKey])

  const renameWorkspace = useCallback(async (sessionId: string, name: string) => {
    if (!sessionId) return
    const trimmed = name.trim()
    if (!trimmed) return

    const headers = await getAuthHeaders()
    const res = await fetch(`${API_URL}/v3/sessions/${sessionId}`, {
      method: 'PATCH',
      headers,
      body: JSON.stringify({ workspace_name: trimmed }),
    })

    if (!res.ok) {
      throw new Error('Failed to rename workspace')
    }

    if (sessionId === activeSessionRef.current) {
      setActiveWorkspaceName(trimmed)
    }

    await refreshSessions()
  }, [getAuthHeaders, refreshSessions])

  const applyWorkspaceUpdate = useCallback((event: V3WorkspaceUpdateEvent) => {
    const nextState = event.workspace_state || workspaceStateRef.current
    workspaceStateRef.current = nextState

    setWorkspacePages((prev) => {
      let nextPages = [...prev]

      if (event.action === 'add_pages' && event.pages) {
        const existing = new Map(nextPages.map((p) => [p.pageId, p]))
        for (const page of event.pages) {
          const prior = existing.get(page.page_id)
          if (prior) {
            prior.pageName = page.page_name
            prior.imageUrl = page.file_path
          } else {
            existing.set(page.page_id, {
              pageId: page.page_id,
              pageName: page.page_name,
              imageUrl: page.file_path,
              state: 'done',
              pinned: nextState.pinned_pages.includes(page.page_id),
              bboxes: [],
              findings: [],
            })
          }
        }
        nextPages = Array.from(existing.values())
      }

      if (event.action === 'remove_pages' && event.page_ids) {
        nextPages = nextPages.filter((p) => !event.page_ids?.includes(p.pageId))
      }

      if (event.action === 'highlight_pointers' && event.pointers) {
        const pageMap = new Map(nextPages.map((p) => [p.pageId, { ...p }]))
        for (const pointer of event.pointers) {
          const page = pageMap.get(pointer.page_id)
          if (!page) continue
          const bbox: BoundingBox = {
            x: pointer.bbox_x,
            y: pointer.bbox_y,
            width: pointer.bbox_width,
            height: pointer.bbox_height,
            label: pointer.title,
          }
          page.bboxes = [bbox]
          pageMap.set(pointer.page_id, page)
        }
        nextPages = Array.from(pageMap.values())
      }

      if (event.action === 'pin_page') {
        nextPages = nextPages.map((page) => ({
          ...page,
          pinned: nextState.pinned_pages.includes(page.pageId),
        }))
      }

      return nextPages
    })
  }, [])

  const handleEvent = useCallback((turnId: string, event: V3Event) => {
    setTurns((prev) => {
      const next = [...prev]
      const turnNumber = 'turn_number' in event ? event.turn_number : undefined
      const index = turnNumber
        ? next.findIndex((turn) => turn.turnNumber === turnNumber)
        : next.findIndex((turn) => turn.id === turnId)
      if (index === -1) return prev
      const turn = { ...next[index] }

      switch (event.type) {
        case 'token':
          turn.response += event.content
          break
        case 'thinking':
          turn.panels[event.panel] = appendPanelText(turn.panels[event.panel], event.content)
          if (event.panel === 'learning') {
            turn.learningStarted = true
          }
          break
        case 'tool_call':
          turn.toolEvents = [...turn.toolEvents, `Tool call: ${event.tool}`]
          turn.panels.workspace_assembly = appendPanelText(
            turn.panels.workspace_assembly,
            `**Tool call**: ${event.tool}
${JSON.stringify(event.arguments, null, 2)}`,
          )
          break
        case 'tool_result':
          turn.toolEvents = [...turn.toolEvents, `Tool result: ${event.tool}`]
          turn.panels.workspace_assembly = appendPanelText(
            turn.panels.workspace_assembly,
            `**Tool result**: ${event.tool}
${JSON.stringify(event.result, null, 2)}`,
          )
          break
        case 'workspace_update':
          applyWorkspaceUpdate(event)
          break
        case 'done':
          turn.done = true
          setIsStreaming(false)
          break
        case 'learning_done':
          turn.learningDone = true
          break
      }

      next[index] = turn
      return next
    })
  }, [applyWorkspaceUpdate, setIsStreaming])

  const sendMessage = useCallback(async (message: string) => {
    if (!activeSessionRef.current) return
    if (isStreaming) return

    const turnId = `turn-${Date.now()}`
    setTurns((prev) => {
      const nextTurnNumber = prev.length ? prev[prev.length - 1].turnNumber + 1 : 1
      return [
        ...prev,
        {
          id: turnId,
          turnNumber: nextTurnNumber,
          user: message,
          response: '',
          panels: createEmptyPanels(),
          toolEvents: [],
          done: false,
          learningStarted: false,
          learningDone: false,
        },
      ]
    })

    setIsStreaming(true)

    const headers = await getAuthHeaders()
    const controller = new AbortController()
    abortControllerRef.current = controller

    try {
      const res = await fetch(`${API_URL}/v3/sessions/${activeSessionRef.current}/query`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ message }),
        signal: controller.signal,
      })

      if (!res.ok || !res.body) {
        throw new Error('Failed to stream response')
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() || ''

        for (const part of parts) {
          if (!part.trim()) continue
          const lines = part.split('\n')
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const payload = line.slice(6).trim()
            if (!payload) continue
            let event: V3Event
            try {
              event = JSON.parse(payload)
            } catch {
              continue
            }
            handleEvent(turnId, event)
          }
        }
      }
    } catch (err) {
      if ((err as DOMException).name !== 'AbortError') {
        throw err
      }
    } finally {
      setIsStreaming(false)
    }
  }, [getAuthHeaders, handleEvent, isStreaming])

  useEffect(() => {
    refreshSessions().catch((err) => {
      console.error('Failed to load sessions', err)
    })
  }, [refreshSessions])

  useEffect(() => {
    if (!projectId || !storageKey) return

    const params = new URLSearchParams(window.location.search)
    const urlSession = params.get('session') || params.get('session_id')
    const storedSession = localStorage.getItem(storageKey)
    const targetSession = urlSession || storedSession

    if (targetSession) {
      loadSession(targetSession).catch((err) => {
        console.warn('Failed to restore session', err)
        localStorage.removeItem(storageKey)
      })
    }
  }, [projectId, storageKey, loadSession])

  useEffect(() => {
    return () => {
      abortActiveStream()
      setIsStreaming(false)
    }
  }, [abortActiveStream])

  return {
    activeSessionId,
    activeWorkspaceName,
    sessions,
    turns,
    workspacePages,
    isStreaming,
    isLoadingSession,
    isLoadingSessions,
    refreshSessions,
    createWorkspace,
    switchWorkspace,
    closeWorkspace,
    renameWorkspace,
    sendMessage,
  }
}
