import { useState, useEffect } from 'react'
import { X, ChevronRight, MessageSquare, FileText, Layers, Trash2, Loader2 } from 'lucide-react'
import { api, ConversationResponse, ConversationWithQueriesResponse, QueryResponse } from '../../lib/api'

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

function getConversationTitle(conversation: ConversationWithQueriesResponse): string {
  // Use the conversation title or fall back to first query
  if (conversation.title) {
    return conversation.title
  }
  if (conversation.queries.length > 0) {
    const firstQuery = conversation.queries[0]
    return firstQuery.displayTitle || truncateText(firstQuery.queryText, 30)
  }
  return 'Empty conversation'
}

export function QueryHistoryPanel({
  projectId,
  isOpen,
  onClose,
  onRestoreConversation,
}: QueryHistoryPanelProps) {
  const [conversations, setConversations] = useState<ConversationResponse[]>([])
  const [expandedConversationId, setExpandedConversationId] = useState<string | null>(null)
  const [expandedConversationData, setExpandedConversationData] = useState<ConversationWithQueriesResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingConversation, setIsLoadingConversation] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Delete confirmation state
  const [deleteTarget, setDeleteTarget] = useState<{
    type: 'conversation' | 'query';
    id: string;
    title: string;
  } | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  // Load conversations when panel opens
  useEffect(() => {
    if (!isOpen) return

    const loadConversations = async () => {
      setIsLoading(true)
      setError(null)
      try {
        const data = await api.conversations.list(projectId)
        setConversations(data)
      } catch (err) {
        console.error('Failed to load conversations:', err)
        setError('Failed to load history')
      } finally {
        setIsLoading(false)
      }
    }

    loadConversations()
  }, [isOpen, projectId])

  // Load conversation details when expanded
  const handleExpandConversation = async (conversationId: string) => {
    if (expandedConversationId === conversationId) {
      // Collapse if already expanded
      setExpandedConversationId(null)
      setExpandedConversationData(null)
      return
    }

    setExpandedConversationId(conversationId)
    setIsLoadingConversation(true)

    try {
      const data = await api.conversations.get(conversationId)
      setExpandedConversationData(data)
    } catch (err) {
      console.error('Failed to load conversation details:', err)
      setExpandedConversationData(null)
    } finally {
      setIsLoadingConversation(false)
    }
  }

  // Restore a conversation with a specific query selected
  const handleRestoreQuery = (query: QueryResponse) => {
    if (!expandedConversationData) return

    onRestoreConversation(
      expandedConversationData.id,
      expandedConversationData.queries,
      query.id
    )
    onClose()
  }

  // Delete a conversation (hard delete with cascade)
  const handleDeleteConversation = async (conversationId: string) => {
    setIsDeleting(true)
    try {
      await api.conversations.delete(conversationId)
      setConversations(prev => prev.filter(c => c.id !== conversationId))
      if (expandedConversationId === conversationId) {
        setExpandedConversationId(null)
        setExpandedConversationData(null)
      }
    } catch (err) {
      console.error('Failed to delete conversation:', err)
    } finally {
      setIsDeleting(false)
      setDeleteTarget(null)
    }
  }

  // Hide a query (soft delete)
  const handleHideQuery = async (queryId: string) => {
    setIsDeleting(true)
    try {
      await api.queries.hide(queryId)
      if (expandedConversationData) {
        const updatedQueries = expandedConversationData.queries.filter(q => q.id !== queryId)
        setExpandedConversationData({ ...expandedConversationData, queries: updatedQueries })
        // If no queries left, remove conversation from list
        if (updatedQueries.length === 0) {
          setConversations(prev => prev.filter(c => c.id !== expandedConversationData.id))
          setExpandedConversationId(null)
          setExpandedConversationData(null)
        }
      }
    } catch (err) {
      console.error('Failed to hide query:', err)
    } finally {
      setIsDeleting(false)
      setDeleteTarget(null)
    }
  }

  // Confirm deletion
  const handleConfirmDelete = () => {
    if (!deleteTarget) return
    if (deleteTarget.type === 'conversation') {
      handleDeleteConversation(deleteTarget.id)
    } else {
      handleHideQuery(deleteTarget.id)
    }
  }

  if (!isOpen) return null

  return (
    <div className="w-96 h-full bg-white/95 backdrop-blur-md border-l border-slate-200/50 flex flex-col z-20 shadow-lg">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 pt-[max(0.75rem,env(safe-area-inset-top))] border-b border-slate-200/50">
        <h2 className="text-lg font-medium text-slate-800">Conversation History</h2>
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
            Loading conversations...
          </div>
        )}

        {error && (
          <div className="p-4 text-center text-red-500 text-sm">{error}</div>
        )}

        {!isLoading && !error && conversations.length === 0 && (
          <div className="p-4 text-center text-slate-400 text-sm">
            No conversations yet. Start a conversation!
          </div>
        )}

        {!isLoading && !error && conversations.length > 0 && (
          <div className="divide-y divide-slate-100">
            {conversations.map((conversation) => {
              const isExpanded = expandedConversationId === conversation.id

              return (
                <div key={conversation.id}>
                  {/* Conversation header */}
                  <div
                    className={`
                      w-full px-4 py-3 transition-colors group
                      ${isExpanded ? 'bg-cyan-50' : 'hover:bg-slate-50'}
                    `}
                  >
                    <div className="flex items-center gap-3 overflow-hidden">
                      <button
                        onClick={() => handleExpandConversation(conversation.id)}
                        className="flex-1 min-w-0 flex items-center gap-3 text-left"
                      >
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
                              : (conversation.title || 'Conversation')}
                          </p>
                          <p className="text-xs text-slate-400">
                            {formatTimeAgo(conversation.createdAt)}
                          </p>
                        </div>
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setDeleteTarget({
                            type: 'conversation',
                            id: conversation.id,
                            title: conversation.title || 'this conversation',
                          })
                        }}
                        className="flex-shrink-0 opacity-0 group-hover:opacity-100 p-1.5 rounded-lg hover:bg-red-100 text-slate-400 hover:text-red-500 transition-all"
                        title="Delete conversation"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>

                  {/* Expanded conversation content */}
                  {isExpanded && (
                    <div className="bg-slate-50/50 border-t border-slate-100">
                      {isLoadingConversation ? (
                        <div className="p-4 text-center text-slate-400 text-sm">
                          Loading queries...
                        </div>
                      ) : expandedConversationData ? (
                        <div className="divide-y divide-slate-100">
                          {expandedConversationData.queries.length === 0 ? (
                            <div className="p-4 text-center text-slate-400 text-sm">
                              No queries in this conversation
                            </div>
                          ) : (
                            expandedConversationData.queries.map((query, idx) => (
                              <div
                                key={query.id}
                                className="w-full px-4 py-3 hover:bg-white transition-colors group flex items-start"
                              >
                                <button
                                  onClick={() => handleRestoreQuery(query)}
                                  className="flex-1 text-left"
                                >
                                  <div className="flex items-start gap-3 pl-6">
                                    <div className="flex-shrink-0 mt-0.5">
                                      <div className="w-5 h-5 rounded-full bg-cyan-100 flex items-center justify-center">
                                        <span className="text-xs font-medium text-cyan-600">
                                          {idx + 1}
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

                                      {/* Page sequence */}
                                      {query.pages && query.pages.length > 0 && (
                                        <div className="flex items-center gap-1 mt-2">
                                          <FileText size={12} className="text-slate-400" />
                                          <span className="text-xs text-slate-400">
                                            {query.pages.length} page{query.pages.length !== 1 ? 's' : ''}
                                          </span>
                                        </div>
                                      )}
                                    </div>
                                    <MessageSquare
                                      size={14}
                                      className="text-slate-300 group-hover:text-cyan-500 transition-colors mt-1"
                                    />
                                  </div>
                                </button>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    setDeleteTarget({
                                      type: 'query',
                                      id: query.id,
                                      title: query.displayTitle || 'this query',
                                    })
                                  }}
                                  className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-100 text-slate-400 hover:text-red-500 transition-all mt-1"
                                  title="Delete query"
                                >
                                  <X size={14} />
                                </button>
                              </div>
                            ))
                          )}
                        </div>
                      ) : (
                        <div className="p-4 text-center text-red-400 text-sm">
                          Failed to load conversation
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

      {/* Delete Confirmation Modal */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm animate-fade-in">
          <div className="bg-white border border-slate-200 rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 rounded-full bg-red-100">
                <Trash2 size={20} className="text-red-500" />
              </div>
              <h3 className="text-lg font-semibold text-slate-800">
                Delete {deleteTarget.type === 'conversation' ? 'Conversation' : 'Query'}
              </h3>
            </div>
            <p className="text-slate-600 mb-6">
              {deleteTarget.type === 'conversation'
                ? `Delete "${deleteTarget.title}" and all its queries? This cannot be undone.`
                : `Delete "${deleteTarget.title}"? This cannot be undone.`}
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
                onClick={handleConfirmDelete}
                disabled={isDeleting}
                className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white text-sm font-medium transition-all flex items-center gap-2 disabled:opacity-50"
              >
                {isDeleting ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    Deleting...
                  </>
                ) : (
                  'Delete'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
