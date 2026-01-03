import React, { useState, useRef, useEffect } from 'react';
import { AppMode, FieldResponse, FieldPage, FieldPointer, FieldViewMode, DisciplineInHierarchy, ContextPointer } from '../../types';
import { PlansPanel } from './PlansPanel';
import { ModeToggle } from '../ModeToggle';
import { api } from '../../lib/api';
import {
  PageViewer,
  PageViewerHandle,
  PointerPopover,
  PageList,
  FileTreeCollapsed,
  ThinkingBubble,
  HoldToTalk,
  SessionControls,
  BackButton,
  useFieldStream,
} from '../field';

interface UseModeProps {
  mode: AppMode;
  setMode: (mode: AppMode) => void;
  projectId: string;
}

export const UseMode: React.FC<UseModeProps> = ({ mode, setMode, projectId }) => {
  // Page viewer ref
  const pageViewerRef = useRef<PageViewerHandle>(null);

  // Selected page state
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [selectedDisciplineId, setSelectedDisciplineId] = useState<string | null>(null);

  // Field mode state
  const [activePointer, setActivePointer] = useState<FieldPointer | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  // Hierarchy data for FileTreeCollapsed
  const [disciplines, setDisciplines] = useState<DisciplineInHierarchy[]>([]);

  // Rendered page PNGs cache
  const [renderedPages, setRenderedPages] = useState<Map<string, string>>(new Map());

  // Page metadata cache
  const [pageMetadata, setPageMetadata] = useState<Map<string, { title: string; pageNumber: number }>>(new Map());

  // Context pointers cache
  const [contextPointers, setContextPointers] = useState<Map<string, ContextPointer[]>>(new Map());

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
  const handlePageSelect = (pageId: string, disciplineId: string, pageName: string) => {
    setSelectedPageId(pageId);
    setSelectedDisciplineId(disciplineId);
    setActivePointer(null);
  };

  // Handle back button (exit response view)
  const handleBackButton = () => {
    resetStream();
    setActivePointer(null);
    // selectedPageId unchanged - stay on current page
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

  // Handle pointer tap on viewer
  const handlePointerTap = (pointer: FieldPointer) => {
    setActivePointer(pointer);
    pageViewerRef.current?.zoomToPointer(pointer);
  };

  // Handle page selection from response list
  const handlePageSelectFromList = (page: FieldPage) => {
    setSelectedPageId(page.id);
    setActivePointer(null);
  };

  // Handle voice recording complete
  const handleRecordingComplete = async (audioBlob: Blob) => {
    // TODO: Send to transcription API, then submit query
    // For now, just log it
    console.log('Recording complete:', audioBlob.size, 'bytes');
  };

  // Update rendered pages cache when page changes
  const handlePageRendered = (pageId: string, pngDataUrl: string) => {
    setRenderedPages(prev => {
      const next = new Map(prev);
      next.set(pageId, pngDataUrl);
      return next;
    });
  };

  // Get current page PNG
  const currentPagePng = selectedPageId ? renderedPages.get(selectedPageId) || null : null;

  return (
    <div className="h-screen w-screen flex overflow-hidden bg-slate-900">
      {/* Left panel - changes based on view mode */}
      {viewMode === 'standard' ? (
        <div className="w-72 h-full flex flex-col bg-white/90 backdrop-blur-xl border-r border-slate-200/50">
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
        <div className="flex h-full">
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

      {/* Main viewer */}
      <div className="flex-1 relative flex flex-col">
        <PageViewer
          ref={pageViewerRef}
          pngDataUrl={currentPagePng}
          pointers={viewMode === 'response' ? (currentFieldPage?.pointers || []) : []}
          activePointerId={activePointer?.id || null}
          onPointerTap={handlePointerTap}
        />

        {/* Floating controls - always visible */}
        <HoldToTalk
          onRecordingComplete={handleRecordingComplete}
          isProcessing={isStreaming}
        />
        <SessionControls
          onToggleHistory={() => setShowHistory(!showHistory)}
          isHistoryOpen={showHistory}
        />

        {/* Response mode only */}
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

        {/* Popover when pointer active */}
        {activePointer && (
          <PointerPopover
            pointer={activePointer}
            onClose={() => setActivePointer(null)}
          />
        )}

        {/* Error display */}
        {error && (
          <div className="fixed bottom-24 left-1/2 -translate-x-1/2 z-40 bg-red-500/90 text-white px-4 py-2 rounded-lg">
            {error}
          </div>
        )}
      </div>

      {/* History panel - slides in from right */}
      {showHistory && (
        <div className="w-80 h-full bg-slate-800/95 backdrop-blur-md border-l border-slate-700/50 p-4">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-medium text-white">History</h2>
            <button
              onClick={() => setShowHistory(false)}
              className="text-slate-400 hover:text-white transition-colors"
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
