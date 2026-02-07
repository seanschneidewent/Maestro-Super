import { useState, useEffect } from 'react'
import { X, ChevronRight, MessageSquare, Layers, Trash2, Loader2 } from 'lucide-react'
import { api, QueryResponse, V3SessionTurnResponse } from '../../lib/api'

interface QueryHistoryPanelProps {
  projectId: string
  isOpen: boolean
  onClose: () => void
  onRestoreConversation: (
    conversationId: string,
    queries: QueryResponse[],
    selectedQueryId: string
  ) => void
}

interface WorkspaceHistoryItem {
  id: string
  title: string | null
  updatedAt: string
}

interface WorkspaceHistoryDetail {
  id: string
  title: string | null
  queries: QueryResponse[]
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

function mapTurnsToQueries(
  sessionId: string,
  projectId: string,
  updatedAt: string,
  turns: V3SessionTurnResponse[],
): QueryResponse[] {
  return turns.map((turn, idx) => {
    const createdAt = new Date(new Date(updatedAt).getTime() + idx).toISOString()
    const queryText = turn.user || ''
    return {
      id: `${sessionId}-turn-${turn.turn_number}`,
      userId: '',
      projectId,
      conversationId: sessionId,
      queryText,
      responseText: turn.response || '',
      displayTitle: queryText ? truncateText(queryText, 50) : null,
      sequenceOrder: turn.turn_number,
      trace: [],
      pages: [],
      createdAt,
    }
  })
}

function getConversationTitle(conversation: WorkspaceHistoryDetail): string {
  if (conversation.title) {
    return conversation.title
  }
  if (conversation.queries.length > 0) {
    const firstQuery = conversation.queries[0]
    return firstQuery.displayTitle || truncateText(firstQuery.queryText, 30)
  }
  return 'Empty workspace'
}

export function QueryHistoryPanel({
  projectId,
  isOpen,
  onClose,
  onRestoreConversation,
}: QueryHistoryPanelProps) {
  const [workspaces, setWorkspaces] = useState<WorkspaceHistoryItem[]>([])
  const [expandedConversationId, setExpandedConversationId] = useState<string | null>(null)
  const [expandedConversationData, setExpandedConversationData] = useState<WorkspaceHistoryDetail | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingConversation, setIsLoadingConversation] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [deleteTarget, setDeleteTarget] = useState<{
    id: string
    title: string
  } | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  useEffect(() => {
    if (!isOpen) return

    const loadWorkspaces = async () => {
      setIsLoading(true)
      setError(null)
      try {
        const data = await api.v3Sessions.list(projectId, {
          sessionType: 'workspace',
          status: 'active',
        })
        const mapped = data.map((session) => ({
          id: session.session_id,
          title: session.workspace_name ?? null,
          updatedAt: session.last_active_at ?? new Date().toISOString(),
        }))
        setWorkspaces(mapped)
      } catch (err) {
        console.error('Failed to load workspaces:', err)
        setError('Failed to load history')
      } finally {
        setIsLoading(false)
      }
    }

    loadWorkspaces()
  }, [isOpen, projectId])

  const handleExpandConversation = async (conversationId: string) => {
    if (expandedConversationId === conversationId) {
      setExpandedConversationId(null)
      setExpandedConversationData(null)
      return
    }

    setExpandedConversationId(conversationId)
    setIsLoadingConversation(true)

    try {
      const [session, history] = await Promise.all([
        api.v3Sessions.get(conversationId),
        api.v3Sessions.history(conversationId),
      ])
      const updatedAt = session.last_active_at ?? new Date().toISOString()
      const queries = mapTurnsToQueries(conversationId, projectId, updatedAt, history.turns || [])
      setExpandedConversationData({
        id: conversationId,
        title: session.workspace_name ?? null,
        queries,
      })
    } catch (err) {
      console.error('Failed to load workspace history:', err)
      setExpandedConversationData(null)
    } finally {
      setIsLoadingConversation(false)
    }
  }

  const handleRestoreQuery = (query: QueryResponse) => {
    if (!expandedConversationData) return

    onRestoreConversation(
      expandedConversationData.id,
      expandedConversationData.queries,
      query.id,
    )
    onClose()
  }

  const handleDeleteConversation = async (conversationId: string) => {
    setIsDeleting(true)
    try {
      await api.v3Sessions.close(conversationId)
      setWorkspaces((prev) => prev.filter((workspace) => workspace.id !== conversationId))
      if (expandedConversationId === conversationId) {
        setExpandedConversationId(null)
        setExpandedConversationData(null)
      }
    } catch (err) {
      console.error('Failed to close workspace:', err)
    } finally {
      setIsDeleting(false)
      setDeleteTarget(null)
    }
  }

  if (!isOpen) return null

