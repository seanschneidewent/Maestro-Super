import React, { useState, useEffect } from 'react';
import { AppMode, DisciplineInHierarchy, ContextPointer } from '../../types';
import { PlansPanel } from './PlansPanel';
import { PlanViewer } from './PlanViewer';
import { ThinkingSection } from './ThinkingSection';
import { ModeToggle } from '../ModeToggle';
import { api, PointerResponse } from '../../lib/api';
import { Send } from 'lucide-react';
import {
  ThinkingBubble,
  HoldToTalk,
  SessionControls,
  useFieldStream,
  QueryHistoryPanel,
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
    restore(restoredTrace, restoredFinalAnswer);
    setShowHistory(false);
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

  // Handle text query submit
  const handleQuerySubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!queryInput.trim() || isStreaming) return;
    submitQuery(queryInput.trim());
    setQueryInput('');
  };

  // Handle navigation from thinking section
  const handleNavigateToPage = (pageId: string) => {
    setSelectedPageId(pageId);
  };

  return (
    <div className="h-screen w-screen flex overflow-hidden bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50 text-slate-900 font-sans relative blueprint-grid">
      {/* Left panel - PlansPanel always visible */}
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

      {/* Main viewer area */}
      <div className="flex-1 relative flex flex-col overflow-hidden">
        {/* PlanViewer - handles PDF rendering */}
        <PlanViewer
          pageId={selectedPageId}
          onPointerClick={handlePointerClick}
          selectedPointerIds={selectedPointerIds}
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

        {/* Thinking bubble - bottom left (shows thinking text or final answer) */}
        <ThinkingBubble
          isThinking={isStreaming}
          thinkingText={thinkingText}
          finalAnswer={finalAnswer}
        />

        {/* Query input bar - bottom center */}
        <form
          onSubmit={handleQuerySubmit}
          className="absolute bottom-6 left-1/2 -translate-x-1/2 z-30 w-full max-w-xl px-4"
        >
          <div className="flex items-center gap-2 bg-white/90 backdrop-blur-md border border-slate-200/50 rounded-2xl px-4 py-2 shadow-lg">
            <input
              type="text"
              value={queryInput}
              onChange={(e) => setQueryInput(e.target.value)}
              placeholder="Ask about your plans..."
              disabled={isStreaming}
              className="flex-1 bg-transparent text-slate-800 placeholder:text-slate-400 outline-none text-sm"
            />
            <button
              type="submit"
              disabled={!queryInput.trim() || isStreaming}
              className="p-2 rounded-xl bg-cyan-500 text-white hover:bg-cyan-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Send size={18} />
            </button>
          </div>
        </form>

        {/* Floating controls */}
        <HoldToTalk
          onRecordingComplete={handleRecordingComplete}
          isProcessing={isStreaming}
        />
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
