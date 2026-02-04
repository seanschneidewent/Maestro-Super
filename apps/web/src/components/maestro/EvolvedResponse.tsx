/**
 * EvolvedResponse — shows the incrementally-built response from the Maestro Orchestrator.
 *
 * As each per-page Deep agent completes, the evolved response text grows.
 * This component renders the current version with a subtle version badge
 * so the superintendent sees the answer improving in real time.
 */

import { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import type { PageAgentState, LearningNote } from '../../hooks/useQueryManager'

interface EvolvedResponseProps {
  text: string
  version: number
  pageAgentStates: PageAgentState[]
  learningNotes: LearningNote[]
  isStreaming: boolean
}

function EvolvedResponseInner({
  text,
  version,
  pageAgentStates,
  learningNotes,
  isStreaming,
}: EvolvedResponseProps) {
  const doneCount = pageAgentStates.filter(p => p.state === 'done').length
  const totalCount = pageAgentStates.length

  if (!text && !learningNotes.length && !pageAgentStates.length) return null

  return (
    <div className="space-y-3">
      {/* Learning notes */}
      {learningNotes.length > 0 && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 space-y-1">
          {learningNotes.map((note, i) => (
            <div key={i} className="flex items-start gap-2 text-sm text-amber-200/80">
              <span className="text-amber-400 mt-0.5 shrink-0">&#x1F4A1;</span>
              <span>{note.text}</span>
            </div>
          ))}
        </div>
      )}

      {/* Page agent progress */}
      {pageAgentStates.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {pageAgentStates.map((page) => (
            <div
              key={page.pageId}
              className={`
                inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium
                transition-colors duration-300
                ${page.state === 'done'
                  ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/20'
                  : page.state === 'processing'
                    ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/20 animate-pulse'
                    : 'bg-slate-500/15 text-slate-400 border border-slate-500/20'
                }
              `}
            >
              {page.state === 'processing' && (
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping" />
              )}
              {page.state === 'done' && (
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              )}
              <span className="truncate max-w-[120px]">{page.pageName}</span>
            </div>
          ))}
        </div>
      )}

      {/* Evolved response text */}
      {text && (
        <div className="relative">
          <div className="prose prose-invert prose-sm max-w-none text-slate-200/90">
            <ReactMarkdown>{text}</ReactMarkdown>
          </div>
          {isStreaming && totalCount > 0 && (
            <div className="mt-2 flex items-center gap-2 text-xs text-slate-400">
              <span>{doneCount}/{totalCount} sheets analyzed</span>
              {version > 0 && <span className="text-slate-500">v{version}</span>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export const EvolvedResponse = memo(EvolvedResponseInner)
