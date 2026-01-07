import React, { useState, useEffect, useCallback } from 'react';
import { AppMode, DisciplineInHierarchy, ContextPointer, QueryWithPages } from '../../types';
import { PlansPanel } from './PlansPanel';
import { PlanViewer } from './PlanViewer';
import { ThinkingSection } from './ThinkingSection';
import { ModeToggle } from '../ModeToggle';
import { api, isNotFoundError } from '../../lib/api';
import { PanelLeftClose, PanelLeft } from 'lucide-react';
import { useToast } from '../ui/Toast';
import {
  ActiveQueryBubble,
  QueryInput,
  SessionControls,
  useFieldStream,
  QueryHistoryPanel,
  AgentSelectedPage,
  NewSessionButton,
  QueryStack,
  CompletedQuery,
} from '../field';
import { QueryResponse, QueryPageResponse } from '../../lib/api';
import { useSession } from '../../hooks/useSession';

interface UseModeProps {
  mode: AppMode;
  setMode: (mode: AppMode) => void;
  projectId: string;
}

export const UseMode: React.FC<UseModeProps> = ({ mode, setMode, projectId }) => {
  const { showError } = useToast();

  // Selected page state
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [selectedDisciplineId, setSelectedDisciplineId] = useState<string | null>(null);

  // UI state
  const [showHistory, setShowHistory] = useState(false);
  const [queryInput, setQueryInput] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState<string | null>(null);
  const [isQueryExpanded, setIsQueryExpanded] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  // Hierarchy data
  const [disciplines, setDisciplines] = useState<DisciplineInHierarchy[]>([]);

  // Caches for field stream
  const [renderedPages] = useState<Map<string, string>>(new Map());
  const [pageMetadata] = useState<Map<string, { title: string; pageNumber: number }>>(new Map());
  const [contextPointers] = useState<Map<string, ContextPointer[]>>(new Map());

  // Session management
  const { currentSession, clearSession, isCreating: isCreatingSession } = useSession(projectId);

  // Track completed queries in the current session for QueryStack
  const [sessionQueries, setSessionQueries] = useState<QueryWithPages[]>([]);
  const [activeQueryId, setActiveQueryId] = useState<string | null>(null);
  // Store full page data for each query so we can restore it
  const [queryPagesCache] = useState<Map<string, AgentSelectedPage[]>>(new Map());

  // Callback when a query completes
  const handleQueryComplete = useCallback((query: CompletedQuery) => {
    const newQuery: QueryWithPages = {
      id: query.queryId,
      sessionId: currentSession?.id ?? null,
      displayTitle: query.displayTitle,
      sequenceOrder: sessionQueries.length + 1,
      queryText: query.queryText,
      responseText: query.finalAnswer,
      pages: query.pages.map((p, idx) => ({
        id: `${query.queryId}-page-${idx}`,
        pageId: p.pageId,
        pageOrder: idx + 1,
        pointersShown: p.pointers.map((ptr) => ({ pointerId: ptr.pointerId })),
      })),
      createdAt: new Date().toISOString(),
    };

    // Cache the full page data for restoration
    queryPagesCache.set(query.queryId, query.pages);

    setSessionQueries((prev) => [...prev, newQuery]);
    setActiveQueryId(query.queryId);
  }, [currentSession?.id, sessionQueries.length, queryPagesCache]);

  // Field stream hook
  const {
    submitQuery,
    isStreaming,
    thinkingText,
    finalAnswer,
    displayTitle,
    currentQueryId,
    trace,
    selectedPages,
    error,
    reset: resetStream,
    restore,
    loadPages,
  } = useFieldStream({
    projectId,
    renderedPages,
    pageMetadata,
    contextPointers,
    onQueryComplete: handleQueryComplete,
  });

  // Handle restoring a previous session from history
  const handleRestoreSession = (
    sessionId: string,
    queries: QueryResponse[],
    selectedQueryId: string
  ) => {
    // Convert QueryResponse[] to QueryWithPages[] for the QueryStack
    const restoredQueries: QueryWithPages[] = queries.map((q, idx) => ({
      id: q.id,
      sessionId: q.sessionId ?? null,
      displayTitle: q.displayTitle ?? null,
      sequenceOrder: q.sequenceOrder ?? idx + 1,
      queryText: q.queryText,
      responseText: q.responseText ?? null,
      pages: (q.pages || []).map((p: QueryPageResponse, pIdx: number) => ({
        id: `${q.id}-page-${pIdx}`,
        pageId: p.pageId,
        pageOrder: p.pageOrder,
        pointersShown: p.pointersShown || [],
        pageName: p.pageName,
        filePath: p.filePath,
        disciplineId: p.disciplineId,
      })),
      createdAt: q.createdAt,
    }));

    // Cache pages for all queries in the session
    queryPagesCache.clear();
    for (const q of queries) {
      if (q.pages && q.pages.length > 0) {
        const queryPages: AgentSelectedPage[] = q.pages
          .sort((a, b) => a.pageOrder - b.pageOrder)
          .map((p) => ({
            pageId: p.pageId,
            pageName: p.pageName || '',
            filePath: p.filePath || '',
            disciplineId: p.disciplineId || '',
            pointers: (p.pointersShown || []).map((ptr) => ({
              pointerId: ptr.pointerId,
              title: '',
              bboxX: 0,
              bboxY: 0,
              bboxWidth: 0,
              bboxHeight: 0,
            })),
          }));
        queryPagesCache.set(q.id, queryPages);
      }
    }

    // Update state
    setSessionQueries(restoredQueries);
    setActiveQueryId(selectedQueryId);

    // Set the submitted query text for the selected query
    const selectedQuery = queries.find(q => q.id === selectedQueryId);
    setSubmittedQuery(selectedQuery?.queryText ?? null);
    setIsQueryExpanded(false);

    // Reset stream state BEFORE loading pages (resetStream clears selectedPages)
    resetStream();
    setQueryInput('');
    setShowHistory(false);

    // Load pages for the selected query from cache (must be AFTER resetStream)
    const cachedPages = queryPagesCache.get(selectedQueryId);
    if (cachedPages) {
      loadPages(cachedPages);
    }
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
  // Resets to fresh session state and loads page into agent viewer
  const handlePageSelect = async (pageId: string, disciplineId: string, pageName: string) => {
    // Reset session state (like handleNewSession but skip clearSession API call)
    resetStream();
    setQueryInput('');
    setSubmittedQuery(null);
    setIsQueryExpanded(false);
    setSessionQueries([]);
    setActiveQueryId(null);
    queryPagesCache.clear();

    // Set sidebar highlighting
    setSelectedPageId(pageId);
    setSelectedDisciplineId(disciplineId);

    // Helper to fetch page with retry on 404 (connection pool stale state fix)
    const fetchPageWithRetry = async (retries = 1): Promise<typeof api.pages.get extends (id: string) => Promise<infer R> ? R : never> => {
      try {
        return await api.pages.get(pageId);
      } catch (err) {
        if (isNotFoundError(err) && retries > 0) {
          // Wait 500ms and retry - connection pool might have stale state
          await new Promise(resolve => setTimeout(resolve, 500));
          return fetchPageWithRetry(retries - 1);
        }
        throw err;
      }
    };

    // Fetch page data (skip pointers - not shown for file tree navigation)
    try {
      const pageData = await fetchPageWithRetry();

      // Load into viewer without pointers (clean sheet browsing)
      loadPages([{
        pageId,
        pageName: pageData.pageName,
        filePath: pageData.filePath,
        disciplineId,
        pointers: [], // Empty - pointers only shown for query results
      }]);
    } catch (err) {
      console.error('Failed to load page for viewer:', err);
      if (isNotFoundError(err)) {
        showError(`Page "${pageName}" not found. Try refreshing the page list.`);
      } else {
        showError('Failed to load page. Please try again.');
      }
    }
  };

  // Handle starting a new session (clears query stack)
  const handleNewSession = async () => {
    await clearSession();
    resetStream();
    setQueryInput('');
    setSubmittedQuery(null);
    setIsQueryExpanded(false);
    setSessionQueries([]);
    setActiveQueryId(null);
    queryPagesCache.clear();
    setSelectedPageId(null);  // Reset viewer to empty state
  };

  // Handle selecting a query from the QueryStack
  const handleSelectQuery = useCallback((queryId: string) => {
    const query = sessionQueries.find((q) => q.id === queryId);
    if (!query) return;

    setActiveQueryId(queryId);
    setSubmittedQuery(query.queryText);
    setIsQueryExpanded(false);

    // Restore pages from cache
    const cachedPages = queryPagesCache.get(queryId);
    if (cachedPages) {
      loadPages(cachedPages);
    }
  }, [sessionQueries, queryPagesCache, loadPages]);


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
          selectedPages={selectedPages}
          onVisiblePageChange={handleVisiblePageChange}
          showPointers={isStreaming || activeQueryId !== null}
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

        {/* Query history stack - shows previous queries (not the active one) */}
        {sessionQueries.length > 1 && (
          <div className="absolute bottom-32 left-4 z-30">
            <QueryStack
              queries={sessionQueries}
              activeQueryId={activeQueryId}
              onSelectQuery={handleSelectQuery}
            />
          </div>
        )}

        {/* Active query bubble - shows streaming state, then transforms into completed response */}
        {(isStreaming || sessionQueries.length > 0) && (
          <div className="absolute bottom-20 left-4 z-30">
            <ActiveQueryBubble
              isStreaming={isStreaming}
              thinkingText={thinkingText}
              displayTitle={displayTitle}
              finalAnswer={finalAnswer}
              activeQuery={
                activeQueryId
                  ? sessionQueries.find(q => q.id === activeQueryId) ?? null
                  : sessionQueries[sessionQueries.length - 1] ?? null
              }
            />
          </div>
        )}

        {/* Query input bar - bottom center */}
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-30 w-full max-w-xl px-4">
          {/* User query bubble - appears above input when query is active */}
          {submittedQuery && (isStreaming || activeQueryId) && (() => {
            const words = submittedQuery.split(/\s+/);
            const isLong = words.length > 7;
            const truncatedText = isLong ? words.slice(0, 7).join(' ') : submittedQuery;
            const showFade = isLong && !isQueryExpanded;

            return (
              <div className="flex justify-end mb-2">
                <button
                  onClick={() => isLong && setIsQueryExpanded(!isQueryExpanded)}
                  className={`
                    bg-blue-600 text-white rounded-2xl px-4 py-2 text-sm shadow-lg max-w-[80%]
                    text-left relative overflow-hidden
                    ${isLong ? 'cursor-pointer hover:bg-blue-700' : 'cursor-default'}
                    transition-colors
                  `}
                >
                  <span className={showFade ? 'line-clamp-1' : ''}>
                    {isQueryExpanded || !isLong ? submittedQuery : truncatedText}
                  </span>
                  {showFade && (
                    <span className="absolute right-0 top-0 bottom-0 w-16 bg-gradient-to-l from-blue-600 to-transparent pointer-events-none" />
                  )}
                </button>
              </div>
            );
          })()}

          <div className="flex items-center gap-3">
            <div className="flex-1">
              <QueryInput
                value={queryInput}
                onChange={setQueryInput}
                onSubmit={() => {
                  if (queryInput.trim() && !isStreaming) {
                    setSubmittedQuery(queryInput.trim());
                    setIsQueryExpanded(false);
                    submitQuery(queryInput.trim(), currentSession?.id);
                    setQueryInput('');
                  }
                }}
                isProcessing={isStreaming}
              />
            </div>
            <NewSessionButton
              onClick={handleNewSession}
              disabled={isStreaming || isCreatingSession}
            />
          </div>
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
