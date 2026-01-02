import React, { useState } from 'react';
import { AppMode } from '../../types';
import { Folder, ChevronLeft, ChevronRight, Bot } from 'lucide-react';
import { AgentPanel } from './AgentPanel';
import { PlansPanel } from './PlansPanel';
import { PlanViewer } from './PlanViewer';
import { ModeToggle } from '../ModeToggle';
import { PointerResponse } from '../../lib/api';

interface UseModeProps {
  mode: AppMode;
  setMode: (mode: AppMode) => void;
  projectId: string;
}

export const UseMode: React.FC<UseModeProps> = ({ mode, setMode, projectId }) => {
  // Panel visibility state
  const [showPlansPanel, setShowPlansPanel] = useState(true);
  const [showAgentPanel, setShowAgentPanel] = useState(true);

  // Selected page state
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [selectedDisciplineId, setSelectedDisciplineId] = useState<string | null>(null);

  // Handle page selection from PlansPanel
  const handlePageSelect = (pageId: string, disciplineId: string, pageName: string) => {
    setSelectedPageId(pageId);
    setSelectedDisciplineId(disciplineId);
  };

  // Handle navigation from agent (for Phase 2)
  const handleNavigateToPage = (pageId: string) => {
    setSelectedPageId(pageId);
  };

  // Handle pointer click from PlanViewer
  const handlePointerClick = (pointer: PointerResponse) => {
    // For now, just log - in Phase 2 we might show a modal or pass to agent
    console.log('Pointer clicked:', pointer.title, pointer.id);
  };


  return (
    <div className="flex h-full w-full bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50 text-slate-900 overflow-hidden font-sans relative blueprint-grid">

      {/* LEFT PANEL: Plans Tree */}
      <div
        className={`absolute left-0 top-0 bottom-0 bg-white/90 backdrop-blur-xl border-r border-slate-200/50 transition-all duration-300 ease-out z-20 shadow-elevation-3 ${
          showPlansPanel ? 'translate-x-0 w-72' : '-translate-x-full w-72'
        }`}
      >
        {/* Header */}
        <div className="px-4 py-3 border-b border-slate-200/50 bg-white/50 space-y-3">
          <ModeToggle mode={mode} setMode={setMode} variant="light" />
          <div className="flex items-center justify-between">
            <div>
              <h1 className="font-bold text-lg text-slate-800">
                Maestro<span className="text-cyan-600">Super</span>
              </h1>
              <p className="text-xs text-slate-500">Field Mode</p>
            </div>
            <button
              onClick={() => setShowPlansPanel(false)}
              className="p-2 hover:bg-slate-100 rounded-lg text-slate-400 hover:text-slate-600 transition-colors"
            >
              <ChevronLeft size={18} />
            </button>
          </div>
        </div>

        {/* Plans Tree */}
        <div className="h-[calc(100%-5rem)]">
          <PlansPanel
            projectId={projectId}
            selectedPageId={selectedPageId}
            onPageSelect={handlePageSelect}
          />
        </div>
      </div>

      {/* RIGHT PANEL: Agent Chat */}
      <div
        className={`absolute right-0 top-0 bottom-0 transition-all duration-300 ease-out z-20 ${
          showAgentPanel ? 'translate-x-0 w-[400px]' : 'translate-x-full w-[400px]'
        }`}
      >
        <AgentPanel
          projectId={projectId}
          onNavigateToPage={handleNavigateToPage}
          onOpenPointer={(pointerId) => console.log('Open pointer:', pointerId)}
        />
      </div>

      {/* CENTER: Plan Viewer */}
      <div
        className="flex-1 h-full relative overflow-hidden flex flex-col transition-all duration-300 ease-out"
        style={{
          marginLeft: showPlansPanel ? '18rem' : '0',
          marginRight: showAgentPanel ? '400px' : '0',
        }}
      >
        {/* Edge Toggle - Plans Panel */}
        {!showPlansPanel && (
          <button
            onClick={() => setShowPlansPanel(true)}
            className="absolute left-0 top-1/2 -translate-y-1/2 z-30 bg-white/90 backdrop-blur-sm border border-l-0 border-slate-200/50 shadow-elevation-2 rounded-r-2xl py-10 px-2 hover:bg-slate-50 group transition-all duration-200"
          >
            <span className="writing-vertical text-xs font-bold text-slate-500 group-hover:text-cyan-600 uppercase tracking-widest flex items-center gap-2">
              <Folder size={14} className="rotate-90" /> Plans
            </span>
          </button>
        )}

        {/* Edge Toggle - Agent Panel */}
        {!showAgentPanel && (
          <button
            onClick={() => setShowAgentPanel(true)}
            className="absolute right-0 top-1/2 -translate-y-1/2 z-30 bg-gradient-to-l from-cyan-500 to-cyan-600 text-white shadow-glow-cyan rounded-l-2xl py-10 px-2 hover:from-cyan-400 hover:to-cyan-500 group transition-all duration-200"
          >
            <span className="writing-vertical text-xs font-bold uppercase tracking-widest flex items-center gap-2">
              <Bot size={14} className="rotate-90" /> AI Agent
            </span>
          </button>
        )}

        {/* Close button for Agent Panel (inside center area) */}
        {showAgentPanel && (
          <button
            onClick={() => setShowAgentPanel(false)}
            className="absolute right-2 top-4 z-30 p-2 bg-white/80 hover:bg-white rounded-lg shadow-sm text-slate-500 hover:text-slate-700 transition-all"
          >
            <ChevronRight size={18} />
          </button>
        )}

        {/* Plan Viewer */}
        <PlanViewer
          pageId={selectedPageId}
          onPointerClick={handlePointerClick}
        />
      </div>
    </div>
  );
};
