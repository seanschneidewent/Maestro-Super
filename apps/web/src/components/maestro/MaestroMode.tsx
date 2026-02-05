import React, { useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { PanelLeft, PanelLeftClose } from 'lucide-react'
import { AppMode } from '../../types'
import { PlansPanel } from './PlansPanel'
import { QueryInput } from './HoldToTalk'
import { PageWorkspace } from './PageWorkspace'
import { ThinkingSection } from './ThinkingSection'
import { useSession } from '../../hooks/useSession'

interface MaestroModeProps {
  mode: AppMode
  setMode: (mode: AppMode) => void
  projectId: string
  onGetStarted?: () => void
}

export const MaestroMode: React.FC<MaestroModeProps> = ({ projectId }) => {
  const [queryInput, setQueryInput] = useState('')
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(true)

  const {
    sessionId,
    turns,
    workspacePages,
    isStreaming,
    createSession,
    sendMessage,
  } = useSession()

  useEffect(() => {
    if (!projectId) return
    createSession(projectId).catch((err) => {
      console.error('Failed to create session', err)
    })
  }, [projectId, createSession])

  const handleSubmit = async () => {
    const trimmed = queryInput.trim()
    if (!trimmed || !sessionId || isStreaming) return
    setQueryInput('')
    await sendMessage(trimmed)
  }

  const lastTurnId = useMemo(() => (turns.length ? turns[turns.length - 1].id : null), [turns])

  return (
    <div className="fixed inset-0 flex overflow-hidden bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50 text-slate-900 font-sans blueprint-grid">
      {isSidebarCollapsed && (
        <button
          onClick={() => setIsSidebarCollapsed(false)}
          className="fixed left-4 top-6 z-50 p-2 rounded-xl bg-white/90 backdrop-blur-md border border-slate-200/50 shadow-lg hover:bg-slate-50 text-slate-500 hover:text-slate-700 transition-all duration-200"
          title="Expand sidebar"
        >
          <PanelLeft size={20} />
        </button>
      )}

      {!isSidebarCollapsed && (
        <div className="w-72 h-full flex flex-col bg-white/90 backdrop-blur-xl border-r border-slate-200/50 z-20 shadow-lg">
          <div className="px-4 pb-4 pt-12 border-b border-slate-200/50 bg-white/50">
            <div className="flex items-center justify-between">
              <button
                onClick={() => setIsSidebarCollapsed(true)}
                className="p-2 rounded-xl bg-white/90 backdrop-blur-md border border-slate-200/50 shadow-sm hover:bg-slate-50 text-slate-500 hover:text-slate-700 transition-all duration-200"
                title="Collapse sidebar"
              >
                <PanelLeftClose size={20} />
              </button>
              <h1 className="font-bold text-2xl text-slate-800">
                Maestro<span className="text-cyan-600">Super</span>
              </h1>
            </div>
          </div>

          <div className="flex-1 overflow-hidden">
            <PlansPanel projectId={projectId} selectedPageId={null} onPageSelect={() => {}} />
          </div>
        </div>
      )}

      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
          <div className="flex-1 overflow-y-auto px-6 pt-8 pb-48">
            <div className="space-y-6 max-w-3xl mx-auto">
              {turns.length === 0 && (
                <div className="text-slate-400 text-sm">
                  Ask about your plans to start a workspace session.
                </div>
              )}

              {turns.map((turn) => (
                <div key={turn.id} className="space-y-3">
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
                  />

                  <div className="flex justify-end">
                    <div className="max-w-[80%] bg-blue-600 text-white rounded-2xl px-4 py-3 shadow-md">
                      {turn.user}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="w-full lg:w-[420px] border-l border-slate-200/60 bg-white/70 backdrop-blur-md">
            <PageWorkspace pages={workspacePages} className="h-full" />
          </div>
        </div>

        <div className="absolute left-6 right-6 bottom-6 z-30">
          <QueryInput
            value={queryInput}
            onChange={setQueryInput}
            onSubmit={handleSubmit}
            isProcessing={isStreaming}
          />
        </div>
      </div>
    </div>
  )
}
