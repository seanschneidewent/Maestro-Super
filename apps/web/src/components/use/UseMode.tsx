import React, { useState, useEffect, useCallback, useRef } from 'react';
import { AppMode, DisciplineInHierarchy, ContextPointer, QueryWithPages, AgentTraceStep } from '../../types';
import { QueryTraceStep } from '../../lib/api';
import { PlansPanel } from './PlansPanel';
import { FeedViewer, FeedItem } from './FeedViewer';
import { ModeToggle } from '../ModeToggle';
import { DemoHeader } from '../DemoHeader';
import { api, isNotFoundError } from '../../lib/api';
import { PanelLeftClose, PanelLeft, FileText, MessageSquare } from 'lucide-react';
import { useToast } from '../ui/Toast';
import { useTutorial } from '../../hooks/useTutorial';
import {
  QueryInput,
  SessionControls,
  useFieldStream,
  QueryHistoryPanel,
  AgentSelectedPage,
  NewConversationButton,
  CompletedQuery,
  SuggestedPrompts,
} from '../field';
import { QueryResponse, QueryPageResponse } from '../../lib/api';
import { useConversation } from '../../hooks/useConversation';

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

  // Response mode: 'pages' shows plan pages, 'conversational' gives text-only answers
  const [responseMode, setResponseMode] = useState<'pages' | 'conversational'>('pages');

  // Hierarchy data
  const [disciplines, setDisciplines] = useState<DisciplineInHierarchy[]>([]);

  // Caches for field stream
  const [renderedPages] = useState<Map<string, string>>(new Map());
  const [pageMetadata] = useState<Map<string, { title: string; pageNumber: number }>>(new Map());
  const [contextPointers] = useState<Map<string, ContextPointer[]>>(new Map());

  // Conversation management
  const { currentConversation, clearConversation, isCreating: isCreatingConversation } = useConversation(projectId);

  // Track completed queries in the current conversation for QueryStack
  const [conversationQueries, setConversationQueries] = useState<QueryWithPages[]>([]);
  const [activeQueryId, setActiveQueryId] = useState<string | null>(null);
  // Store full page data for each query so we can restore it
  const [queryPagesCache] = useState<Map<string, AgentSelectedPage[]>>(new Map());
  // Store trace data for each query so we can restore thinking section
  const [queryTraceCache] = useState<Map<string, AgentTraceStep[]>>(new Map());

  // Feed items for vertical scroll view
  const [feedItems, setFeedItems] = useState<FeedItem[]>([]);

  // Track previous streaming state to detect completion
  const wasStreamingRef = useRef(false);

  // Callback when a query completes
  const handleQueryComplete = useCallback((query: CompletedQuery) => {
    const newQuery: QueryWithPages = {
      id: query.queryId,
      conversationId: currentConversation?.id ?? null,
      displayTitle: query.displayTitle,
      sequenceOrder: conversationQueries.length + 1,
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

    setConversationQueries((prev) => [...prev, newQuery]);
    setActiveQueryId(query.queryId);
  }, [currentConversation?.id, conversationQueries.length, queryPagesCache, queryTraceCache]);

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

  // Detect streaming completion and add pages/text to feed
  useEffect(() => {
    // Streaming just ended (true → false)
    if (wasStreamingRef.current && !isStreaming) {
      // Add pages if we have them
      if (selectedPages.length > 0) {
        setFeedItems((prev) => [
          ...prev,
          {
            type: 'pages',
            id: crypto.randomUUID(),
            pages: selectedPages,
            timestamp: Date.now(),
          },
        ]);

        // Auto-switch to conversational mode after showing pages
        if (responseMode === 'pages') {
          setResponseMode('conversational');
        }
      }
      // Add text response if we have one (show below pages as conversational output)
      if (finalAnswer) {
        setFeedItems((prev) => [
          ...prev,
          {
            type: 'text',
            id: crypto.randomUUID(),
            content: finalAnswer,
            trace: [...trace],  // Include trace for ThinkingSection
            timestamp: Date.now(),
          },
        ]);
      }
    }
    wasStreamingRef.current = isStreaming;
  }, [isStreaming, selectedPages, finalAnswer, trace, responseMode]);

  // Handle suggested prompt selection - auto-submit
  const handleSuggestedPrompt = useCallback((prompt: string) => {
    if (isStreaming) return;
    // Add user query to feed
    setFeedItems((prev) => [
      ...prev,
      {
        type: 'user-query',
        id: crypto.randomUUID(),
        text: prompt,
        timestamp: Date.now(),
      },
    ]);
    setSubmittedQuery(prompt);
    setIsQueryExpanded(false);
    submitQuery(prompt, currentConversation?.id, responseMode);
  }, [isStreaming, currentConversation?.id, submitQuery, responseMode]);

  // Handle restoring a previous conversation from history
  const handleRestoreConversation = (
    conversationId: string,
    queries: QueryResponse[],
    selectedQueryId: string
  ) => {
    // Convert QueryResponse[] to QueryWithPages[] for the QueryStack
    const restoredQueries: QueryWithPages[] = queries.map((q, idx) => {
      // Use API responseText, or extract from trace as fallback
      const responseText = q.responseText || extractFinalAnswerFromTrace(q.trace) || null;
      return {
        id: q.id,
        conversationId: q.conversationId ?? null,
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

    // Cache pages and traces for all queries in the conversation
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
    setConversationQueries(restoredQueries);
    setActiveQueryId(selectedQueryId);

    // Rebuild feedItems from conversation history up to selected query
    const selectedQueryIndex = queries.findIndex(q => q.id === selectedQueryId);
    const queriesToShow = queries.slice(0, selectedQueryIndex + 1);

    const newFeedItems: FeedItem[] = [];
    for (const q of queriesToShow) {
      // Add user query
      newFeedItems.push({
        type: 'user-query',
        id: `feed-query-${q.id}`,
        text: q.queryText,
        timestamp: new Date(q.createdAt).getTime(),
      });

      // Add pages if available
      const cachedPages = queryPagesCache.get(q.id);
      if (cachedPages && cachedPages.length > 0) {
        newFeedItems.push({
          type: 'pages',
          id: `feed-pages-${q.id}`,
          pages: cachedPages,
          timestamp: new Date(q.createdAt).getTime() + 1,
        });
      }

      // Add text response if available
      const responseText = q.responseText || extractFinalAnswerFromTrace(q.trace);
      const cachedTrace = queryTraceCache.get(q.id);
      if (responseText) {
        newFeedItems.push({
          type: 'text',
          id: `feed-text-${q.id}`,
          content: responseText,
          trace: (cachedTrace || []) as AgentTraceStep[],
          timestamp: new Date(q.createdAt).getTime() + 2,
        });
      }
    }

    setFeedItems(newFeedItems);

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

  // Tutorial: detect streaming end → advance from 'responding' to 'new-conversation'
  useEffect(() => {
    // Streaming just ended (true → false) during 'responding' step
    if (prevIsStreamingRef.current && !isStreaming && tutorialActive && currentStep === 'responding') {
      // Small delay so user can see the response before showing next arrow
      const timer = setTimeout(() => advanceStep(), 1500);
      return () => clearTimeout(timer);
    }
    prevIsStreamingRef.current = isStreaming;
  }, [isStreaming, tutorialActive, currentStep, advanceStep]);

  // Tutorial: auto-advance from 'conversation-intro' to 'history' after pause
  useEffect(() => {
    if (tutorialActive && currentStep === 'conversation-intro') {
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
  // Resets to fresh conversation state and loads page into agent viewer
  const handlePageSelect = async (pageId: string, disciplineId: string, pageName: string) => {
    // Tutorial: complete 'sidebar' step when user selects a page
    completeStep('sidebar');

    // Reset conversation state (like handleNewConversation but skip clearConversation API call)
    resetStream();
    setQueryInput('');
    setSubmittedQuery(null);
    setIsQueryExpanded(false);
    setConversationQueries([]);
    setActiveQueryId(null);
    queryPagesCache.clear();
    queryTraceCache.clear();
    setFeedItems([]);

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
      const pageToLoad = {
        pageId,
        pageName: pageData.pageName,
        filePath: pageData.pageImagePath || pageData.filePath,
        disciplineId,
        pointers: [], // Empty - pointers only shown for query results
      };

      loadPages([pageToLoad]);

      // Add as standalone page for full-screen zoomable viewing
      // (Different from 'pages' type which shows thumbnails for query results)
      setFeedItems([{
        type: 'standalone-page',
        id: crypto.randomUUID(),
        page: pageToLoad,
        timestamp: Date.now(),
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

  // Handle starting a new conversation (clears query stack)
  const handleNewConversation = async () => {
    await clearConversation();
    resetStream();
    setQueryInput('');
    setSubmittedQuery(null);
    setIsQueryExpanded(false);
    setInputHasBeenFocused(false);  // Reset so prompts don't reappear
    setConversationQueries([]);
    setActiveQueryId(null);
    queryPagesCache.clear();
    queryTraceCache.clear();
    setSelectedPageId(null);  // Reset viewer to empty state
    setFeedItems([]);  // Clear feed
    setResponseMode('pages');  // Reset to pages mode for new conversation

    // Tutorial: advance from 'new-conversation' step
    if (tutorialActive && currentStep === 'new-conversation') {
      advanceStep(); // → 'conversation-intro'
    }
  };

  // Handle selecting a query from the QueryStack
  const handleSelectQuery = useCallback((queryId: string) => {
    const query = conversationQueries.find((q) => q.id === queryId);
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
  }, [conversationQueries, queryPagesCache, queryTraceCache, restore]);


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
        <FeedViewer
          key={currentConversation?.id}
          feedItems={feedItems}
          isStreaming={isStreaming}
          streamingText={finalAnswer}
          streamingTrace={trace}
          currentTool={currentTool}
          tutorialText={
            tutorialActive && currentStep === 'welcome' ? "Let me show you around." :
            tutorialActive && currentStep === 'sidebar' ? "Pick a sheet to get started." :
            tutorialActive && currentStep === 'conversation-intro' ? "Now we're in a new conversation." :
            tutorialActive && currentStep === 'history' ? (showHistory ? "Now close that." : "These are previous conversations") :
            tutorialActive && currentStep === 'complete' ? "That's it! I'm pretty simple. Make an account so I can be your plans expert." :
            undefined
          }
        />

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
          {mode === AppMode.DEMO && (inputHasBeenFocused || !tutorialActive || hasCompleted) && !submittedQuery && !isStreaming && conversationQueries.length === 0 && (
            <SuggestedPrompts
              onSelectPrompt={handleSuggestedPrompt}
              disabled={isStreaming}
              showTutorialArrows={tutorialActive && inputHasBeenFocused && !hasCompleted}
            />
          )}

          <div className="flex flex-col gap-2">
            {/* Response mode toggle - positioned above input row, right-aligned */}
            <div className="flex justify-end">
              <button
                onClick={() => setResponseMode(prev => prev === 'pages' ? 'conversational' : 'pages')}
                disabled={isStreaming}
                className={`
                  w-12 h-12 rounded-full flex items-center justify-center transition-all shadow-lg
                  ${isStreaming ? 'opacity-50 cursor-not-allowed' : ''}
                  ${responseMode === 'pages'
                    ? 'bg-cyan-500/20 text-cyan-600 border border-cyan-500/30'
                    : 'bg-white text-slate-600 border border-slate-200'}
                `}
                title={responseMode === 'pages' ? 'Pages mode: Will show relevant pages' : 'Chat mode: Will respond conversationally'}
              >
                {responseMode === 'pages' ? (
                  <FileText size={20} />
                ) : (
                  <MessageSquare size={20} />
                )}
              </button>
            </div>

            {/* Input and new session button inline */}
            <div className="flex items-center gap-3">
              <div className="flex-1" data-tutorial="query-input">
                <QueryInput
                  value={queryInput}
                  onChange={setQueryInput}
                  onSubmit={() => {
                    if (queryInput.trim() && !isStreaming) {
                      const trimmedQuery = queryInput.trim();
                      // Add user query to feed
                      setFeedItems((prev) => [
                        ...prev,
                        {
                          type: 'user-query',
                          id: crypto.randomUUID(),
                          text: trimmedQuery,
                          timestamp: Date.now(),
                        },
                      ]);
                      setSubmittedQuery(trimmedQuery);
                      setIsQueryExpanded(false);
                      submitQuery(trimmedQuery, currentConversation?.id, responseMode);
                      setQueryInput('');
                    }
                  }}
                  isProcessing={isStreaming}
                  onFocus={() => {
                    setInputHasBeenFocused(true);
                    // Advance from 'query' step to hide the input arrow
                    if (tutorialActive && currentStep === 'query') {
                      advanceStep(); // → 'responding' (no arrow)
                    }
                  }}
                />
              </div>
              <NewConversationButton
                onClick={handleNewConversation}
                disabled={isStreaming || isCreatingConversation}
              />
            </div>
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
        onRestoreConversation={handleRestoreConversation}
      />
    </div>
  );
};
