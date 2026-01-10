import React, { useState, useRef, useEffect, useCallback } from 'react';
import * as pdfjs from 'pdfjs-dist';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';
import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import { downloadFile, getPublicUrl } from '../../lib/storage';
import { AgentSelectedPage } from '../field';

// Set up PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

// Render scale for PNG conversion (3x for sharp rendering on iPad, matches PdfViewer)
const RENDER_SCALE = 3;

interface PageImage {
  dataUrl: string;
  width: number;
  height: number;
}

interface PlanViewerProps {
  selectedPages?: AgentSelectedPage[];
  onVisiblePageChange?: (pageId: string, disciplineId: string) => void;
  showPointers?: boolean; // Only show pointer overlays when viewing query results
  tutorialText?: string; // Override greeting with tutorial message
  currentTool?: string; // Current tool being called during streaming
}

// Cache for rendered page images
const pageImageCache = new Map<string, PageImage>();

// Track in-flight loads to avoid duplicate fetches
const loadingPromises = new Map<string, Promise<PageImage | null>>();

// Welcome greetings for empty state (randomly selected)
const WELCOME_GREETINGS = [
  "What do you need to see?",
  "Where should we look?",
  "What are we solving today?",
  "I'm ready - ask away.",
  "Go ahead, I'm listening.",
  "Fire away.",
  "What are we hunting for?",
  "Point me at a problem.",
  "Let's find it.",
  "I've got the plans - what do you need?",
  "Ask me to pull something up.",
  "Tell me what you're working on.",
  "Ready when you are.",
  "What can I help you find?",
];

// Status messages for each tool type (randomly selected per call)
const TOOL_STATUS_MESSAGES: Record<string, string[]> = {
  search_pointers: [
    "Searching...",
    "Looking for details...",
    "Hunting through the plans...",
  ],
  search_pages: [
    "Checking sheets...",
    "Scanning the plans...",
    "Looking through pages...",
  ],
  get_pointer: [
    "Looking closer...",
    "Checking that out...",
    "Examining...",
  ],
  get_page_context: [
    "Reading the page...",
    "Seeing what's here...",
    "Checking this sheet...",
  ],
  get_discipline_overview: [
    "Getting the overview...",
    "Zooming out...",
    "Getting the big picture...",
  ],
  get_references_to_page: [
    "Finding references...",
    "Tracking connections...",
    "Following the trail...",
  ],
  select_pages: [
    "Pulling up the sheets...",
    "Loading pages...",
    "Got it, bringing those up...",
  ],
  select_pointers: [
    "Highlighting...",
    "Marking the spots...",
    "Found it, showing you...",
  ],
  list_project_pages: [
    "Browsing the project...",
    "Looking at what's available...",
  ],
};

// Helper to get random status message for a tool
function getToolStatusMessage(tool: string): string {
  const messages = TOOL_STATUS_MESSAGES[tool];
  if (!messages || messages.length === 0) {
    return "Working on it...";
  }
  return messages[Math.floor(Math.random() * messages.length)];
}

