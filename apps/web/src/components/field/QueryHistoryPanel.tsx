import { useState, useEffect } from 'react'
import { X, Trash2, MessageSquare } from 'lucide-react'
import { api, QueryResponse } from '../../lib/api'
import { AgentTraceStep } from '../../types'

interface QueryHistoryPanelProps {
  projectId: string
  isOpen: boolean
  onClose: () => void
  onRestoreSession: (query: QueryResponse, trace: AgentTraceStep[], finalAnswer: string) => void
}

function formatTimeAgo(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength - 3) + '...'
}

export function QueryHistoryPanel({
  projectId,
  isOpen,
  onClose,
  onRestoreSession,
}: QueryHistoryPanelProps) {
  const [queries, setQueries] = useState<QueryResponse[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Load queries when panel opens
  useEffect(() => {
    if (!isOpen) return

    const loadQueries = async () => {
      setIsLoading(true)
      setError(null)
      try {
        const data = await api.queries.list(projectId)
        setQueries(data)
      } catch (err) {
        console.error('Failed to load query history:', err)
        setError('Failed to load history')
      } finally {
        setIsLoading(false)
      }
    }

    loadQueries()
  }, [isOpen, projectId])

  // Hide a query (soft delete)
  const handleHide = async (queryId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await api.queries.hide(queryId)
      setQueries((prev) => prev.filter((q) => q.id !== queryId))
    } catch (err) {
      console.error('Failed to hide query:', err)
    }
  }

  // Restore a previous session
  const handleRestore = (query: QueryResponse) => {
    // Convert API trace format to AgentTraceStep format
    const trace: AgentTraceStep[] = (query.trace || []).map((step) => ({
      type: step.type,
      content: step.content,
      tool: step.tool,
      input: step.input,
      result: step.result,
    }))

    onRestoreSession(query, trace, query.responseText || '')
    onClose()
  }

  if (!isOpen) return null

  return (
    <div className="w-80 h-full bg-white/95 backdrop-blur-md border-l border-slate-200/50 flex flex-col z-20 shadow-lg">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200/50">
        <h2 className="text-lg font-medium text-slate-800">Query History</h2>
        <button
          onClick={onClose}
          className="p-1 rounded-lg hover:bg-slate-100 transition-colors"
        >
          <X size={18} className="text-slate-500" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <div className="p-4 text-center text-slate-500 text-sm">
            Loading history...
          </div>
        )}

        {error && (
          <div className="p-4 text-center text-red-500 text-sm">{error}</div>
        )}

        {!isLoading && !error && queries.length === 0 && (
          <div className="p-4 text-center text-slate-400 text-sm">
            No queries yet. Ask a question to get started!
          </div>
        )}

        {!isLoading && !error && queries.length > 0 && (
          <div className="divide-y divide-slate-100">
            {queries.map((query) => (
              <button
                key={query.id}
                onClick={() => handleRestore(query)}
                className="w-full p-4 text-left hover:bg-slate-50 transition-colors group"
              >
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0 mt-0.5">
                    <MessageSquare size={16} className="text-cyan-500" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-slate-800 font-medium leading-snug">
                      {truncateText(query.queryText, 80)}
                    </p>
                    {query.responseText && (
                      <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                        {truncateText(query.responseText, 100)}
                      </p>
                    )}
                    <p className="text-xs text-slate-400 mt-2">
                      {formatTimeAgo(query.createdAt)}
                      {query.tokensUsed && (
                        <span className="ml-2 text-slate-300">
                          {query.tokensUsed.toLocaleString()} tokens
                        </span>
                      )}
                    </p>
                  </div>
                  <button
                    onClick={(e) => handleHide(query.id, e)}
                    className="flex-shrink-0 p-1.5 rounded-lg opacity-0 group-hover:opacity-100 hover:bg-red-50 transition-all"
                    title="Remove from history"
                  >
                    <Trash2 size={14} className="text-red-400" />
                  </button>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
