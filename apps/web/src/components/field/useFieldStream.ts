import { useState, useCallback, useRef } from 'react'
import { supabase } from '../../lib/supabase'
import { FieldResponse, ContextPointer, AgentTraceStep } from '../../types'
import { transformAgentResponse, extractLatestThinking } from './transformResponse'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

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
}

export interface CompletedQuery {
  queryId: string
  queryText: string
  displayTitle: string | null
  pages: AgentSelectedPage[]
  finalAnswer: string
  trace: AgentTraceStep[]
}

interface UseFieldStreamOptions {
  projectId: string
  renderedPages: Map<string, string>
  pageMetadata: Map<string, { title: string; pageNumber: number }>
  contextPointers: Map<string, ContextPointer[]>
  onQueryComplete?: (query: CompletedQuery) => void
}

interface UseFieldStreamReturn {
  submitQuery: (query: string, sessionId?: string) => Promise<void>
  isStreaming: boolean
  thinkingText: string
  finalAnswer: string
  displayTitle: string | null
  currentQueryId: string | null
  trace: AgentTraceStep[]
  selectedPages: AgentSelectedPage[]
  currentTool: string | null
  response: FieldResponse | null
  error: string | null
  reset: () => void
  abort: () => void
  restore: (trace: AgentTraceStep[], finalAnswer: string, displayTitle: string | null, pages?: AgentSelectedPage[]) => void
  loadPages: (pages: AgentSelectedPage[]) => void
}

interface AgentMessageAccumulator {
  timestamp: Date
  reasoning: string[]
  pagesVisited: { pageId: string; pageName: string }[]
  finalAnswer?: string
  trace: AgentTraceStep[]
  isComplete: boolean
}

