import { useState, useEffect } from 'react'
import { X, ChevronRight, MessageSquare, FileText, Layers } from 'lucide-react'
import { api, SessionResponse, SessionWithQueriesResponse, QueryResponse } from '../../lib/api'

interface QueryHistoryPanelProps {
  projectId: string
  isOpen: boolean
  onClose: () => void
  onRestoreSession: (
    sessionId: string,
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

function getSessionTitle(session: SessionWithQueriesResponse): string {
  // Use the first query's display title or query text
  if (session.queries.length > 0) {
    const firstQuery = session.queries[0]
    return firstQuery.displayTitle || truncateText(firstQuery.queryText, 30)
  }
  return 'Empty session'
}

export function QueryHistoryPanel({
  projectId,
  isOpen,
  onClose,
  onRestoreSession,
}: QueryHistoryPanelProps) {
  const [sessions, setSessions] = useState<SessionResponse[]>([])
  const [expandedSessionId, setExpandedSessionId] = useState<string | null>(null)
  const [expandedSessionData, setExpandedSessionData] = useState<SessionWithQueriesResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingSession, setIsLoadingSession] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Load sessions when panel opens
  useEffect(() => {
    if (!isOpen) return

    const loadSessions = async () => {
      setIsLoading(true)
      setError(null)
      try {
        const data = await api.sessions.list(projectId)
        setSessions(data)
      } catch (err) {
        console.error('Failed to load sessions:', err)
        setError('Failed to load history')
      } finally {
        setIsLoading(false)
      }
    }

    loadSessions()
  }, [isOpen, projectId])

  // Load session details when expanded
  const handleExpandSession = async (sessionId: string) => {
    if (expandedSessionId === sessionId) {
      // Collapse if already expanded
      setExpandedSessionId(null)
      setExpandedSessionData(null)
      return
    }

    setExpandedSessionId(sessionId)
    setIsLoadingSession(true)

    try {
      const data = await api.sessions.get(sessionId)
      setExpandedSessionData(data)
    } catch (err) {
      console.error('Failed to load session details:', err)
      setExpandedSessionData(null)
    } finally {
      setIsLoadingSession(false)
    }
  }

  // Restore a session with a specific query selected
  const handleRestoreQuery = (query: QueryResponse) => {
    if (!expandedSessionData) return

    onRestoreSession(
      expandedSessionData.id,
      expandedSessionData.queries,
      query.id
    )
    onClose()
  }

  if (!isOpen) return null

  return (
    <div className="w-96 h-full bg-white/95 backdrop-blur-md border-l border-slate-200/50 flex flex-col z-20 shadow-lg">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200/50">
        <h2 className="text-lg font-medium text-slate-800">Session History</h2>
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
            Loading sessions...
          </div>
        )}

        {error && (
          <div className="p-4 text-center text-red-500 text-sm">{error}</div>
        )}

        {!isLoading && !error && sessions.length === 0 && (
          <div className="p-4 text-center text-slate-400 text-sm">
            No sessions yet. Start a conversation!
          </div>
        )}

        {!isLoading && !error && sessions.length > 0 && (
          <div className="divide-y divide-slate-100">
            {sessions.map((session) => {
              const isExpanded = expandedSessionId === session.id

              return (
                <div key={session.id}>
                  {/* Session header */}
                  <button
                    onClick={() => handleExpandSession(session.id)}
                    className={`
                      w-full px-4 py-3 text-left transition-colors
                      ${isExpanded ? 'bg-cyan-50' : 'hover:bg-slate-50'}
                    `}
                  >
                    <div className="flex items-center gap-3">
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
                          {isExpanded && expandedSessionData
                            ? getSessionTitle(expandedSessionData)
                            : (session.title || 'Session')}
                        </p>
                        <p className="text-xs text-slate-400">
                          {formatTimeAgo(session.createdAt)}
                        </p>
                      </div>
                    </div>
                  </button>

                  {/* Expanded session content */}
                  {isExpanded && (
                    <div className="bg-slate-50/50 border-t border-slate-100">
                      {isLoadingSession ? (
                        <div className="p-4 text-center text-slate-400 text-sm">
                          Loading queries...
                        </div>
                      ) : expandedSessionData ? (
                        <div className="divide-y divide-slate-100">
                          {expandedSessionData.queries.length === 0 ? (
                            <div className="p-4 text-center text-slate-400 text-sm">
                              No queries in this session
                            </div>
                          ) : (
                            expandedSessionData.queries.map((query, idx) => (
                              <button
                                key={query.id}
                                onClick={() => handleRestoreQuery(query)}
                                className="w-full px-4 py-3 text-left hover:bg-white transition-colors group"
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
                            ))
                          )}
                        </div>
                      ) : (
                        <div className="p-4 text-center text-red-400 text-sm">
                          Failed to load session
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
    </div>
  )
}
