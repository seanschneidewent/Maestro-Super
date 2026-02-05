import React, { useCallback, useRef } from 'react'
import { Plus, X } from 'lucide-react'
import type { WorkspaceSessionSummary } from '../../hooks/useSession'

interface WorkspacesPanelProps {
  sessions: WorkspaceSessionSummary[]
  activeSessionId: string | null
  isLoading?: boolean
  onCreate: (name?: string | null) => void
  onSelect: (sessionId: string) => void
  onClose: (sessionId: string) => void
}

function formatRelativeTime(timestamp?: string | null): string {
  if (!timestamp) return '?'
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return '?'

  const diffMs = Date.now() - date.getTime()
  const minutes = Math.floor(diffMs / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`

  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`

  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export const WorkspacesPanel: React.FC<WorkspacesPanelProps> = ({
  sessions,
  activeSessionId,
  isLoading = false,
  onCreate,
  onSelect,
  onClose,
}) => {
  const longPressTimer = useRef<number | null>(null)
  const swipeStateRef = useRef<{ x: number; y: number; sessionId: string; triggered: boolean } | null>(null)
  const suppressClickRef = useRef(false)

  const handleCreate = useCallback(() => {
    const name = window.prompt('Workspace name (optional)')
    if (name === null) {
      return
    }
    onCreate(name)
  }, [onCreate])

  const handleClose = useCallback((sessionId: string) => {
    const confirmed = window.confirm('Close this workspace? You can reopen it later from the list.')
    if (confirmed) {
      onClose(sessionId)
    }
  }, [onClose])

  const startLongPress = useCallback((sessionId: string) => {
    if (longPressTimer.current) {
      window.clearTimeout(longPressTimer.current)
    }
    longPressTimer.current = window.setTimeout(() => {
      suppressClickRef.current = true
      handleClose(sessionId)
    }, 650)
  }, [handleClose])

  const clearLongPress = useCallback(() => {
    if (longPressTimer.current) {
      window.clearTimeout(longPressTimer.current)
      longPressTimer.current = null
    }
  }, [])

  const startSwipe = useCallback((event: React.PointerEvent, sessionId: string) => {
    swipeStateRef.current = {
      x: event.clientX,
      y: event.clientY,
      sessionId,
      triggered: false,
    }
  }, [])

  const handleSwipeMove = useCallback((event: React.PointerEvent) => {
    const swipe = swipeStateRef.current
    if (!swipe || swipe.triggered) return

    const dx = event.clientX - swipe.x
    const dy = event.clientY - swipe.y
    const absDx = Math.abs(dx)
    const absDy = Math.abs(dy)

    if (absDx > 60 && absDx > absDy * 1.4) {
      swipe.triggered = true
      suppressClickRef.current = true
      clearLongPress()
      handleClose(swipe.sessionId)
    }
  }, [clearLongPress, handleClose])

  const endSwipe = useCallback(() => {
    swipeStateRef.current = null
  }, [])

  const workspaceCount = sessions.length

  return (
    <div className="h-full flex flex-col bg-white/90 backdrop-blur-xl border-r border-slate-200/50 shadow-lg">
      <div className="px-4 pb-4 pt-10 border-b border-slate-200/50 bg-white/60">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Workspaces</div>
            <div className="text-xl font-semibold text-slate-800">{workspaceCount}</div>
          </div>
          <button
            onClick={handleCreate}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-cyan-600 text-white text-sm font-semibold shadow-sm hover:bg-cyan-700 transition-colors"
          >
            <Plus size={16} />
            New Workspace
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-3">
        {isLoading && (
          <div className="text-sm text-slate-400 text-center py-6">Loading workspaces...</div>
        )}

        {!isLoading && sessions.length === 0 && (
          <div className="text-sm text-slate-400 text-center py-6">
            No workspaces yet.
            <div className="text-xs text-slate-300 mt-1">Create one to begin.</div>
          </div>
        )}

        <div className="space-y-2">
          {sessions.map((session) => {
            const isActive = session.session_id === activeSessionId
            const preview = session.last_message_preview?.trim() || 'No messages yet'
            const timeLabel = formatRelativeTime(session.last_active_at)
            const statusLabel = session.status === 'idle' ? 'Idle' : null

            return (
              <div
                key={session.session_id}
                onClick={() => {
                  if (suppressClickRef.current) {
                    suppressClickRef.current = false
                    return
                  }
                  onSelect(session.session_id)
                }}
                onContextMenu={(event) => {
                  event.preventDefault()
                  suppressClickRef.current = true
                  handleClose(session.session_id)
                }}
                onPointerDown={(event) => {
                  startLongPress(session.session_id)
                  startSwipe(event, session.session_id)
                }}
                onPointerMove={handleSwipeMove}
                onPointerUp={() => {
                  clearLongPress()
                  endSwipe()
                }}
                onPointerLeave={() => {
                  clearLongPress()
                  endSwipe()
                }}
                onPointerCancel={() => {
                  clearLongPress()
                  endSwipe()
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    onSelect(session.session_id)
                  }
                }}
                className={`group w-full text-left rounded-xl border px-3 py-3 transition-all duration-150 relative ${
                  isActive
                    ? 'border-cyan-300 bg-cyan-50/80 shadow-sm'
                    : 'border-slate-200/70 bg-white/70 hover:border-slate-300 hover:bg-slate-50'
                }`}
                role="button"
                tabIndex={0}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-slate-800 truncate">
                      {session.workspace_name || 'Workspace'}
                    </div>
                    <div className="text-xs text-slate-400 mt-1 line-clamp-2">
                      {preview}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <span className="text-[11px] text-slate-400">{timeLabel}</span>
                    {statusLabel && (
                      <span className="text-[10px] uppercase tracking-wide text-amber-600 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5">
                        {statusLabel}
                      </span>
                    )}
                  </div>
                </div>

                <div className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation()
                      handleClose(session.session_id)
                    }}
                    onPointerDown={(event) => {
                      event.stopPropagation()
                    }}
                    className="p-1 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-50"
                    title="Close workspace"
                    aria-label="Close workspace"
                  >
                    <X size={14} />
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
