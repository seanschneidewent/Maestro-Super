import React, { useState, useEffect, useCallback, useRef } from 'react';
import { AppMode, DisciplineInHierarchy, ContextPointer, QueryWithPages, AgentTraceStep } from '../../types';
import { QueryTraceStep } from '../../lib/api';
import { PlansPanel } from './PlansPanel';
import { PlanViewer } from './PlanViewer';
import { ThinkingSection } from './ThinkingSection';
import { ModeToggle } from '../ModeToggle';
import { DemoHeader } from '../DemoHeader';
import { api, isNotFoundError } from '../../lib/api';
import { PanelLeftClose, PanelLeft } from 'lucide-react';
import { useToast } from '../ui/Toast';
import { useTutorial } from '../../hooks/useTutorial';
import {
  QueryInput,
  SessionControls,
  useFieldStream,
  QueryHistoryPanel,
  AgentSelectedPage,
  NewSessionButton,
  QueryBubbleStack,
  CompletedQuery,
  SuggestedPrompts,
} from '../field';
import { QueryResponse, QueryPageResponse } from '../../lib/api';
import { useSession } from '../../hooks/useSession';

/**
 * Extract final answer text from the query trace.
 * Looks for 'response' type step (old format) or 'reasoning' after last tool_result (new format).
 */
function extractFinalAnswerFromTrace(trace: QueryTraceStep[] | undefined): string {
  if (!trace || trace.length === 0) return '';

  // First, check for 'response' type step (contains the final answer directly)
  for (const step of trace) {
    if (step.type === 'response' && step.content) {
      return step.content;
    }
  }

  // Fallback: collect reasoning content after last tool_result (new format)
  let lastToolResultIdx = -1;
  for (let i = trace.length - 1; i >= 0; i--) {
    if (trace[i].type === 'tool_result') {
      lastToolResultIdx = i;
      break;
    }
  }

  const parts: string[] = [];
  for (let i = lastToolResultIdx + 1; i < trace.length; i++) {
    const step = trace[i];
    if (step.type === 'reasoning' && step.content) {
      parts.push(step.content);
    }
  }

  return parts.join('');
}

/**
 * Extract pointer data (including bboxes) from the query trace.
 * The select_pointers tool_result contains full pointer info.
 */
function extractPointerDataFromTrace(
  trace: QueryTraceStep[] | undefined
): Map<string, { title: string; bboxX: number; bboxY: number; bboxWidth: number; bboxHeight: number }> {
  const pointerMap = new Map<string, { title: string; bboxX: number; bboxY: number; bboxWidth: number; bboxHeight: number }>();

  if (!trace) return pointerMap;

  for (const step of trace) {
    if (step.type === 'tool_result' && step.tool === 'select_pointers') {
      const result = step.result as { pointers?: Array<{
        pointer_id: string;
        title: string;
        bbox_x: number;
        bbox_y: number;
        bbox_width: number;
        bbox_height: number;
      }> } | undefined;

      if (result?.pointers) {
        for (const p of result.pointers) {
          pointerMap.set(p.pointer_id, {
            title: p.title || '',
            bboxX: p.bbox_x || 0,
            bboxY: p.bbox_y || 0,
            bboxWidth: p.bbox_width || 0,
            bboxHeight: p.bbox_height || 0,
          });
        }
      }
    }
  }

  return pointerMap;
}

interface UseModeProps {
  mode: AppMode;
  setMode: (mode: AppMode) => void;
  projectId: string;
  onGetStarted?: () => void;
}

