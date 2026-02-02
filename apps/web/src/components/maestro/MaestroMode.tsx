import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { AppMode, DisciplineInHierarchy, ContextPointer, QueryWithPages, AgentTraceStep, AgentConceptResponse, AgentFinding, AgentCrossReference } from '../../types';
import { QueryTraceStep } from '../../lib/api';
import { PlansPanel } from './PlansPanel';
import { FeedViewer, FeedItem } from './FeedViewer';
import { ModeToggle } from '../ModeToggle';
import { DemoHeader } from '../DemoHeader';
import { api, isNotFoundError } from '../../lib/api';
import { PanelLeftClose, PanelLeft } from 'lucide-react';
import { useToast } from '../ui/Toast';
import { useTutorial } from '../../hooks/useTutorial';
import {
  QueryInput,
  SessionControls,
  QueryHistoryPanel,
  NewConversationButton,
  SuggestedPrompts,
} from '.';
import { useQueryManager, AgentSelectedPage, CompletedQuery } from '../../hooks/useQueryManager';
import { QueryResponse, QueryPageResponse, ConversationResponse } from '../../lib/api';
import { useConversation } from '../../hooks/useConversation';
import { useAgentToast } from '../../contexts/AgentToastContext';
import { AgentToastStack } from './AgentToastStack';
import { ConversationIndicator } from './ConversationIndicator';
import { useKeyboardHeight } from '../../hooks/useKeyboardHeight';

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

/**
 * Extract concept findings from the explore_concept_with_vision tool_result in a trace.
 */
function extractConceptDataFromTrace(
  trace: QueryTraceStep[] | undefined,
  pageNameLookup?: Map<string, string>
): AgentConceptResponse | null {
  if (!trace || trace.length === 0) return null;

  let result: Record<string, unknown> | null = null;
  for (let i = trace.length - 1; i >= 0; i--) {
    const step = trace[i];
    if (step.type === 'tool_result' && step.tool === 'explore_concept_with_vision' && step.result) {
      result = step.result as Record<string, unknown>;
      break;
    }
  }

  if (!result) return null;

  const conceptName = typeof result.concept_name === 'string'
    ? result.concept_name
    : (typeof result.conceptName === 'string' ? result.conceptName : null);
  const summary = typeof result.summary === 'string' ? result.summary : null;

  const rawFindings = Array.isArray((result as { findings?: unknown }).findings)
    ? (result as { findings?: Array<Record<string, unknown>> }).findings
    : [];
  const rawCrossReferences = Array.isArray((result as { cross_references?: unknown }).cross_references)
    ? (result as { cross_references?: Array<Record<string, unknown>> }).cross_references
    : Array.isArray((result as { crossReferences?: unknown }).crossReferences)
      ? (result as { crossReferences?: Array<Record<string, unknown>> }).crossReferences
      : [];
  const rawGaps = Array.isArray((result as { gaps?: unknown }).gaps)
    ? (result as { gaps?: Array<unknown> }).gaps
    : [];

  const pageLookup = pageNameLookup ?? new Map<string, string>();

  const findings: AgentFinding[] = rawFindings
    .map((f) => {
      const raw = f as Record<string, any>;
      const pageId = String(raw.page_id || raw.pageId || '');
      return {
        category: String(raw.category || ''),
        content: String(raw.content || ''),
        pageId,
        semanticRefs: Array.isArray(raw.semantic_refs)
          ? raw.semantic_refs as number[]
          : Array.isArray(raw.semanticRefs)
            ? raw.semanticRefs as number[]
            : undefined,
        bbox: Array.isArray(raw.bbox) ? raw.bbox as [number, number, number, number] : undefined,
        confidence: typeof raw.confidence === 'string' ? raw.confidence : undefined,
        sourceText: typeof raw.source_text === 'string'
          ? raw.source_text
          : (typeof raw.sourceText === 'string' ? raw.sourceText : undefined),
        pageName: pageLookup.get(pageId) || undefined,
      };
    })
    .filter((finding) => finding.pageId && finding.content);

  const resolvePageLabel = (value: string) => pageLookup.get(value) || value;
  const crossReferences: AgentCrossReference[] = rawCrossReferences
    .map((ref) => {
      const raw = ref as Record<string, any>;
      const fromRaw = String(raw.fromPageName || raw.from_page_name || raw.fromPage || raw.from_page || '');
      const toRaw = String(raw.toPageName || raw.to_page_name || raw.toPage || raw.to_page || '');
      return {
        fromPage: resolvePageLabel(fromRaw),
        toPage: resolvePageLabel(toRaw),
        relationship: String(raw.relationship || ''),
      };
    })
    .filter((ref) => ref.fromPage && ref.toPage && ref.relationship);

  const gaps = rawGaps
    .map((gap) => String(gap || '').trim())
    .filter((gap) => gap.length > 0);

  return {
    conceptName,
    summary,
    findings,
    crossReferences,
    gaps,
  };
}