// Reusable function to load a page image (used by both prefetch and current-page loading)
async function loadPageImage(page: AgentSelectedPage): Promise<PageImage | null> {
  // Check cache first
  const cached = pageImageCache.get(page.pageId);
  if (cached) {
    console.log('[PlanViewer] Cache hit:', page.pageId);
    return cached;
  }

  // Check if already loading
  const existing = loadingPromises.get(page.pageId);
  if (existing) return existing;

  // Start loading
  const promise = (async () => {
    try {
      console.log('[PlanViewer] Loading page:', page.pageId, 'filePath:', page.filePath);

      // Check if it's a PNG (pre-rendered) - use public URL for fast loading
      // This matches how PdfViewer loads pre-rendered PNGs
      if (page.filePath.endsWith('.png')) {
        console.log('[PlanViewer] PNG detected, using getPublicUrl');
        const url = getPublicUrl(page.filePath);
        console.log('[PlanViewer] Public URL:', url);
        const img = new Image();
        img.src = url;
        await img.decode();
        console.log('[PlanViewer] PNG loaded:', page.pageId, img.naturalWidth, 'x', img.naturalHeight);

        const pageImage: PageImage = {
          dataUrl: url,
          width: img.naturalWidth / RENDER_SCALE,
          height: img.naturalHeight / RENDER_SCALE,
        };

        pageImageCache.set(page.pageId, pageImage);
        return pageImage;
      }

      // PDF fallback - download and render via PDF.js
      console.log('[PlanViewer] PDF detected, using PDF.js fallback');
      const blob = await downloadFile(page.filePath);
      const arrayBuffer = await blob.arrayBuffer();
      const pdf = await pdfjs.getDocument({ data: arrayBuffer }).promise;
      const pdfPage = await pdf.getPage(1);
      const viewport = pdfPage.getViewport({ scale: RENDER_SCALE });

      const canvas = document.createElement('canvas');
      const context = canvas.getContext('2d')!;
      canvas.width = viewport.width;
      canvas.height = viewport.height;

      await pdfPage.render({
        canvasContext: context,
        viewport: viewport,
      }).promise;

      const dataUrl = canvas.toDataURL('image/png');

      // Pre-decode the image so it's ready for instant display
      const img = new Image();
      img.src = dataUrl;
      await img.decode();

      const pageImage: PageImage = {
        dataUrl,
        width: viewport.width / RENDER_SCALE,
        height: viewport.height / RENDER_SCALE,
      };

      pageImageCache.set(page.pageId, pageImage);
      return pageImage;
    } catch (err) {
      console.error('Failed to load page:', page.pageId, err);
      return null;
    } finally {
      loadingPromises.delete(page.pageId);
    }
  })();

  loadingPromises.set(page.pageId, promise);
  return promise;
}