  return (
    <div className="w-96 h-full bg-white/95 backdrop-blur-md border-l border-slate-200/50 flex flex-col z-20 shadow-lg">
      <div className="flex items-center justify-between px-4 py-3 pt-12 border-b border-slate-200/50">
        <h2 className="text-lg font-medium text-slate-800">Workspace History</h2>
        <button
          onClick={onClose}
          className="p-1 rounded-lg hover:bg-slate-100 transition-colors"
        >
          <X size={18} className="text-slate-500" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <div className="p-4 text-center text-slate-500 text-sm">
            Loading workspaces...
          </div>
        )}

        {error && (
          <div className="p-4 text-center text-red-500 text-sm">{error}</div>
        )}

        {!isLoading && !error && workspaces.length === 0 && (
          <div className="p-4 text-center text-slate-400 text-sm">
            No workspace history yet.
          </div>
        )}

        {!isLoading && !error && workspaces.length > 0 && (
          <div className="divide-y divide-slate-100">
            {workspaces.map((workspace) => {
              const isExpanded = expandedConversationId === workspace.id

              return (
                <div key={workspace.id}>
                  <div
                    className={`
                      w-full px-4 py-3 transition-colors group cursor-pointer
                      ${isExpanded ? 'bg-cyan-50' : 'active:bg-slate-50'}
                    `}
                    onClick={() => handleExpandConversation(workspace.id)}
                    onTouchEnd={(e) => {
                      e.preventDefault()
                      handleExpandConversation(workspace.id)
                    }}
                    style={{ touchAction: 'manipulation' }}
                  >
                    <div className="flex items-center gap-3 overflow-hidden">
                      <div className="flex-1 min-w-0 flex items-center gap-3 text-left">
                        <ChevronRight
                          size={16}
                          className={`
                            text-slate-400 transition-transform
                            ${isExpanded ? 'rotate-90' : ''}
                          `}
                        />
                        <Layers size={16} className="text-cyan-500" />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-slate-700 truncate">
                            {isExpanded && expandedConversationData
                              ? getConversationTitle(expandedConversationData)
                              : (workspace.title || 'Workspace')}
                          </p>
                          <p className="text-xs text-slate-400">
                            {formatTimeAgo(workspace.updatedAt)}
                          </p>
                        </div>
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setDeleteTarget({
                            id: workspace.id,
                            title: workspace.title || 'this workspace',
                          })
                        }}
                        className="flex-shrink-0 opacity-0 group-hover:opacity-100 p-1.5 rounded-lg hover:bg-red-100 text-slate-400 hover:text-red-500 transition-all"
                        title="Close workspace"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="bg-slate-50/50 border-t border-slate-100">
                      {isLoadingConversation ? (
                        <div className="p-4 text-center text-slate-400 text-sm">
                          Loading turns...
                        </div>
                      ) : expandedConversationData ? (
                        <div className="divide-y divide-slate-100">
                          {expandedConversationData.queries.length === 0 ? (
                            <div className="p-4 text-center text-slate-400 text-sm">
                              No turns in this workspace
                            </div>
                          ) : (
                            expandedConversationData.queries.map((query, idx) => (
                              <div
                                key={query.id}
                                className="w-full px-4 py-3 active:bg-white transition-colors group flex items-start cursor-pointer"
                                onClick={() => handleRestoreQuery(query)}
                                onTouchEnd={(e) => {
                                  e.preventDefault()
                                  handleRestoreQuery(query)
                                }}
                                style={{ touchAction: 'manipulation' }}
                              >
                                <div className="flex-1 text-left">
                                  <div className="flex items-start gap-3 pl-6">
                                    <div className="flex-shrink-0 mt-0.5">
                                      <div className="w-5 h-5 rounded-full bg-cyan-100 flex items-center justify-center">
                                        <span className="text-xs font-medium text-cyan-600">
                                          {query.sequenceOrder ?? idx + 1}
                                        </span>
                                      </div>
                                    </div>
                                    <div className="flex-1 min-w-0">
                                      <p className="text-sm font-medium text-slate-700 leading-snug">
                                        {query.displayTitle || truncateText(query.queryText, 50)}
                                      </p>
                                      {query.responseText && (
                                        <p className="text-xs text-slate-500 mt-1 leading-relaxed line-clamp-2">
                                          {truncateText(query.responseText, 80)}
                                        </p>
                                      )}
                                    </div>
                                    <MessageSquare
                                      size={14}
                                      className="text-slate-300 group-hover:text-cyan-500 transition-colors mt-1"
                                    />
                                  </div>
                                </div>
                              </div>
                            ))
                          )}
                        </div>
                      ) : (
                        <div className="p-4 text-center text-red-400 text-sm">
                          Failed to load workspace history
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm animate-fade-in">
          <div className="bg-white border border-slate-200 rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 rounded-full bg-red-100">
                <Trash2 size={20} className="text-red-500" />
              </div>
              <h3 className="text-lg font-semibold text-slate-800">
                Close Workspace
              </h3>
            </div>
            <p className="text-slate-600 mb-6">
              {`Close "${deleteTarget.title}"? This removes it from active workspace history.`}
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setDeleteTarget(null)}
                disabled={isDeleting}
                className="px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-medium transition-all disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDeleteConversation(deleteTarget.id)}
                disabled={isDeleting}
                className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white text-sm font-medium transition-all flex items-center gap-2 disabled:opacity-50"
              >
                {isDeleting ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    Closing...
                  </>
                ) : (
                  'Close'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
