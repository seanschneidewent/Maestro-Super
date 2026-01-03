import {
  AgentMessage,
  AgentTraceStep,
  ContextPointer,
  FieldResponse,
  FieldPage,
  FieldPointer,
} from '../../types'

export function transformAgentResponse(
  agentMessage: AgentMessage,
  renderedPages: Map<string, string>, // pageId -> pngDataUrl
  pageMetadata: Map<string, { title: string; pageNumber: number }>, // pageId -> metadata
  contextPointers: Map<string, ContextPointer[]>, // pageId -> pointers
  query: string
): FieldResponse {
  const pages: FieldPage[] = []

  // Extract pages visited from agentMessage.pagesVisited
  const visitedPages = agentMessage.pagesVisited || []

  for (const visit of visitedPages) {
    const pngDataUrl = renderedPages.get(visit.pageId)
    const metadata = pageMetadata.get(visit.pageId)
    const pointers = contextPointers.get(visit.pageId) || []

    if (!pngDataUrl || !metadata) continue

    // Transform ContextPointers to FieldPointers
    const fieldPointers: FieldPointer[] = pointers.map((pointer) => ({
      id: pointer.id,
      label: pointer.title || 'Region',
      region: {
        bboxX: pointer.bboxX,
        bboxY: pointer.bboxY,
        bboxWidth: pointer.bboxWidth,
        bboxHeight: pointer.bboxHeight,
      },
      answer: extractFirstLine(pointer.description),
      evidence: {
        type: 'explanation' as const,
        text: pointer.description,
      },
    }))

    // Generate intro from agent reasoning or use page name
    const intro = generatePageIntro(visit.pageName, agentMessage.reasoning)

    pages.push({
      id: visit.pageId,
      pageNumber: metadata.pageNumber,
      title: metadata.title || visit.pageName,
      pngDataUrl,
      intro,
      pointers: fieldPointers,
    })
  }

  // Extract summary from finalAnswer
  const summary = extractSummary(agentMessage.finalAnswer)

  return {
    id: `response-${agentMessage.timestamp.getTime()}`,
    query,
    summary,
    pages,
  }
}

export function extractLatestThinking(trace: AgentTraceStep[]): string {
  // Find the last reasoning entry in trace
  for (let i = trace.length - 1; i >= 0; i--) {
    const step = trace[i]
    if (step.type === 'reasoning' && step.content) {
      // Clean up markdown and get first real sentence
      let content = step.content
        .replace(/^#+\s*.*/gm, '') // Remove markdown headers
        .replace(/^\*\*[^*]+\*\*\s*/gm, '') // Remove bold headers like **Summary**
        .replace(/^\s*[-*]\s*/gm, '') // Remove list markers
        .trim()

      // Skip if only headers/formatting was present
      if (!content) continue

      // Get first sentence
      const sentenceMatch = content.match(/^[^.!?]*[.!?]/)
      if (sentenceMatch) {
        return sentenceMatch[0].trim()
      }

      // No sentence ending, truncate
      if (content.length > 100) {
        return content.slice(0, 97) + '...'
      }

      return content
    }
  }

  return ''
}

function extractFirstLine(text: string): string {
  if (!text) return ''

  // Split by newlines and get first non-empty line
  const lines = text.split('\n').filter((line) => line.trim())
  const firstLine = lines[0] || ''

  // Truncate if too long
  if (firstLine.length > 150) {
    return firstLine.slice(0, 147) + '...'
  }

  return firstLine
}

function extractSummary(finalAnswer: string | undefined): string {
  if (!finalAnswer) return ''

  const trimmed = finalAnswer.trim()

  // Try to get first sentence
  const periodIndex = trimmed.indexOf('.')
  if (periodIndex > 0 && periodIndex < 200) {
    return trimmed.slice(0, periodIndex + 1)
  }

  // Truncate if too long
  if (trimmed.length > 200) {
    return trimmed.slice(0, 197) + '...'
  }

  return trimmed
}

function generatePageIntro(pageName: string, reasoning?: string[]): string {
  // For now, generate a simple intro based on page name
  // Later this can be enriched with agent reasoning
  if (reasoning && reasoning.length > 0) {
    // Try to find reasoning that mentions this page
    const relevant = reasoning.find(
      (r) => r.toLowerCase().includes(pageName.toLowerCase())
    )
    if (relevant) {
      return extractFirstLine(relevant)
    }
  }

  return `Information found on ${pageName}`
}