export function useFieldStream(options: UseFieldStreamOptions): UseFieldStreamReturn {
  const { projectId, renderedPages, pageMetadata, contextPointers, onQueryComplete } = options

  const [isStreaming, setIsStreaming] = useState(false)
  const [thinkingText, setThinkingText] = useState('')
  const [finalAnswer, setFinalAnswer] = useState('')
  const [displayTitle, setDisplayTitle] = useState<string | null>(null)
  const [currentQueryId, setCurrentQueryId] = useState<string | null>(null)
  const [trace, setTrace] = useState<AgentTraceStep[]>([])
  const [selectedPages, setSelectedPages] = useState<AgentSelectedPage[]>([])
  const [currentTool, setCurrentTool] = useState<string | null>(null)
  const [response, setResponse] = useState<FieldResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const selectedPagesRef = useRef<AgentSelectedPage[]>([])
  const currentQueryRef = useRef<{ id: string; text: string } | null>(null)
  const pageDataCache = useRef<Map<string, { filePath: string; pageName: string; disciplineId: string }>>(new Map())

  const abort = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
      setIsStreaming(false)
    }
  }, [])

  const submitQuery = useCallback(
    async (query: string, sessionId?: string) => {
      // Abort any existing stream
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }

      setIsStreaming(true)
      setThinkingText('')
      setFinalAnswer('')
      setDisplayTitle(null)
      setCurrentQueryId(null)
      setTrace([])
      setSelectedPages([])
      selectedPagesRef.current = []
      currentQueryRef.current = { id: '', text: query }
      setResponse(null)
      setError(null)

      // Create new abort controller
      abortControllerRef.current = new AbortController()

      // Accumulate agent message data
      const agentMessage: AgentMessageAccumulator = {
        timestamp: new Date(),
        reasoning: [],
        pagesVisited: [],
        trace: [],
        isComplete: false,
      }

      try {
        // Get auth token
        const {
          data: { session },
        } = await supabase.auth.getSession()

        const res = await fetch(`${API_URL}/projects/${projectId}/queries/stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(session?.access_token && {
              Authorization: `Bearer ${session.access_token}`,
            }),
          },
          body: JSON.stringify({ query, sessionId }),
          signal: abortControllerRef.current.signal,
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

          // Decode chunk and add to buffer
          buffer += decoder.decode(value, { stream: true })

          // Process complete SSE messages (separated by double newlines)
          const parts = buffer.split('\n\n')
          buffer = parts.pop() || '' // Keep incomplete part in buffer

          for (const part of parts) {
            if (!part.trim()) continue

            // Parse SSE format: "data: {...}"
            const lines = part.split('\n')
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const jsonStr = line.slice(6).trim()
                if (jsonStr) {
                  try {
                    const data = JSON.parse(jsonStr)
                    processEvent(data, agentMessage, query)
                  } catch (parseError) {
                    console.warn('Failed to parse SSE event:', jsonStr, parseError)
                  }
                }
              }
            }
          }
        }

        // Process any remaining data in buffer
        if (buffer.trim()) {
          const lines = buffer.split('\n')
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const jsonStr = line.slice(6).trim()
              if (jsonStr) {
                try {
                  const data = JSON.parse(jsonStr)
                  processEvent(data, agentMessage, query)
                } catch (parseError) {
                  console.warn('Failed to parse remaining SSE event:', jsonStr, parseError)
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
        setError(message)
        setIsStreaming(false)
      }
    },
    [projectId, renderedPages, pageMetadata, contextPointers]
  )

  const processEvent = (
    data: Record<string, unknown>,
    agentMessage: AgentMessageAccumulator,
    query: string
  ) => {
    switch (data.type) {
      case 'text':
        // Accumulate text into the current reasoning step (or create one)
        if (typeof data.content === 'string') {
          agentMessage.reasoning.push(data.content)

          // Check if the last trace step is a reasoning step we can append to
          const lastStep = agentMessage.trace[agentMessage.trace.length - 1]
          if (lastStep && lastStep.type === 'reasoning') {
            // Append to existing reasoning step
            lastStep.content = (lastStep.content || '') + data.content
          } else {
            // Create new reasoning step
            agentMessage.trace.push({ type: 'reasoning', content: data.content })
          }

          setTrace([...agentMessage.trace])
          setThinkingText(extractLatestThinking(agentMessage.trace))
        }
        break

      case 'tool_call':
        if (typeof data.tool === 'string') {
          // Set current tool for status display
          setCurrentTool(data.tool)

          // Don't update thinkingText for tool calls - only show reasoning in the bubble
          const newStep: AgentTraceStep = {
            type: 'tool_call',
            tool: data.tool,
            input: data.input as Record<string, unknown>,
          }
          agentMessage.trace.push(newStep)
          setTrace([...agentMessage.trace])

          // Track page visits from get_page_details tool
          if (data.tool === 'get_page_details' && data.input) {
            const input = data.input as { page_id?: string; page_name?: string }
            if (input.page_id) {
              agentMessage.pagesVisited.push({
                pageId: input.page_id,
                pageName: input.page_name || 'Unknown Page',
              })
            }
          }

          // Prefetch pages on select_pages tool_call using cached search_pages data
          if (data.tool === 'select_pages') {
            const input = data.input as { page_ids?: string[] }
            if (input?.page_ids) {
              const pagesToPrefetch: AgentSelectedPage[] = []
              for (const pageId of input.page_ids) {
                const cached = pageDataCache.current.get(pageId)
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
                selectedPagesRef.current = pagesToPrefetch
                setSelectedPages([...pagesToPrefetch])
              }
            }
          }
        }
        break

      case 'tool_result':
        if (typeof data.tool === 'string') {
          // NOTE: Don't clear currentTool here - React batching causes the status to never show.
          // Instead, clear it only when streaming ends (in 'done' case).

          const newStep: AgentTraceStep = {
            type: 'tool_result',
            tool: data.tool,
            result: data.result as Record<string, unknown>,
          }
          agentMessage.trace.push(newStep)
          setTrace([...agentMessage.trace])

          // Cache page data from search_pages for prefetching on select_pages tool_call
          if (data.tool === 'search_pages') {
            const result = data.result as { pages?: Array<{ page_id: string; page_name: string; file_path: string; discipline_id: string }> }
            if (result?.pages) {
              for (const p of result.pages) {
                pageDataCache.current.set(p.page_id, {
                  filePath: p.file_path,
                  pageName: p.page_name,
                  disciplineId: p.discipline_id,
                })
              }
            }
          }

          // Extract selected pages from select_pages tool
          if (data.tool === 'select_pages') {
            const result = data.result as {
              pages?: Array<{
                page_id: string
                page_name: string
                file_path: string
                discipline_id: string
                discipline_name?: string
              }>
            }

            if (result?.pages && Array.isArray(result.pages)) {
              // Find the corresponding tool_call to get the agent's intended page order
              // (the result.pages order is scrambled by the SQL .in_() query)
              let orderedPageIds: string[] | null = null
              for (let i = agentMessage.trace.length - 1; i >= 0; i--) {
                const step = agentMessage.trace[i]
                if (step.type === 'tool_call' && step.tool === 'select_pages') {
                  const input = step.input as { page_ids?: string[] }
                  if (input?.page_ids) {
                    orderedPageIds = input.page_ids
                  }
                  break
                }
              }

              // Build a map of page_id -> page data for quick lookup
              const pageDataMap = new Map<string, typeof result.pages[0]>()
              for (const p of result.pages) {
                if (p.page_id && p.file_path) {
                  pageDataMap.set(p.page_id, p)
                }
              }

              // Build pages in the agent's intended order
              const newPages: AgentSelectedPage[] = []
              const pageOrder = orderedPageIds || result.pages.map(p => p.page_id)
              for (const pageId of pageOrder) {
                const p = pageDataMap.get(pageId)
                if (p) {
                  newPages.push({
                    pageId: p.page_id,
                    pageName: p.page_name || 'Unknown',
                    filePath: p.file_path,
                    disciplineId: p.discipline_id || '',
                    pointers: [], // No pointers for select_pages
                  })
                }
              }

              // Merge with existing (avoid duplicates)
              const existingPageIds = new Set(selectedPagesRef.current.map((p) => p.pageId))
              const uniqueNewPages = newPages.filter((p) => !existingPageIds.has(p.pageId))

              if (uniqueNewPages.length > 0) {
                selectedPagesRef.current = [...selectedPagesRef.current, ...uniqueNewPages]
                setSelectedPages([...selectedPagesRef.current])
              }
              // Don't update thinkingText for tool results - only show reasoning in the bubble
            }
          }
          // Extract selected pages from select_pointers tool
          else if (data.tool === 'select_pointers') {
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

            if (result?.pointers && Array.isArray(result.pointers)) {
              // Find the corresponding tool_call to get the agent's intended pointer order
              let orderedPointerIds: string[] | null = null
              for (let i = agentMessage.trace.length - 1; i >= 0; i--) {
                const step = agentMessage.trace[i]
                if (step.type === 'tool_call' && step.tool === 'select_pointers') {
                  const input = step.input as { pointer_ids?: string[] }
                  if (input?.pointer_ids) {
                    orderedPointerIds = input.pointer_ids
                  }
                  break
                }
              }

              // Build a map of pointer_id -> pointer data for quick lookup
              const pointerDataMap = new Map<string, typeof result.pointers[0]>()
              for (const p of result.pointers) {
                if (p.pointer_id) {
                  pointerDataMap.set(p.pointer_id, p)
                }
              }

              // Group pointers by page, preserving the order from tool_call input
              const pageMap = new Map<string, AgentSelectedPage>()
              const pageOrder: string[] = []  // Track order pages are first encountered

              const pointerOrder = orderedPointerIds || result.pointers.map(p => p.pointer_id)
              for (const pointerId of pointerOrder) {
                const p = pointerDataMap.get(pointerId)
                if (!p || !p.page_id || !p.file_path) continue

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

              // Merge pointers into existing pages OR add new pages
              const existingPageMap = new Map(selectedPagesRef.current.map((p) => [p.pageId, p]))
              let hasChanges = false

              for (const pageId of pageOrder) {
                const newPageData = pageMap.get(pageId)!
                const existingPage = existingPageMap.get(pageId)

                if (existingPage) {
                  // Page already exists - merge pointers into it
                  const existingPointerIds = new Set(existingPage.pointers.map((p) => p.pointerId))
                  for (const pointer of newPageData.pointers) {
                    if (!existingPointerIds.has(pointer.pointerId)) {
                      existingPage.pointers.push(pointer)
                      hasChanges = true
                    }
                  }
                } else {
                  // New page - add it to the list
                  selectedPagesRef.current.push(newPageData)
                  existingPageMap.set(pageId, newPageData)
                  hasChanges = true
                }
              }

              if (hasChanges) {
                setSelectedPages([...selectedPagesRef.current])
              }
              // Don't update thinkingText for tool results - only show reasoning in the bubble
            }
          }
          // Don't update thinkingText for any tool results - only show reasoning in the bubble
        }
        break

      case 'done':
        agentMessage.isComplete = true

        // Extract displayTitle from done event
        const eventDisplayTitle = typeof data.displayTitle === 'string' ? data.displayTitle : null
        setDisplayTitle(eventDisplayTitle)

        // Extract final answer from trace (reasoning after last tool result)
        const traceSteps = agentMessage.trace
        let extractedAnswer = ''

        // Find the last tool_result index
        let lastToolResultIndex = -1
        for (let i = traceSteps.length - 1; i >= 0; i--) {
          if (traceSteps[i].type === 'tool_result') {
            lastToolResultIndex = i
            break
          }
        }

        // Collect all reasoning after the last tool result as the final answer
        const answerParts: string[] = []
        for (let i = lastToolResultIndex + 1; i < traceSteps.length; i++) {
          if (traceSteps[i].type === 'reasoning' && traceSteps[i].content) {
            answerParts.push(traceSteps[i].content!)
          }
        }
        extractedAnswer = answerParts.join('')

        // If no tools were called, the entire reasoning is the answer
        if (lastToolResultIndex === -1) {
          extractedAnswer = agentMessage.reasoning.join('')
        }

        agentMessage.finalAnswer = extractedAnswer
        setFinalAnswer(extractedAnswer)

        // Generate a query ID for tracking
        const queryId = `query-${agentMessage.timestamp.getTime()}`
        setCurrentQueryId(queryId)
        if (currentQueryRef.current) {
          currentQueryRef.current.id = queryId
        }

        // Transform to FieldResponse
        const fieldResponse = transformAgentResponse(
          {
            id: `msg-${agentMessage.timestamp.getTime()}`,
            role: 'agent',
            timestamp: agentMessage.timestamp,
            reasoning: agentMessage.reasoning,
            finalAnswer: agentMessage.finalAnswer,
            displayTitle: eventDisplayTitle,
            trace: agentMessage.trace,
            pagesVisited: agentMessage.pagesVisited,
            isComplete: true,
          },
          renderedPages,
          pageMetadata,
          contextPointers,
          query
        )
        setResponse(fieldResponse)
        setIsStreaming(false)
        setCurrentTool(null) // Clear tool status when streaming completes

        // Notify parent of completed query
        if (onQueryComplete && currentQueryRef.current) {
          onQueryComplete({
            queryId,
            queryText: currentQueryRef.current.text,
            displayTitle: eventDisplayTitle,
            pages: [...selectedPagesRef.current],
            finalAnswer: extractedAnswer,
            trace: [...agentMessage.trace],
          })
        }
        break

      case 'error':
        if (typeof data.message === 'string') {
          setError(data.message)
        } else {
          setError('An error occurred')
        }
        setIsStreaming(false)
        setCurrentTool(null) // Clear tool status on error
        break
    }
  }

  const reset = useCallback(() => {
    abort()
    setIsStreaming(false)
    setThinkingText('')
    setFinalAnswer('')
    setDisplayTitle(null)
    setCurrentQueryId(null)
    setTrace([])
    setSelectedPages([])
    setCurrentTool(null)
    selectedPagesRef.current = []
    currentQueryRef.current = null
    pageDataCache.current.clear()
    setResponse(null)
    setError(null)
  }, [abort])

  const restore = useCallback((
    restoredTrace: AgentTraceStep[],
    restoredFinalAnswer: string,
    restoredDisplayTitle: string | null,
    pages?: AgentSelectedPage[]
  ) => {
    abort()
    setIsStreaming(false)
    setThinkingText('')
    setFinalAnswer(restoredFinalAnswer)
    setDisplayTitle(restoredDisplayTitle)
    setTrace(restoredTrace)
    setSelectedPages(pages || [])
    selectedPagesRef.current = pages || []
    setResponse(null)
    setError(null)
  }, [abort])

  // Load pages directly (for restoring from QueryStack selection)
  const loadPages = useCallback((pages: AgentSelectedPage[]) => {
    setSelectedPages(pages)
    selectedPagesRef.current = pages
  }, [])

  return {
    submitQuery,
    isStreaming,
    thinkingText,
    finalAnswer,
    displayTitle,
    currentQueryId,
    trace,
    selectedPages,
    currentTool,
    response,
    error,
    reset,
    abort,
    restore,
    loadPages,
  }
}
