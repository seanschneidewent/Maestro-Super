import React, { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { ChevronDown, ChevronRight } from 'lucide-react'

interface CognitionPanelProps {
  title: string
  color: 'cyan' | 'yellow' | 'purple'
  content: string
  isActive?: boolean
  defaultExpanded?: boolean
  emptyLabel?: string
}

const COLOR_CLASSES: Record<CognitionPanelProps['color'], string> = {
  cyan: 'border-cyan-200 bg-cyan-50/60 text-cyan-700',
  yellow: 'border-amber-200 bg-amber-50/60 text-amber-700',
  purple: 'border-purple-200 bg-purple-50/60 text-purple-700',
}

export const CognitionPanel: React.FC<CognitionPanelProps> = ({
  title,
  color,
  content,
  isActive = false,
  defaultExpanded = false,
  emptyLabel = 'No activity yet.',
}) => {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const hasContent = content.trim().length > 0

  return (
    <div className={`rounded-xl border ${COLOR_CLASSES[color]} overflow-hidden transition-all duration-300`}>
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left"
      >
        {expanded ? (
          <ChevronDown size={14} className="text-slate-400" />
        ) : (
          <ChevronRight size={14} className="text-slate-400" />
        )}
        <div className="flex-1 text-xs font-semibold uppercase tracking-wide">
          {title}
        </div>
        {isActive && <span className="text-[11px] text-slate-500">active</span>}
      </button>
      {expanded && (
        <div className="px-3 pb-3 max-h-64 overflow-y-auto text-xs text-slate-700">
          {hasContent ? (
            <ReactMarkdown
              components={{
                p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                ul: ({ children }) => <ul className="list-disc ml-5 mb-2">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal ml-5 mb-2">{children}</ol>,
              }}
            >
              {content}
            </ReactMarkdown>
          ) : (
            <div className="text-slate-400">{emptyLabel}</div>
          )}
        </div>
      )}
    </div>
  )
}

interface ThinkingSectionProps {
  workspaceAssembly: string
  learning?: string
  knowledgeUpdate?: string
  isActive?: boolean
  defaultExpanded?: boolean
  learningActive?: boolean
}

export const ThinkingSection: React.FC<ThinkingSectionProps> = ({
  workspaceAssembly,
  learning = '',
  knowledgeUpdate = '',
  isActive = false,
  defaultExpanded = false,
  learningActive = false,
}) => {
  const showLearning = learning.trim().length > 0 || learningActive
  const showKnowledgeUpdate = knowledgeUpdate.trim().length > 0

  return (
    <div className="space-y-2">
      <CognitionPanel
        title="Workspace Assembly"
        color="cyan"
        content={workspaceAssembly}
        isActive={isActive}
        defaultExpanded={defaultExpanded}
      />
      {showLearning && (
        <CognitionPanel
          title="Learning"
          color="yellow"
          content={learning}
          isActive={learningActive}
          defaultExpanded={false}
          emptyLabel={learningActive ? 'Learning in progress...' : 'No activity yet.'}
        />
      )}
      {showKnowledgeUpdate && (
        <CognitionPanel
          title="Knowledge Update"
          color="purple"
          content={knowledgeUpdate}
          isActive={false}
          defaultExpanded={false}
        />
      )}
    </div>
  )
}