function inferQueryModeFromTrace(
  trace: QueryTraceStep[] | undefined
): 'fast' | 'deep' {
  if (!trace || trace.length === 0) return 'fast';

  for (const step of trace) {
    if (
      step.type === 'tool_call' &&
      step.tool === 'explore_concept_with_vision'
    ) {
      return 'deep';
    }
    if (
      step.type === 'tool_result' &&
      step.tool === 'explore_concept_with_vision'
    ) {
      return 'deep';
    }
  }

  return 'fast';
}

interface MaestroModeProps {
  mode: AppMode;
  setMode: (mode: AppMode) => void;
  projectId: string;
  onGetStarted?: () => void;
}

export const MaestroMode: React.FC<MaestroModeProps> = ({ mode, setMode, projectId, onGetStarted }) => {
  const queryClient = useQueryClient();
  const { showError } = useToast();
  const { currentStep, completeStep, advanceStep, isActive: tutorialActive, hasCompleted, skipTutorial } = useTutorial();

  // Selected page state
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [selectedDisciplineId, setSelectedDisciplineId] = useState<string | null>(null);

  // UI state
  const [showHistory, setShowHistory] = useState(false);
  const [queryInput, setQueryInput] = useState('');
  const [queryMode, setQueryMode] = useState<'fast' | 'deep'>('fast');
  const [submittedQuery, setSubmittedQuery] = useState<string | null>(null);
  const [isQueryExpanded, setIsQueryExpanded] = useState(false);
  const [inputHasBeenFocused, setInputHasBeenFocused] = useState(false);
  // Start with sidebar collapsed by default
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(true);

  // Hierarchy data
  const [disciplines, setDisciplines] = useState<DisciplineInHierarchy[]>([]);

  // Caches for field stream
  const [renderedPages] = useState<Map<string, string>>(new Map());
  const [pageMetadata] = useState<Map<string, { title: string; pageNumber: number }>>(new Map());
  const [contextPointers] = useState<Map<string, ContextPointer[]>>(new Map());

  // Conversation management
  const {
    activeConversationId,
    activeConversation,
    startNewConversation,
    createAndBindConversation,
    bindToConversation,
    isCreating: isCreatingConversation,
  } = useConversation(projectId);

  // Track completed queries in the current conversation for QueryStack
  const [conversationQueries, setConversationQueries] = useState<QueryWithPages[]>([]);
  const [activeQueryId, setActiveQueryId] = useState<string | null>(null);
  // Local state for conversation title - more reliable than cache for immediate display
  const [localConversationTitle, setLocalConversationTitle] = useState<string | null>(null);
  // Store full page data for each query so we can restore it
  const [queryPagesCache] = useState<Map<string, AgentSelectedPage[]>>(new Map());
  // Store trace data for each query so we can restore thinking section
  const [queryTraceCache] = useState<Map<string, AgentTraceStep[]>>(new Map());

  // Feed items for vertical scroll view
  const [feedItems, setFeedItems] = useState<FeedItem[]>([]);

  // Agent toasts - for checking if any are showing (used by ConversationIndicator)
  const { toasts } = useAgentToast();

  // Keyboard height for adjusting input position on iOS
  const keyboardHeight = useKeyboardHeight();

  // Callback when a query completes
  const handleQueryComplete = useCallback((query: CompletedQuery) => {
    const newQuery: QueryWithPages = {
      id: query.queryId,
      conversationId: activeConversationId,
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

    // Update conversation title in cache and local state if provided
    if (query.conversationTitle && activeConversationId) {
      // Update local state immediately for reliable display
      setLocalConversationTitle(query.conversationTitle);
      // Also update cache for persistence
      queryClient.setQueryData<ConversationResponse[]>(
        ['conversations', projectId],
        (old) => old?.map(c =>
          c.id === activeConversationId
            ? { ...c, title: query.conversationTitle }
            : c
        ) ?? []
      );
    }

    // Add pages and text response to feed (using callback data which has correct trace)
    setFeedItems((prev) => {
      const newItems: FeedItem[] = [...prev];

      // Add pages if we have them
      if (query.pages.length > 0) {
        newItems.push({
          type: 'pages',
          id: crypto.randomUUID(),
          pages: query.pages,
          findings: query.conceptResponse?.findings || [],
          timestamp: Date.now(),
        });
      }

      // Add structured findings if available
      if (query.conceptResponse && (query.conceptResponse.findings?.length || query.conceptResponse.gaps?.length)) {
        newItems.push({
          type: 'findings',
          id: crypto.randomUUID(),
          conceptName: query.conceptResponse.conceptName,
          summary: query.conceptResponse.summary,
          findings: query.conceptResponse.findings || [],
          gaps: query.conceptResponse.gaps,
          crossReferences: query.conceptResponse.crossReferences,
          mode: query.mode,
          timestamp: Date.now(),
        });
      }

      // Add text response if we have one
      if (query.finalAnswer) {
        newItems.push({
          type: 'text',
          id: crypto.randomUUID(),
          content: query.finalAnswer,
          trace: query.trace,
          mode: query.mode,
          elapsedTime: query.elapsedTime,
          timestamp: Date.now(),
        });
      }

      return newItems;
    });

    setConversationQueries((prev) => [...prev, newQuery]);
    setActiveQueryId(query.queryId);
  }, [activeConversationId, conversationQueries.length, queryPagesCache, queryTraceCache, queryClient, projectId]);

  // Multi-query manager - supports concurrent background queries
  const {
    submitQuery,
    activeQuery,
    runningCount,
    reset: resetStream,
    restore,
    loadPages,
  } = useQueryManager({
    projectId,
    renderedPages,
    pageMetadata,
    contextPointers,
    onQueryComplete: handleQueryComplete,
  });

  // Derive state from active query
  const isStreaming = activeQuery?.status === 'streaming';
  const thinkingText = activeQuery?.thinkingText ?? '';
  const finalAnswer = activeQuery?.finalAnswer ?? '';
  const displayTitle = activeQuery?.displayTitle ?? null;
  const currentQueryId = activeQuery?.id ?? null;
  const trace = activeQuery?.trace ?? [];
  const selectedPages = activeQuery?.selectedPages ?? [];
  const currentTool = activeQuery?.currentTool ?? null;
  const error = activeQuery?.error ?? null;

  // Toast management is now handled internally by useQueryManager

  // Handle suggested prompt selection - auto-submit
  const handleSuggestedPrompt = useCallback(async (prompt: string) => {
    if (isStreaming) return;

    // Tutorial: advance from 'prompt-suggestions' to 'background-task'
    if (tutorialActive && currentStep === 'prompt-suggestions') {
      advanceStep(); // → 'background-task'
    }

    // If no active conversation, create one first
    let conversationId = activeConversationId;
    if (!conversationId) {
      const newConv = await createAndBindConversation();
      conversationId = newConv?.id ?? null;
    }

    // Add user query to feed
    setFeedItems((prev) => [
      ...prev,
      {
        type: 'user-query',
        id: crypto.randomUUID(),
        text: prompt,
        mode: queryMode,
        timestamp: Date.now(),
      },
    ]);
    setSubmittedQuery(prompt);
    setIsQueryExpanded(false);
    // Toast management handled by useQueryManager
    submitQuery(prompt, conversationId ?? undefined, selectedPageId, queryMode);
  }, [isStreaming, activeConversationId, createAndBindConversation, submitQuery, selectedPageId, queryMode, tutorialActive, currentStep, advanceStep]);

  // Handle restoring a previous conversation from history
  const handleRestoreConversation = (
    conversationId: string,
    queries: QueryResponse[],
    selectedQueryId: string
  ) => {
    // Clear local title to avoid stale title from previous conversation
    // Will fall back to activeConversation?.title from cache
    setLocalConversationTitle(null);
    // Bind to the restored conversation
    bindToConversation(conversationId);
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
      const inferredMode = inferQueryModeFromTrace(q.trace);

      // Add user query
      newFeedItems.push({
        type: 'user-query',
        id: `feed-query-${q.id}`,
        text: q.queryText,
        mode: inferredMode,
        timestamp: new Date(q.createdAt).getTime(),
      });

      // Add pages if available
      const cachedPages = queryPagesCache.get(q.id);
      const pageNameLookup = cachedPages
        ? new Map<string, string>(cachedPages.map((page) => [page.pageId, page.pageName]))
        : undefined;
      const conceptData = extractConceptDataFromTrace(q.trace, pageNameLookup);

      if (cachedPages && cachedPages.length > 0) {
        newFeedItems.push({
          type: 'pages',
          id: `feed-pages-${q.id}`,
          pages: cachedPages,
          findings: conceptData?.findings || [],
          timestamp: new Date(q.createdAt).getTime() + 1,
        });
      }

      // Add structured findings if available in trace
      if (conceptData && (conceptData.findings?.length || conceptData.gaps?.length || conceptData.crossReferences?.length)) {
        newFeedItems.push({
          type: 'findings',
          id: `feed-findings-${q.id}`,
          conceptName: conceptData.conceptName,
          summary: conceptData.summary,
          findings: conceptData.findings || [],
          gaps: conceptData.gaps,
          crossReferences: conceptData.crossReferences,
          mode: inferredMode,
          timestamp: new Date(q.createdAt).getTime() + 2,
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
          mode: inferredMode,
          timestamp: new Date(q.createdAt).getTime() + 3,
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

  // Handle navigation from agent toast (fetch conversation and restore)
  const handleToastNavigate = useCallback(async (conversationId: string) => {
    // Tutorial: advance from 'complete-task' to 'result-page' when user clicks Complete
    if (tutorialActive && currentStep === 'complete-task') {
      advanceStep(); // → 'result-page'
    }

    // If we're already on this conversation, show the conversation content
    // by filtering out standalone-page items (the user was browsing pages)
    if (activeConversationId === conversationId && conversationQueries.length > 0) {
      setShowHistory(false);
      // Remove standalone-page items to show conversation content
      setFeedItems((prev) => prev.filter((item) => item.type !== 'standalone-page'));
      // Force scroll to top
      setTimeout(() => {
        const scrollContainer = document.querySelector('[data-scroll-container]');
        scrollContainer?.scrollTo({ top: 0, behavior: 'smooth' });
      }, 100);
      return;
    }

    // Otherwise fetch from API and restore
    try {
      const conversation = await api.conversations.get(conversationId);
      if (conversation.queries && conversation.queries.length > 0) {
        // Navigate to the most recent query in the conversation
        const lastQuery = conversation.queries[conversation.queries.length - 1];
        handleRestoreConversation(conversationId, conversation.queries, lastQuery.id);
      }
      // Set title AFTER restore (which clears it) so we have the fetched title
      setLocalConversationTitle(conversation.title ?? null);

      // Force scroll to top when navigating from toast
      setTimeout(() => {
        const scrollContainer = document.querySelector('[data-scroll-container]');
        scrollContainer?.scrollTo({ top: 0, behavior: 'smooth' });
      }, 100);
    } catch (err) {
      console.error('Failed to navigate to conversation:', err);
      showError('Failed to load conversation. Please try again.');
    }
  }, [activeConversationId, conversationQueries.length, handleRestoreConversation, showError, tutorialActive, currentStep, advanceStep]);

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

  // Tutorial: detect sidebar expand to complete 'welcome' step
  // Only triggers when user manually expands after tutorial collapsed it
  useEffect(() => {
    if (!isSidebarCollapsed && tutorialActive && currentStep === 'welcome' && tutorialCollapsedSidebarRef.current) {
      tutorialCollapsedSidebarRef.current = false;
      completeStep('welcome');
    }
  }, [isSidebarCollapsed, tutorialActive, currentStep, completeStep]);

  // Tutorial: advance to 'complete-task' when toast status changes to complete
  useEffect(() => {
    if (tutorialActive && currentStep === 'background-task') {
      const completedToast = toasts.find(t => t.status === 'complete');
      if (completedToast) {
        advanceStep(); // → 'complete-task'
      }
    }
  }, [tutorialActive, currentStep, toasts, advanceStep]);

  // Tutorial: auto-advance from 'page-zoom' to 'prompt-suggestions' after 2 seconds
  useEffect(() => {
    if (tutorialActive && currentStep === 'page-zoom') {
      const timer = setTimeout(() => {
        advanceStep(); // → 'prompt-suggestions'
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [tutorialActive, currentStep, advanceStep]);

  // Callback for when expanded page modal closes (for tutorial)
  const handleExpandedPageClose = useCallback(() => {
    if (tutorialActive && currentStep === 'result-page') {
      advanceStep(); // → 'new-session'
    }
  }, [tutorialActive, currentStep, advanceStep]);

  // Handle page selection from PlansPanel
  // Loads page into viewer - preserves agent if streaming
  const handlePageSelect = async (pageId: string, disciplineId: string, pageName: string) => {
    // Tutorial: complete 'pick-sheet' step when user selects a page
    completeStep('pick-sheet');

    // If agent is streaming, don't reset - let it continue in background
    // User can browse pages while agent works, then click toast to see response
    if (!isStreaming) {
      // Reset conversation state only when not streaming
      resetStream();
      setQueryInput('');
      setSubmittedQuery(null);
      setIsQueryExpanded(false);
      setConversationQueries([]);
      setActiveQueryId(null);
      queryPagesCache.clear();
      queryTraceCache.clear();
    }
    // Don't clear feedItems here - we'll replace them atomically below

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

      // Update feedItems for page viewing
      // Always preserve conversation items when adding standalone-page
      // This ensures content isn't lost when browsing file tree pages
      setFeedItems((prev) => {
        const conversationItems = prev.filter((item) => item.type !== 'standalone-page');
        return [
          {
            type: 'standalone-page',
            id: crypto.randomUUID(),
            page: pageToLoad,
            timestamp: Date.now(),
          },
          ...conversationItems,
        ];
      });
    } catch (err) {
      console.error('Failed to load page for viewer:', err);
      setFeedItems([]); // Clear on error to show empty state
      if (isNotFoundError(err)) {
        showError(`Page "${pageName}" not found. Try refreshing the page list.`);
      } else {
        showError('Failed to load page. Please try again.');
      }
    }
  };

  // Handle starting a new conversation (clears query stack)
  const handleNewConversation = () => {
    startNewConversation();
    resetStream();
    setQueryInput('');
    setSubmittedQuery(null);
    setIsQueryExpanded(false);
    setInputHasBeenFocused(false);  // Reset so prompts don't reappear
    setConversationQueries([]);
    setActiveQueryId(null);
    setLocalConversationTitle(null);  // Clear title for new conversation
    queryPagesCache.clear();
    queryTraceCache.clear();
    setSelectedPageId(null);  // Reset viewer to empty state
    setFeedItems([]);  // Clear feed

    // Tutorial: advance from 'new-session' step to 'cta'
    if (tutorialActive && currentStep === 'new-session') {
      advanceStep(); // → 'cta'
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

  // Compute toast visibility: show when user is on file tree page (standalone-page),
  // hide when in conversation view (they can see the agent working directly).
  // Toast auto-dismisses naturally - don't tie visibility to isStreaming.
  const hasStandalonePageVisible = feedItems.some((item) => item.type === 'standalone-page');
  const shouldShowToast = hasStandalonePageVisible;

  // Compute whether toast or conversation indicator is visible for button positioning
  const isToastVisible = toasts.length > 0 && shouldShowToast;
  // Indicator shows when: in conversation, not streaming, and all toasts auto-dismissed
  const isIndicatorVisible = activeConversationId !== null && !isStreaming && toasts.length === 0;
  const hasTopLeftOverlay = isToastVisible || isIndicatorVisible;

  return (
    <div className="fixed inset-0 flex overflow-hidden bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50 text-slate-900 font-sans blueprint-grid">
      {/* Fixed toggle button - only visible when sidebar is collapsed */}
      {/* Positioned to align with toggle button location when panel is expanded (below ModeToggle) */}
      {isSidebarCollapsed && (
        <button
          onClick={() => setIsSidebarCollapsed(false)}
          className={`fixed left-4 z-50 p-2 rounded-xl bg-white/90 backdrop-blur-md border border-slate-200/50 shadow-lg hover:bg-slate-50 text-slate-500 hover:text-slate-700 transition-all duration-200 ${
            hasTopLeftOverlay ? 'top-[11.5rem]' : 'top-[6.5rem]'
          }`}
          title="Expand sidebar"
          data-tutorial="sidebar-expand"
        >
          <PanelLeft size={20} />
        </button>
      )}

      {/* Left panel - PlansPanel with collapse */}
      {!isSidebarCollapsed && (
        <div className="w-72 h-full flex flex-col bg-white/90 backdrop-blur-xl border-r border-slate-200/50 z-20 shadow-lg">
          {/* Header */}
          <div className="px-4 pb-4 pt-12 border-b border-slate-200/50 bg-white/50 space-y-3">
            {mode === AppMode.DEMO && onGetStarted ? (
              <DemoHeader onGetStarted={onGetStarted} />
            ) : mode !== AppMode.DEMO ? (
              <ModeToggle mode={mode} setMode={setMode} variant="light" />
            ) : null}
            <div className="flex items-center justify-between">
              <button
                onClick={() => setIsSidebarCollapsed(true)}
                className="p-2 rounded-xl bg-white/90 backdrop-blur-md border border-slate-200/50 shadow-sm hover:bg-slate-50 text-slate-500 hover:text-slate-700 transition-all duration-200"
                title="Collapse sidebar"
              >
                <PanelLeftClose size={20} />
              </button>
              <h1 className="font-bold text-2xl text-slate-800">
                Maestro<span className="text-cyan-600">Super</span>
              </h1>
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
          feedItems={feedItems}
          isStreaming={isStreaming}
          streamingTrace={trace}
          thinkingText={thinkingText}
          currentTool={currentTool}
          tutorialStep={currentStep}
          onExpandedPageClose={handleExpandedPageClose}
        />

        {/* Query input bar - bottom, adjusts for keyboard on iOS */}
        <div
          className="absolute left-6 right-6 z-30 transition-[bottom] duration-100"
          style={{
            bottom: keyboardHeight > 0
              ? `${keyboardHeight + 12}px` // 12px padding above keyboard
              : '1.5rem',
          }}
        >
          {/* Suggested prompts - show in demo mode after page loaded in tutorial, after input focused, or after tutorial completed */}
          {mode === AppMode.DEMO && (
            inputHasBeenFocused ||
            !tutorialActive ||
            hasCompleted ||
            currentStep === 'prompt-suggestions'
          ) && !submittedQuery && !isStreaming && conversationQueries.length === 0 && (
            <SuggestedPrompts
              onSelectPrompt={handleSuggestedPrompt}
              disabled={isStreaming}
              showTutorialArrows={tutorialActive && currentStep === 'prompt-suggestions'}
            />
          )}

          <div className="flex flex-col gap-2">
            {/* Input and new session button inline */}
            <div className="flex items-center gap-3">
              <div className="flex-1" data-tutorial="query-input">
                <QueryInput
                  value={queryInput}
                  onChange={setQueryInput}
                  onSubmit={async () => {
                    if (queryInput.trim() && !isStreaming) {
                      const trimmedQuery = queryInput.trim();

                      // If no active conversation, create one first
                      let conversationId = activeConversationId;
                      if (!conversationId) {
                        const newConv = await createAndBindConversation();
                        conversationId = newConv?.id ?? null;
                      }

                      // Add user query to feed
                      setFeedItems((prev) => [
                        ...prev,
                        {
                          type: 'user-query',
                          id: crypto.randomUUID(),
                          text: trimmedQuery,
                          mode: queryMode,
                          timestamp: Date.now(),
                        },
                      ]);
                      setSubmittedQuery(trimmedQuery);
                      setIsQueryExpanded(false);
                      // Toast management handled by useQueryManager
                      submitQuery(trimmedQuery, conversationId ?? undefined, selectedPageId, queryMode);
                      setQueryInput('');
                    }
                  }}
                  isProcessing={isStreaming}
                  queryMode={queryMode}
                  onQueryModeChange={setQueryMode}
                  onFocus={() => {
                    setInputHasBeenFocused(true);
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

        {/* Agent working toast stack - only shows when on file tree page with background agent */}
        <AgentToastStack onNavigate={handleToastNavigate} shouldShow={shouldShowToast} />

        {/* Conversation indicator - shows when bound to conversation and idle */}
        <ConversationIndicator
          conversationTitle={localConversationTitle ?? activeConversation?.title ?? null}
          isVisible={activeConversationId !== null && !isStreaming && toasts.length === 0}
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