export const UseMode: React.FC<UseModeProps> = ({ mode, setMode, projectId, onGetStarted }) => {
  const { showError } = useToast();
  const { currentStep, completeStep, advanceStep, skipTutorial, isActive: tutorialActive, hasCompleted } = useTutorial();

  // Selected page state
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [selectedDisciplineId, setSelectedDisciplineId] = useState<string | null>(null);

  // UI state
  const [showHistory, setShowHistory] = useState(false);
  const [queryInput, setQueryInput] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState<string | null>(null);
  const [isQueryExpanded, setIsQueryExpanded] = useState(false);
  const [inputHasBeenFocused, setInputHasBeenFocused] = useState(false);
  // Start with sidebar collapsed if tutorial is on welcome step
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(
    tutorialActive && currentStep === 'welcome'
  );

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
  // Store trace data for each query so we can restore thinking section
  const [queryTraceCache] = useState<Map<string, AgentTraceStep[]>>(new Map());

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

    // Cache the full page data and trace for restoration
    queryPagesCache.set(query.queryId, query.pages);
    queryTraceCache.set(query.queryId, query.trace);

    setSessionQueries((prev) => [...prev, newQuery]);
    setActiveQueryId(query.queryId);
  }, [currentSession?.id, sessionQueries.length, queryPagesCache, queryTraceCache]);

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
    currentTool,
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

  // Handle suggested prompt selection - auto-submit
  const handleSuggestedPrompt = useCallback((prompt: string) => {
    if (isStreaming) return;
    setSubmittedQuery(prompt);
    setIsQueryExpanded(false);
    submitQuery(prompt, currentSession?.id);
  }, [isStreaming, currentSession?.id, submitQuery]);

  // Handle restoring a previous session from history
  const handleRestoreSession = (
    sessionId: string,
    queries: QueryResponse[],
    selectedQueryId: string
  ) => {
    // Convert QueryResponse[] to QueryWithPages[] for the QueryStack
    const restoredQueries: QueryWithPages[] = queries.map((q, idx) => {
      // Use API responseText, or extract from trace as fallback
      const responseText = q.responseText || extractFinalAnswerFromTrace(q.trace) || null;
      return {
        id: q.id,
        sessionId: q.sessionId ?? null,
        displayTitle: q.displayTitle ?? null,
        sequenceOrder: q.sequenceOrder ?? idx + 1,
        queryText: q.queryText,
        responseText,
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
      };
    });

    // Cache pages and traces for all queries in the session
    queryPagesCache.clear();
    queryTraceCache.clear();
    for (const q of queries) {
      // Extract pointer data (including bboxes) from trace
      const pointerData = extractPointerDataFromTrace(q.trace);

      // Cache pages with full pointer data
      if (q.pages && q.pages.length > 0) {
        const queryPages: AgentSelectedPage[] = q.pages
          .sort((a, b) => a.pageOrder - b.pageOrder)
          .map((p) => ({
            pageId: p.pageId,
            pageName: p.pageName || '',
            filePath: p.filePath || '',
            disciplineId: p.disciplineId || '',
            pointers: (p.pointersShown || []).map((ptr) => {
              // Backend sends pointer_id (snake_case), not pointerId (camelCase)
              const ptrId = (ptr as { pointer_id?: string; pointerId?: string }).pointer_id || ptr.pointerId;
              const ptrInfo = pointerData.get(ptrId);
              return {
                pointerId: ptrId,
                title: ptrInfo?.title || '',
                bboxX: ptrInfo?.bboxX || 0,
                bboxY: ptrInfo?.bboxY || 0,
                bboxWidth: ptrInfo?.bboxWidth || 0,
                bboxHeight: ptrInfo?.bboxHeight || 0,
              };
            }),
          }));
        queryPagesCache.set(q.id, queryPages);
      }
      // Cache trace
      if (q.trace && q.trace.length > 0) {
        queryTraceCache.set(q.id, q.trace as AgentTraceStep[]);
      }
    }

    // Update state
    setSessionQueries(restoredQueries);
    setActiveQueryId(selectedQueryId);

    // Set the submitted query text for the selected query
    const selectedQuery = queries.find(q => q.id === selectedQueryId);
    setSubmittedQuery(selectedQuery?.queryText ?? null);
    setIsQueryExpanded(false);

    // Restore stream state with full query data (trace, response, pages)
    setQueryInput('');
    setShowHistory(false);

    const cachedPages = queryPagesCache.get(selectedQueryId);
    // Use API responseText, or extract from trace as fallback
    const selectedResponseText = selectedQuery?.responseText || extractFinalAnswerFromTrace(selectedQuery?.trace) || '';
    restore(
      (selectedQuery?.trace || []) as AgentTraceStep[],
      selectedResponseText,
      selectedQuery?.displayTitle || null,
      cachedPages
    );
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

  // Track if tutorial has collapsed the sidebar (to detect manual expand)
  // Initialize to true if sidebar starts collapsed due to tutorial
  const tutorialCollapsedSidebarRef = useRef(tutorialActive && currentStep === 'welcome');

  // Track previous streaming state to detect when agent finishes
  const prevIsStreamingRef = useRef(isStreaming);

  // Track if history panel was opened (for tutorial flow)
  const historyOpenedRef = useRef(false);

  // Tutorial: detect sidebar expand to complete 'welcome' step
  // Only triggers when user manually expands after tutorial collapsed it
  useEffect(() => {
    if (!isSidebarCollapsed && tutorialActive && currentStep === 'welcome' && tutorialCollapsedSidebarRef.current) {
      tutorialCollapsedSidebarRef.current = false;
      completeStep('welcome');
    }
  }, [isSidebarCollapsed, tutorialActive, currentStep, completeStep]);

  // Tutorial: auto-advance from 'viewer' to 'query' after 4 seconds
  useEffect(() => {
    if (tutorialActive && currentStep === 'viewer') {
      const timer = setTimeout(() => {
        advanceStep();
      }, 4000);
      return () => clearTimeout(timer);
    }
  }, [tutorialActive, currentStep, advanceStep]);

  // Tutorial: detect streaming end → advance to 'new-session'
  useEffect(() => {
    // Streaming just ended (true → false) during 'query' step
    if (prevIsStreamingRef.current && !isStreaming && tutorialActive && currentStep === 'query') {
      // Small delay so user can see the response
      const timer = setTimeout(() => advanceStep(), 1500);
      return () => clearTimeout(timer);
    }
    prevIsStreamingRef.current = isStreaming;
  }, [isStreaming, tutorialActive, currentStep, advanceStep]);

  // Tutorial: auto-advance from 'session-intro' to 'history' after pause
  useEffect(() => {
    if (tutorialActive && currentStep === 'session-intro') {
      const timer = setTimeout(() => advanceStep(), 2500);
      return () => clearTimeout(timer);
    }
  }, [tutorialActive, currentStep, advanceStep]);

  // Tutorial: track history panel toggle → advance from 'history' when closed after opening
  useEffect(() => {
    if (tutorialActive && currentStep === 'history') {
      if (showHistory) {
        historyOpenedRef.current = true;
      } else if (historyOpenedRef.current) {
        // Panel was open, now closed
        advanceStep(); // → 'complete'
        historyOpenedRef.current = false;
      }
    }
  }, [showHistory, tutorialActive, currentStep, advanceStep]);

  // Handle page selection from PlansPanel
  // Resets to fresh session state and loads page into agent viewer
  const handlePageSelect = async (pageId: string, disciplineId: string, pageName: string) => {
    // Tutorial: complete 'sidebar' step when user selects a page
    completeStep('sidebar');

    // Reset session state (like handleNewSession but skip clearSession API call)
    resetStream();
    setQueryInput('');
    setSubmittedQuery(null);
    setIsQueryExpanded(false);
    setSessionQueries([]);
    setActiveQueryId(null);
    queryPagesCache.clear();
    queryTraceCache.clear();

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
      // Use pre-rendered PNG if available, fall back to PDF
      loadPages([{
        pageId,
        pageName: pageData.pageName,
        filePath: pageData.pageImagePath || pageData.filePath,
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
    queryTraceCache.clear();
    setSelectedPageId(null);  // Reset viewer to empty state

    // Tutorial: advance from 'new-session' step
    if (tutorialActive && currentStep === 'new-session') {
      advanceStep(); // → 'session-intro'
    }
  };

  // Handle selecting a query from the QueryStack
  const handleSelectQuery = useCallback((queryId: string) => {
    const query = sessionQueries.find((q) => q.id === queryId);
    if (!query) return;

    setActiveQueryId(queryId);
    setSubmittedQuery(query.queryText);
    setIsQueryExpanded(false);

    // Restore full query data (trace, response, pages) from cache
    const cachedPages = queryPagesCache.get(queryId);
    const cachedTrace = queryTraceCache.get(queryId);
    restore(
      cachedTrace || [],
      query.responseText || '',
      query.displayTitle || null,
      cachedPages
    );
  }, [sessionQueries, queryPagesCache, queryTraceCache, restore]);


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
            {mode === AppMode.DEMO && onGetStarted ? (
              <DemoHeader onGetStarted={onGetStarted} />
            ) : mode !== AppMode.DEMO ? (
              <ModeToggle mode={mode} setMode={setMode} variant="light" />
            ) : null}
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
          key={currentSession?.id}
          selectedPages={selectedPages}
          onVisiblePageChange={handleVisiblePageChange}
          showPointers={isStreaming || activeQueryId !== null}
          currentTool={currentTool}
          tutorialText={
            tutorialActive && currentStep === 'welcome' ? "Let me show you around." :
            tutorialActive && currentStep === 'sidebar' ? "Pick a sheet to get started." :
            tutorialActive && currentStep === 'session-intro' ? "Now we're in a new session." :
            tutorialActive && currentStep === 'history' ? "These are previous sessions" :
            tutorialActive && currentStep === 'complete' ? "That's it! I'm pretty simple. Make an account so I can be your plans expert." :
            undefined
          }
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
            data-tutorial="sidebar-expand"
          >
            <PanelLeft size={20} />
          </button>
        )}

        {/* Query bubble stack - unified list of all queries */}
        {(isStreaming || sessionQueries.length > 0 || (tutorialActive && (currentStep === 'viewer' || currentStep === 'query'))) && (
          <div className="absolute bottom-20 left-4 z-30">
            <QueryBubbleStack
              queries={sessionQueries}
              activeQueryId={activeQueryId}
              onSelectQuery={handleSelectQuery}
              isStreaming={isStreaming}
              thinkingText={thinkingText}
              streamingDisplayTitle={displayTitle}
              streamingFinalAnswer={finalAnswer}
              tutorialMessage={
                tutorialActive && currentStep === 'viewer' ? "Pinch to zoom. Drag to pan." :
                tutorialActive && currentStep === 'query' ? "Ask me anything about these plans." :
                undefined
              }
            />
          </div>
        )}

        {/* Centered sign-up button for tutorial complete step */}
        {tutorialActive && currentStep === 'complete' && onGetStarted && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-40">
            <button
              onClick={onGetStarted}
              className="pointer-events-auto px-6 py-3 bg-cyan-500 text-white rounded-xl font-medium text-lg hover:bg-cyan-600 transition-colors shadow-xl mt-24"
            >
              Create Account
            </button>
          </div>
        )}

        {/* Query input bar - bottom right */}
        <div className="absolute bottom-6 right-6 z-30 w-full max-w-xl">
          {/* Suggested prompts - show in demo mode after input focused or after tutorial */}
          {mode === AppMode.DEMO && (inputHasBeenFocused || !tutorialActive || hasCompleted) && !submittedQuery && !isStreaming && sessionQueries.length === 0 && (
            <SuggestedPrompts
              onSelectPrompt={handleSuggestedPrompt}
              disabled={isStreaming}
              showTutorialArrows={tutorialActive && inputHasBeenFocused && !hasCompleted}
            />
          )}

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
            <div className="flex-1" data-tutorial="query-input">
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
                onFocus={() => {
                  setInputHasBeenFocused(true);
                  // Don't advance step here - wait for agent response to complete
                }}
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
          showSkipTutorial={tutorialActive}
          onSkipTutorial={skipTutorial}
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
