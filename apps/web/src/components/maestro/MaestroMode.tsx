import React, { useCallback, useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { PanelLeft } from 'lucide-react'
import { AppMode } from '../../types'
import { QueryInput } from './HoldToTalk'
import { PageWorkspace } from './PageWorkspace'
import { ThinkingSection, CognitionIndicator } from './ThinkingSection'
import { WorkspacesPanel } from './WorkspacesPanel'
import { useSession } from '../../hooks/useSession'
import type { MaestroTurn } from '../../hooks/useSession'

interface MaestroModeProps {
  mode: AppMode
  setMode: (mode: AppMode) => void
  projectId: string
  onGetStarted?: () => void
}

export const MaestroMode: React.FC<MaestroModeProps> = ({ projectId }) => {
  const [queryInput, setQueryInput] = useState('')
  const [isWorkspacesOpen, setIsWorkspacesOpen] = useState(false)
  const [expandedTurns, setExpandedTurns] = useState<Set<string>>(new Set())

  const {
    activeSessionId,
    activeWorkspaceName,
    sessions,
    turns,
    workspacePages,
    isStreaming,
    isLoadingSession,
    isLoadingSessions,
    createWorkspace,
    switchWorkspace,
    closeWorkspace,
    sendMessage,
  } = useSession(projectId)

  useEffect(() => {
    setExpandedTurns(new Set())
  }, [activeSessionId])

  useEffect(() => {
    if (activeSessionId) {
      setIsWorkspacesOpen(false)
    } else if (!isLoadingSessions) {
      setIsWorkspacesOpen(true)
    }
  }, [activeSessionId, isLoadingSessions])

  const lastTurnId = useMemo(() => (turns.length ? turns[turns.length - 1].id : null), [turns])

  const handleSubmit = async () => {
    const trimmed = queryInput.trim()
    if (!trimmed || isStreaming || isLoadingSession) return
    if (!activeSessionId) {
      setIsWorkspacesOpen(true)
      return
    }
    setQueryInput('')
    await sendMessage(trimmed)
  }

  const toggleTurn = useCallback((turnId: string) => {
    if (turnId === lastTurnId) return
    setExpandedTurns((prev) => {
      const next = new Set(prev)
      if (next.has(turnId)) {
        next.delete(turnId)
      } else {
        next.add(turnId)
      }
      return next
    })
  }, [lastTurnId])

  const renderTurn = useCallback((turn: MaestroTurn) => {
    const isLatest = turn.id === lastTurnId
    const isExpanded = isLatest || expandedTurns.has(turn.id)
    const responseText = turn.response?.trim() || '...'
    const summary = responseText.length > 100 ? `${responseText.slice(0, 100)}...` : responseText

    if (!isExpanded) {
      return (
        <button
          key={turn.id}
          onClick={() => toggleTurn(turn.id)}
          className="w-full text-left border border-slate-200/70 rounded-2xl bg-white/80 backdrop-blur-md shadow-sm px-4 py-4 hover:border-slate-300 transition-all"
        >
          <div className="text-sm text-slate-700">{summary}</div>
          <div className="mt-3 flex items-center justify-between">
            <CognitionIndicator panels={turn.panels} />
            <span className="text-[11px] text-slate-400">Tap to expand</span>
          </div>
          <div className="mt-3 text-xs text-slate-500 line-clamp-2">{turn.user}</div>
        </button>
      )
    }

    return (
      <div key={turn.id} className="space-y-3">
        {!isLatest && (
          <div className="flex items-center justify-between">
            <CognitionIndicator panels={turn.panels} />
            <button
              onClick={() => toggleTurn(turn.id)}
              className="text-xs text-slate-400 hover:text-slate-600"
            >
              Collapse
            </button>
          </div>
        )}

        <div className="bg-white/90 backdrop-blur-md border border-slate-200/60 rounded-2xl shadow-sm p-4 md:p-6">
          <ReactMarkdown
            components={{
              p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
            }}
          >
            {turn.response || '...'}
          </ReactMarkdown>
        </div>

        <ThinkingSection
          workspaceAssembly={turn.panels.workspace_assembly}
          learning={turn.panels.learning}
          knowledgeUpdate={turn.panels.knowledge_update}
          isActive={turn.id === lastTurnId}
          defaultExpanded={turn.id === lastTurnId}
          learningActive={turn.learningStarted && !turn.learningDone}
        />

        <div className="flex justify-end">
          <div className="max-w-[80%] bg-blue-600 text-white rounded-2xl px-4 py-3 shadow-md">
            {turn.user}
          </div>
        </div>
      </div>
    )
  }, [expandedTurns, lastTurnId, toggleTurn])

  return (
    <div className="fixed inset-0 flex overflow-hidden bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50 text-slate-900 font-sans blueprint-grid">
      {/* Mobile overlay */}
      <div
        className={`fixed inset-0 bg-slate-900/40 transition-opacity duration-200 z-30 ${
          isWorkspacesOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'
        } lg:hidden`}
        onClick={() => setIsWorkspacesOpen(false)}
      />

      {/* Workspaces Panel */}
      <div
        className={`fixed inset-y-0 left-0 z-40 w-72 transform transition-transform duration-200 lg:static lg:translate-x-0 lg:w-80 ${
          isWorkspacesOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <WorkspacesPanel
          sessions={sessions}
          activeSessionId={activeSessionId}
          isLoading={isLoadingSessions}
          onCreate={async (name) => {
            await createWorkspace(name)
            setIsWorkspacesOpen(false)
          }}
          onSelect={async (sessionId) => {
            await switchWorkspace(sessionId)
            setIsWorkspacesOpen(false)
          }}
          onClose={closeWorkspace}
        />
      </div>

      <div className="flex-1 flex flex-col overflow-hidden relative">
        {/* Header bar */}
        <div className="flex items-center justify-between px-6 pt-6 pb-3 lg:pb-0">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsWorkspacesOpen(true)}
              className="lg:hidden p-2 rounded-xl bg-white/90 border border-slate-200/60 shadow-sm text-slate-500"
              title="Open workspaces"
            >
              <PanelLeft size={18} />
            </button>
            <div>
              <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Workspace</div>
              <div className="text-lg font-semibold text-slate-800">
                {activeWorkspaceName || (activeSessionId ? 'Workspace' : 'Select a workspace')}
              </div>
            </div>
          </div>
        </div>

        <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
          <div className="order-2 lg:order-1 flex-1 overflow-y-auto px-6 pt-4 pb-48">
            <div className="space-y-6 max-w-3xl mx-auto">
              {!activeSessionId && (
                <div className="text-slate-400 text-sm">
                  Select or create a workspace to begin.
                </div>
              )}

              {activeSessionId && turns.length === 0 && (
                <div className="text-slate-400 text-sm">
                  Ask about your plans to start this workspace.
                </div>
              )}

              {turns.map(renderTurn)}
            </div>
          </div>

          <div className="order-1 lg:order-2 w-full lg:w-[420px] border-l border-slate-200/60 bg-white/70 backdrop-blur-md">
            <PageWorkspace pages={workspacePages} className="h-full" />
          </div>
        </div>

        <div className="absolute left-6 right-6 bottom-6 z-30">
          <QueryInput
            value={queryInput}
            onChange={setQueryInput}
            onSubmit={handleSubmit}
            isProcessing={isStreaming || isLoadingSession}
            placeholder={activeSessionId ? 'Ask about your plans...' : 'Select a workspace to start'}
          />
        </div>
      </div>
    </div>
  )
}