export const PlanViewer: React.FC<PlanViewerProps> = ({
  selectedPages = [],
  onVisiblePageChange,
  showPointers = false,
  tutorialText,
  currentTool,
}) => {
  // =====================================
  // ALL HOOKS MUST BE AT THE TOP (unconditionally)
  // =====================================

  // Container size for fit calculation
  const [containerSize, setContainerSize] = useState({ width: 800, height: 600 });

  // Random greeting for empty state (picked once on mount)
  const [greeting] = useState(() =>
    WELCOME_GREETINGS[Math.floor(Math.random() * WELCOME_GREETINGS.length)]
  );

  // Tool status message (changes when currentTool changes)
  const [toolStatus, setToolStatus] = useState<string | null>(null);

  // Update tool status when currentTool changes
  useEffect(() => {
    console.log('[PlanViewer] currentTool changed:', currentTool);
    if (currentTool) {
      const statusMsg = getToolStatusMessage(currentTool);
      console.log('[PlanViewer] Setting toolStatus to:', statusMsg);
      setToolStatus(statusMsg);
    } else {
      setToolStatus(null);
    }
  }, [currentTool]);

  // Refs
  const containerRef = useRef<HTMLDivElement>(null);
  const hasEverShownPage = useRef(false);

  // Multi-page mode: current page index
  const [agentPageIndex, setAgentPageIndex] = useState(0);

  // Reset agent page index when selectedPages changes (new query)
  useEffect(() => {
    setAgentPageIndex(0);
    if (selectedPages.length > 0) {
      onVisiblePageChange?.(selectedPages[0].pageId, selectedPages[0].disciplineId);
    }
  }, [selectedPages.length]); // Only trigger on length change to avoid infinite loop

  // Navigate between agent-selected pages
  const goToPrevAgentPage = useCallback(() => {
    if (selectedPages.length === 0) return;
    const newIndex = Math.max(0, agentPageIndex - 1);
    setAgentPageIndex(newIndex);
    onVisiblePageChange?.(selectedPages[newIndex].pageId, selectedPages[newIndex].disciplineId);
  }, [agentPageIndex, selectedPages, onVisiblePageChange]);

  const goToNextAgentPage = useCallback(() => {
    if (selectedPages.length === 0) return;
    const newIndex = Math.min(selectedPages.length - 1, agentPageIndex + 1);
    setAgentPageIndex(newIndex);
    onVisiblePageChange?.(selectedPages[newIndex].pageId, selectedPages[newIndex].disciplineId);
  }, [agentPageIndex, selectedPages, onVisiblePageChange]);

  // Touch swipe handling for iPad/mobile
  const touchStartY = useRef<number | null>(null);

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 1) {
      touchStartY.current = e.touches[0].clientY;
    }
  }, []);

  const handleTouchEnd = useCallback((e: React.TouchEvent) => {
    if (touchStartY.current === null) return;

    const touchEndY = e.changedTouches[0].clientY;
    const deltaY = touchStartY.current - touchEndY;

    // Require a minimum swipe distance (50px)
    if (Math.abs(deltaY) > 50) {
      if (deltaY > 0) {
        // Swiped up = go to next page
        goToNextAgentPage();
      } else {
        // Swiped down = go to previous page
        goToPrevAgentPage();
      }
    }

    touchStartY.current = null;
  }, [goToNextAgentPage, goToPrevAgentPage]);

  // Current agent page
  const currentAgentPage = selectedPages[agentPageIndex];

  // Agent page image state
  const [agentPageImage, setAgentPageImage] = useState<PageImage | null>(null);
  const [isLoadingAgentPage, setIsLoadingAgentPage] = useState(false);

  // Prefetch first 3 pages when selectedPages changes (limit for iPad memory)
  useEffect(() => {
    if (selectedPages.length === 0) return;

    // Only prefetch first 3 pages to avoid iPad memory issues
    const pagesToPrefetch = selectedPages.slice(0, 3);
    const pagesToLoad = pagesToPrefetch.filter(p => !pageImageCache.has(p.pageId));
    if (pagesToLoad.length > 0) {
      Promise.all(pagesToLoad.map(page => loadPageImage(page)));
    }
  }, [selectedPages]);

  // Load current agent page image when it changes (shows immediately from cache or loads)
  useEffect(() => {
    if (!currentAgentPage) {
      setAgentPageImage(null);
      return;
    }

    // Check cache first (may already be prefetched)
    const cached = pageImageCache.get(currentAgentPage.pageId);
    if (cached) {
      setAgentPageImage(cached);
      hasEverShownPage.current = true;
      return;
    }

    // Load the current page (will also be picked up by prefetch, but we track loading state here)
    setIsLoadingAgentPage(true);
    loadPageImage(currentAgentPage).then(pageImage => {
      if (pageImage) {
        setAgentPageImage(pageImage);
        hasEverShownPage.current = true;
      }
      setIsLoadingAgentPage(false);
    });
  }, [currentAgentPage?.pageId, currentAgentPage?.filePath]);

  // Measure container size
  useEffect(() => {
    const updateSize = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        setContainerSize({ width: rect.width - 64, height: rect.height - 64 });
      }
    };

    const timer = setTimeout(updateSize, 100);
    window.addEventListener('resize', updateSize);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', updateSize);
    };
  }, []);

  // Calculate agent page display dimensions
  const agentDisplayDimensions = agentPageImage ? (() => {
    const imgWidth = agentPageImage.width;
    const imgHeight = agentPageImage.height;
    const scaleX = containerSize.width / imgWidth;
    const scaleY = containerSize.height / imgHeight;
    const fitScale = Math.min(scaleX, scaleY, 1);
    return {
      width: imgWidth * fitScale,
      height: imgHeight * fitScale,
    };
  })() : { width: 800, height: 600 };

  // =====================================
  // MULTI-PAGE MODE (when agent has selected pages)
  // =====================================
  if (selectedPages.length > 0 && currentAgentPage) {
    return (
      <div className="flex-1 flex flex-col h-full relative overflow-hidden">
        {/* Page name header */}
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 bg-white/90 backdrop-blur-md border border-slate-200/50 px-4 py-2 rounded-xl shadow-sm">
          <span className="text-sm font-medium text-slate-700">{currentAgentPage.pageName}</span>
        </div>

        {/* Navigation - side buttons */}
        {selectedPages.length > 1 && (
          <>
            {/* Previous page - left side */}
            {agentPageIndex > 0 && (
              <button
                onClick={goToPrevAgentPage}
                className="absolute left-2 top-1/2 -translate-y-1/2 z-20 flex items-center gap-1 bg-white/95 backdrop-blur-md border border-slate-200/50 rounded-xl px-3 py-2 shadow-lg hover:bg-slate-50 transition-all"
              >
                <ChevronLeft size={18} className="text-slate-600" />
                <span className="text-sm font-medium text-slate-600">Prev</span>
              </button>
            )}

            {/* Next page - right side */}
            {agentPageIndex < selectedPages.length - 1 && (
              <button
                onClick={goToNextAgentPage}
                className="absolute right-2 top-1/2 -translate-y-1/2 z-20 flex items-center gap-1 bg-white/95 backdrop-blur-md border border-slate-200/50 rounded-xl px-3 py-2 shadow-lg hover:bg-slate-50 transition-all"
              >
                <span className="text-sm font-medium text-slate-600">
                  pg. {agentPageIndex + 1}/{selectedPages.length}
                </span>
                <ChevronRight size={18} className="text-slate-600" />
              </button>
            )}
          </>
        )}

        {/* Canvas Area - pinch-to-zoom enabled */}
        <div
          ref={containerRef}
          className="flex-1 blueprint-grid"
          style={{ position: 'relative' }}
        >
          {/* Loading overlay - shown on top of viewer when loading */}
          {isLoadingAgentPage && (
            <div className="absolute inset-0 flex items-center justify-center bg-slate-100 z-10">
              <Loader2 size={48} className="text-cyan-500 animate-spin" />
            </div>
          )}

          {agentPageImage && (
            <TransformWrapper
              initialScale={1}
              minScale={0.5}
              maxScale={5}
              centerOnInit={true}
              doubleClick={{ mode: "reset" }}
              panning={{ velocityDisabled: true }}
            >
              <TransformComponent
                wrapperStyle={{
                  width: '100%',
                  height: '100%',
                }}
                contentStyle={{
                  width: '100%',
                  height: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <div
                  className="relative shadow-2xl select-none"
                  style={{
                    width: agentDisplayDimensions.width,
                    height: agentDisplayDimensions.height,
                  }}
                >
                  <img
                    src={agentPageImage.dataUrl}
                    alt={currentAgentPage?.pageName ?? ''}
                    className="max-w-none w-full h-full"
                    draggable={false}
                  />

                  {/* Pointer overlays - simplified for iOS Safari compatibility */}
                  {showPointers && currentAgentPage?.pointers.map((pointer) => (
                    <div
                      key={pointer.pointerId}
                      className="absolute border-2 border-cyan-500/70 bg-cyan-500/10 hover:bg-cyan-500/20 cursor-pointer group"
                      style={{
                        left: `${pointer.bboxX * 100}%`,
                        top: `${pointer.bboxY * 100}%`,
                        width: `${pointer.bboxWidth * 100}%`,
                        height: `${pointer.bboxHeight * 100}%`,
                      }}
                    >
                      <div className="opacity-0 group-hover:opacity-100 absolute -top-8 left-1/2 -translate-x-1/2 bg-slate-800/90 px-2 py-1 rounded text-xs text-white whitespace-nowrap z-10 pointer-events-none">
                        {pointer.title}
                      </div>
                    </div>
                  ))}
                </div>
              </TransformComponent>
            </TransformWrapper>
          )}
        </div>
      </div>
    );
  }

  // =====================================
  // EMPTY STATE (no pages selected)
  // =====================================
  // Show tool status during streaming (always), or greeting if pages haven't been shown yet
  const displayText = tutorialText || toolStatus || (!hasEverShownPage.current ? greeting : null);

  // Debug logging
  console.log('[PlanViewer] Empty state render:', {
    tutorialText,
    toolStatus,
    hasEverShownPage: hasEverShownPage.current,
    greeting,
    displayText,
    selectedPagesLength: selectedPages.length,
  });

  return (
    <div className="flex-1 flex items-center justify-center h-full blueprint-grid">
      {displayText && (
        <p className="text-black text-2xl">{displayText}</p>
      )}
    </div>
  );
};
