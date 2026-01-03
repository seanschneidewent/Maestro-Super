import { useState, useCallback, useRef } from 'react'
import { supabase } from '../../lib/supabase'
import { FieldResponse, ContextPointer, AgentTraceStep } from '../../types'
import { transformAgentResponse, extractLatestThinking } from './transformResponse'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface UseFieldStreamOptions {
  projectId: string
  renderedPages: Map<string, string>
  pageMetadata: Map<string, { title: string; pageNumber: number }>
  contextPointers: Map<string, ContextPointer[]>
}

interface UseFieldStreamReturn {
  submitQuery: (query: string) => Promise<void>
  isStreaming: boolean
  thinkingText: string
  finalAnswer: string
  trace: AgentTraceStep[]
  response: FieldResponse | null
  error: string | null
  reset: () => void
  abort: () => void
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
  const { projectId, renderedPages, pageMetadata, contextPointers } = options

  const [isStreaming, setIsStreaming] = useState(false)
  const [thinkingText, setThinkingText] = useState('')
  const [finalAnswer, setFinalAnswer] = useState('')
  const [trace, setTrace] = useState<AgentTraceStep[]>([])
  const [response, setResponse] = useState<FieldResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const abort = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
      setIsStreaming(false)
    }
  }, [])

  const submitQuery = useCallback(
    async (query: string) => {
      // Abort any existing stream
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }

      setIsStreaming(true)
      setThinkingText('')
      setFinalAnswer('')
      setTrace([])
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
          body: JSON.stringify({ query }),
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
          setThinkingText(`Searching ${data.tool}...`)
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
        }
        break

      case 'tool_result':
        if (typeof data.tool === 'string') {
          const newStep: AgentTraceStep = {
            type: 'tool_result',
            tool: data.tool,
            result: data.result as Record<string, unknown>,
          }
          agentMessage.trace.push(newStep)
          setTrace([...agentMessage.trace])

          // Could preview results
          const result = data.result as { pointers?: unknown[] }
          if (result?.pointers && Array.isArray(result.pointers)) {
            setThinkingText(`Found ${result.pointers.length} locations...`)
          }
        }
        break

      case 'done':
        agentMessage.isComplete = true

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

        // Transform to FieldResponse
        const fieldResponse = transformAgentResponse(
          {
            id: `msg-${agentMessage.timestamp.getTime()}`,
            role: 'agent',
            timestamp: agentMessage.timestamp,
            reasoning: agentMessage.reasoning,
            finalAnswer: agentMessage.finalAnswer,
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
        break

      case 'error':
        if (typeof data.message === 'string') {
          setError(data.message)
        } else {
          setError('An error occurred')
        }
        setIsStreaming(false)
        break
    }
  }

  const reset = useCallback(() => {
    abort()
    setIsStreaming(false)
    setThinkingText('')
    setFinalAnswer('')
    setTrace([])
    setResponse(null)
    setError(null)
  }, [abort])

  return { submitQuery, isStreaming, thinkingText, finalAnswer, trace, response, error, reset, abort }
}
