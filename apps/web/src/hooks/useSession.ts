import { useCallback, useEffect, useRef, useState } from 'react'
import { supabase } from '../lib/supabase'
import type { V3Event, V3WorkspaceUpdateEvent, V3ThinkingPanel, V3WorkspaceState } from '../types/v3'
import type { WorkspacePage, BoundingBox } from '../components/maestro/PageWorkspace'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface MaestroTurn {
  id: string
  user: string
  response: string
  panels: Record<V3ThinkingPanel, string>
  toolEvents: string[]
  done: boolean
}

interface UseSessionResult {
  sessionId: string | null
  turns: MaestroTurn[]
  workspacePages: WorkspacePage[]
  isStreaming: boolean
  createSession: (projectId: string) => Promise<void>
  sendMessage: (message: string) => Promise<void>
}

function createEmptyPanels(): Record<V3ThinkingPanel, string> {
  return {
    workspace_assembly: '',
    learning: '',
    knowledge_update: '',
  }
}

function appendPanelText(current: string, incoming: string): string {
  if (!incoming) return current
  return current ? `${current}\n${incoming}` : incoming
}

export function useSession(): UseSessionResult {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [turns, setTurns] = useState<MaestroTurn[]>([])
  const [workspacePages, setWorkspacePages] = useState<WorkspacePage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const workspaceStateRef = useRef<V3WorkspaceState>({
    displayed_pages: [],
    highlighted_pointers: [],
    pinned_pages: [],
  })

  const createSession = useCallback(async (projectId: string) => {
    const { data: { session } } = await supabase.auth.getSession()
    const res = await fetch(`${API_URL}/v3/sessions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(session?.access_token && { Authorization: `Bearer ${session.access_token}` }),
      },
      body: JSON.stringify({
        project_id: projectId,
        session_type: 'workspace',
      }),
    })

    if (!res.ok) {
      throw new Error('Failed to create session')
    }

    const data = await res.json()
    setSessionId(data.session_id)
    if (data.workspace_state) {
      workspaceStateRef.current = data.workspace_state
    }
  }, [])

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
      const index = next.findIndex((turn) => turn.id === turnId)
      if (index === -1) return prev
      const turn = { ...next[index] }

      switch (event.type) {
        case 'token':
          turn.response += event.content
          break
        case 'thinking':
          turn.panels[event.panel] = appendPanelText(turn.panels[event.panel], event.content)
          break
        case 'tool_call':
          turn.toolEvents = [...turn.toolEvents, `Tool call: ${event.tool}`]
          turn.panels.workspace_assembly = appendPanelText(
            turn.panels.workspace_assembly,
            `**Tool call**: ${event.tool}\n${JSON.stringify(event.arguments, null, 2)}`,
          )
          break
        case 'tool_result':
          turn.toolEvents = [...turn.toolEvents, `Tool result: ${event.tool}`]
          turn.panels.workspace_assembly = appendPanelText(
            turn.panels.workspace_assembly,
            `**Tool result**: ${event.tool}\n${JSON.stringify(event.result, null, 2)}`,
          )
          break
        case 'workspace_update':
          applyWorkspaceUpdate(event)
          break
        case 'done':
          turn.done = true
          break
      }

      next[index] = turn
      return next
    })
  }, [applyWorkspaceUpdate])

  const sendMessage = useCallback(async (message: string) => {
    if (!sessionId) return

    const turnId = `turn-${Date.now()}`
    setTurns((prev) => [
      ...prev,
      {
        id: turnId,
        user: message,
        response: '',
        panels: createEmptyPanels(),
        toolEvents: [],
        done: false,
      },
    ])

    setIsStreaming(true)

    const { data: { session } } = await supabase.auth.getSession()
    const res = await fetch(`${API_URL}/v3/sessions/${sessionId}/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(session?.access_token && { Authorization: `Bearer ${session.access_token}` }),
      },
      body: JSON.stringify({ message }),
    })

    if (!res.ok || !res.body) {
      setIsStreaming(false)
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

    setIsStreaming(false)
  }, [sessionId, applyWorkspaceUpdate])

  useEffect(() => {
    return () => {
      setIsStreaming(false)
    }
  }, [])

  return {
    sessionId,
    turns,
    workspacePages,
    isStreaming,
    createSession,
    sendMessage,
  }
}
