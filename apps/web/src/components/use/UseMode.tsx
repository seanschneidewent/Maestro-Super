import React, { useState, useEffect } from 'react';
import { AppMode, DisciplineInHierarchy, ContextPointer } from '../../types';
import { PlansPanel } from './PlansPanel';
import { PlanViewer } from './PlanViewer';
import { ThinkingSection } from './ThinkingSection';
import { ModeToggle } from '../ModeToggle';
import { api, PointerResponse } from '../../lib/api';
import { PanelLeftClose, PanelLeft } from 'lucide-react';
import {
  ThinkingBubble,
  QueryInput,
  SessionControls,
  useFieldStream,
  QueryHistoryPanel,
  AgentSelectedPage,
} from '../field';
import { QueryResponse } from '../../lib/api';
import { AgentTraceStep } from '../../types';

interface UseModeProps {
  mode: AppMode;
  setMode: (mode: AppMode) => void;
  projectId: string;
}

export const UseMode: React.FC<UseModeProps> = ({ mode, setMode, projectId }) => {
  // Selected page state
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [selectedDisciplineId, setSelectedDisciplineId] = useState<string | null>(null);

  // UI state
  const [showHistory, setShowHistory] = useState(false);
  const [queryInput, setQueryInput] = useState('');
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  // Hierarchy data
  const [disciplines, setDisciplines] = useState<DisciplineInHierarchy[]>([]);

  // Selected pointers from agent response (for PlanViewer highlighting)
  const [selectedPointerIds, setSelectedPointerIds] = useState<string[]>([]);

  // Caches for field stream
  const [renderedPages] = useState<Map<string, string>>(new Map());
  const [pageMetadata] = useState<Map<string, { title: string; pageNumber: number }>>(new Map());
  const [contextPointers] = useState<Map<string, ContextPointer[]>>(new Map());

  // Field stream hook
  const {
    submitQuery,
    isStreaming,
    thinkingText,
    finalAnswer,
    trace,
    selectedPages,
    error,
    reset: resetStream,
    restore,
  } = useFieldStream({
    projectId,
    renderedPages,
    pageMetadata,
    contextPointers,
  });

  // Handle restoring a previous session from history
  const handleRestoreSession = (query: QueryResponse, restoredTrace: AgentTraceStep[], restoredFinalAnswer: string) => {
    // TODO: Extract selectedPages from restored trace if needed
    restore(restoredTrace, restoredFinalAnswer);
    setShowHistory(false);
  };

  // Handle visible page change from scrolling in multi-page mode
  const handleVisiblePageChange = (pageId: string, disciplineId: string) => {
    setSelectedPageId(pageId);
    if (disciplineId) {
      setSelectedDisciplineId(disciplineId);
    }
  };

  // Load hierarchy on mount
  useEffect(() => {
    const loadHierarchy = async () => {
      try {
        const hierarchy = await api.projects.getHierarchy(projectId);
        setDisciplines(hierarchy.disciplines);
      } catch (err) {
        console.error('Failed to load hierarchy:', err);
      }
    };
    loadHierarchy();
  }, [projectId]);

  // Handle page selection from PlansPanel
  const handlePageSelect = (pageId: string, disciplineId: string, _pageName: string) => {
    setSelectedPageId(pageId);
    setSelectedDisciplineId(disciplineId);
  };

  // Handle pointer click from PlanViewer
  const handlePointerClick = (pointer: PointerResponse) => {
    console.log('Pointer clicked:', pointer.title, pointer.id);
  };

  // Handle voice recording complete
  const handleRecordingComplete = async (audioBlob: Blob) => {
    // TODO: Send to transcription API, then submit query
    console.log('Recording complete:', audioBlob.size, 'bytes');
  };


  // Handle navigation from thinking section
  const handleNavigateToPage = (pageId: string) => {
    setSelectedPageId(pageId);
  };

  return (
    <div className="h-screen w-screen flex overflow-hidden bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50 text-slate-900 font-sans relative blueprint-grid">
      {/* Left panel - PlansPanel with collapse */}
      {!isSidebarCollapsed && (
        <div className="w-72 h-full flex flex-col bg-white/90 backdrop-blur-xl border-r border-slate-200/50 z-20 shadow-lg">
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
                onClick={() => setIsSidebarCollapsed(true)}
                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
                title="Collapse sidebar"
              >
                <PanelLeftClose size={18} />
              </button>
            </div>
          </div>

          {/* Plans Tree */}
          <div className="flex-1 overflow-hidden">
            <PlansPanel
              projectId={projectId}
              selectedPageId={selectedPageId}
              onPageSelect={handlePageSelect}
            />
          </div>
        </div>
      )}

      {/* Main viewer area */}
      <div className="flex-1 relative flex flex-col overflow-hidden">
        {/* PlanViewer - handles PDF rendering */}
        <PlanViewer
          pageId={selectedPageId}
          onPointerClick={handlePointerClick}
          selectedPointerIds={selectedPointerIds}
          selectedPages={selectedPages}
          onVisiblePageChange={handleVisiblePageChange}
        />

        {/* Thought process dropdown - top left */}
        {(isStreaming || trace.length > 0) && (
          <div className="absolute top-4 left-4 z-30 w-80 max-w-[calc(100%-2rem)]">
            <ThinkingSection
              reasoning={[]}
              isStreaming={isStreaming}
              autoCollapse={true}
              trace={trace}
              onNavigateToPage={handleNavigateToPage}
            />
          </div>
        )}

        {/* Floating expand button - shows when sidebar collapsed, below ThinkingSection */}
        {isSidebarCollapsed && (
          <button
            onClick={() => setIsSidebarCollapsed(false)}
            className="absolute top-20 left-4 z-30 p-2 rounded-xl bg-white/90 backdrop-blur-md border border-slate-200/50 shadow-lg hover:bg-slate-50 text-slate-500 hover:text-slate-700 transition-colors"
            title="Expand sidebar"
          >
            <PanelLeft size={20} />
          </button>
        )}

        {/* Thinking bubble - bottom left (thinking during stream, full answer after) */}
        <ThinkingBubble
          thinkingText={thinkingText}
          finalAnswer={finalAnswer}
          isStreaming={isStreaming}
        />

        {/* Query input bar - bottom center */}
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-30 w-full max-w-xl px-4">
          <QueryInput
            value={queryInput}
            onChange={setQueryInput}
            onSubmit={() => {
              if (queryInput.trim() && !isStreaming) {
                submitQuery(queryInput.trim());
                setQueryInput('');
              }
            }}
            onRecordingComplete={handleRecordingComplete}
            isProcessing={isStreaming}
          />
        </div>

        {/* Floating controls */}
        <SessionControls
          onToggleHistory={() => setShowHistory(!showHistory)}
          isHistoryOpen={showHistory}
        />

        {/* Error display */}
        {error && (
          <div className="fixed bottom-24 left-1/2 -translate-x-1/2 z-40 bg-red-500/90 text-white px-4 py-2 rounded-lg shadow-lg">
            {error}
          </div>
        )}
      </div>

      {/* History panel - slides in from right */}
      <QueryHistoryPanel
        projectId={projectId}
        isOpen={showHistory}
        onClose={() => setShowHistory(false)}
        onRestoreSession={handleRestoreSession}
      />
    </div>
  );
};
