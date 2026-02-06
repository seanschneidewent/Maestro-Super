import React, { useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { V3ThinkingPanel } from '../../types/v3'

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

const PANEL_META: Array<{
  key: V3ThinkingPanel
  label: string
  color: string
}> = [
  { key: 'workspace_assembly', label: 'Assembly', color: 'bg-cyan-500' },
  { key: 'learning', label: 'Learning', color: 'bg-amber-500' },
  { key: 'knowledge_update', label: 'Knowledge', color: 'bg-purple-500' },
]

interface CognitionIndicatorProps {
  panels: Record<V3ThinkingPanel, string>
  learningActive?: boolean
  className?: string
}

export const CognitionIndicator: React.FC<CognitionIndicatorProps> = ({
  panels,
  learningActive = false,
  className,
}) => {
  const dots = useMemo(() => {
    return PANEL_META.map((panel) => {
      const hasContent = panels[panel.key]?.trim().length > 0
      const isActive = panel.key === 'learning' ? hasContent || learningActive : hasContent
      return { ...panel, isActive }
    })
  }, [panels, learningActive])

  return (
    <div className={`flex items-center gap-1.5 ${className ?? ''}`}>
      {dots.map((dot) => (
        <span key={dot.key} className="flex items-center gap-1">
          <span
            className={`h-2.5 w-2.5 rounded-full ${dot.isActive ? dot.color : 'bg-slate-300'}`}
            title={dot.label}
          />
        </span>
      ))}
    </div>
  )
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
  return (
    <div className="space-y-2">
      <CognitionPanel
        title="Workspace Assembly"
        color="cyan"
        content={workspaceAssembly}
        isActive={isActive}
        defaultExpanded={defaultExpanded}
      />
      <CognitionPanel
        title="Learning"
        color="yellow"
        content={learning}
        isActive={learningActive}
        defaultExpanded={false}
        emptyLabel={learningActive ? 'Learning in progress...' : 'No activity yet.'}
      />
      <CognitionPanel
        title="Knowledge Update"
        color="purple"
        content={knowledgeUpdate}
        isActive={false}
        defaultExpanded={false}
      />
    </div>
  )
}
