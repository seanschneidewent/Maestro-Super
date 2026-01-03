import React, { useState, useRef, useEffect } from 'react';
import { AppMode, FieldResponse, FieldPage, FieldPointer, FieldViewMode, DisciplineInHierarchy, ContextPointer } from '../../types';
import { PlansPanel } from './PlansPanel';
import { PlanViewer } from './PlanViewer';
import { ModeToggle } from '../ModeToggle';
import { api, PointerResponse } from '../../lib/api';
import { Send } from 'lucide-react';
import {
  PageList,
  FileTreeCollapsed,
  ThinkingBubble,
  HoldToTalk,
  SessionControls,
  BackButton,
  PointerPopover,
  useFieldStream,
} from '../field';

interface UseModeProps {
  mode: AppMode;
  setMode: (mode: AppMode) => void;
  projectId: string;
}

export const UseMode: React.FC<UseModeProps> = ({ mode, setMode, projectId }) => {
  // Selected page state
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [selectedDisciplineId, setSelectedDisciplineId] = useState<string | null>(null);

  // Field mode state
  const [activePointer, setActivePointer] = useState<FieldPointer | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [queryInput, setQueryInput] = useState('');

  // Hierarchy data for FileTreeCollapsed
  const [disciplines, setDisciplines] = useState<DisciplineInHierarchy[]>([]);

  // Selected pointers from agent response (for PlanViewer highlighting)
  const [selectedPointerIds, setSelectedPointerIds] = useState<string[]>([]);

  // Caches for field stream (will be populated when we have rendered pages)
  const [renderedPages] = useState<Map<string, string>>(new Map());
  const [pageMetadata] = useState<Map<string, { title: string; pageNumber: number }>>(new Map());
  const [contextPointers] = useState<Map<string, ContextPointer[]>>(new Map());

  // Field stream hook
  const {
    submitQuery,
    isStreaming,
    thinkingText,
    response,
    error,
    reset: resetStream,
  } = useFieldStream({
    projectId,
    renderedPages,
    pageMetadata,
    contextPointers,
  });

  // Derived view mode
  const viewMode: FieldViewMode = response ? 'response' : 'standard';

  // Current page's pointers (in response mode)
  const currentFieldPage = response?.pages.find(p => p.id === selectedPageId);

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
    setActivePointer(null);
  };

  // Handle pointer click from PlanViewer
  const handlePointerClick = (pointer: PointerResponse) => {
    console.log('Pointer clicked:', pointer.title, pointer.id);
  };

  // Handle back button (exit response view)
  const handleBackButton = () => {
    resetStream();
    setActivePointer(null);
    setSelectedPointerIds([]);
  };

  // Handle discipline selection from collapsed tree
  const handleDisciplineSelect = (disciplineId: string) => {
    resetStream();
    setActivePointer(null);
    setSelectedDisciplineId(disciplineId);
    // Find first page in discipline and select it
    const discipline = disciplines.find(d => d.id === disciplineId);
    if (discipline && discipline.pages.length > 0) {
      setSelectedPageId(discipline.pages[0].id);
    }
  };

  // Handle page selection from response list
  const handlePageSelectFromList = (page: FieldPage) => {
    setSelectedPageId(page.id);
    setActivePointer(null);
  };

  // Handle voice recording complete
  const handleRecordingComplete = async (audioBlob: Blob) => {
    // TODO: Send to transcription API, then submit query
    console.log('Recording complete:', audioBlob.size, 'bytes');
    // For now, show a message that transcription is coming soon
  };

  // Handle text query submit
  const handleQuerySubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!queryInput.trim() || isStreaming) return;
    submitQuery(queryInput.trim());
    setQueryInput('');
  };

  return (
    <div className="h-screen w-screen flex overflow-hidden bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50 text-slate-900 font-sans relative blueprint-grid">
      {/* Left panel - changes based on view mode */}
      {viewMode === 'standard' ? (
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
      ) : (
        <div className="flex h-full z-20">
          <FileTreeCollapsed
            disciplines={disciplines}
            selectedDisciplineId={selectedDisciplineId}
            onDisciplineSelect={handleDisciplineSelect}
          />
          <PageList
            pages={response?.pages || []}
            selectedPageId={selectedPageId}
            onPageSelect={handlePageSelectFromList}
          />
        </div>
      )}

      {/* Main viewer area */}
      <div className="flex-1 relative flex flex-col overflow-hidden">
        {/* PlanViewer - handles PDF rendering */}
        <PlanViewer
          pageId={selectedPageId}
          onPointerClick={handlePointerClick}
          selectedPointerIds={selectedPointerIds}
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

        {/* Response mode overlays */}
        {viewMode === 'response' && (
          <>
            <BackButton visible={true} onBack={handleBackButton} />
            <ThinkingBubble
              isThinking={isStreaming}
              thinkingText={thinkingText}
              summary={response?.summary || ''}
            />
          </>
        )}

        {/* Thinking bubble during streaming (even in standard mode) */}
        {isStreaming && viewMode === 'standard' && (
          <ThinkingBubble
            isThinking={isStreaming}
            thinkingText={thinkingText}
            summary=""
          />
        )}

        {/* Popover when pointer active */}
        {activePointer && (
          <PointerPopover
            pointer={activePointer}
            onClose={() => setActivePointer(null)}
          />
        )}

        {/* Error display */}
        {error && (
          <div className="fixed bottom-24 left-1/2 -translate-x-1/2 z-40 bg-red-500/90 text-white px-4 py-2 rounded-lg shadow-lg">
            {error}
          </div>
        )}
      </div>

      {/* History panel - slides in from right */}
      {showHistory && (
        <div className="w-80 h-full bg-white/95 backdrop-blur-md border-l border-slate-200/50 p-4 z-20 shadow-lg">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-medium text-slate-800">History</h2>
            <button
              onClick={() => setShowHistory(false)}
              className="text-slate-400 hover:text-slate-600 transition-colors text-sm"
            >
              Close
            </button>
          </div>
          <p className="text-slate-500 text-sm">Session history coming soon...</p>
        </div>
      )}
    </div>
  );
};
