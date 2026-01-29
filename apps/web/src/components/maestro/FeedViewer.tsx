import React, { useState, useRef, useEffect, useCallback } from 'react';
import * as pdfjs from 'pdfjs-dist';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';
import { Loader2, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { downloadFile, getPublicUrl } from '../../lib/storage';
import { AgentSelectedPage } from '.';
import { MaestroText } from './MaestroText';
import { ThinkingSection } from './ThinkingSection';
import { TextHighlightOverlay } from './TextHighlightOverlay';
import type { AgentTraceStep } from '../../types';

// Set up PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

// Render scale for PNG conversion (3x for sharp rendering on iPad)
const RENDER_SCALE = 3;

// Feed item types
export type FeedItem =
  | { type: 'user-query'; id: string; text: string; timestamp: number }
  | { type: 'pages'; id: string; pages: AgentSelectedPage[]; timestamp: number }
  | { type: 'text'; id: string; content: string; trace: AgentTraceStep[]; elapsedTime?: number; timestamp: number }
  | { type: 'standalone-page'; id: string; page: AgentSelectedPage; timestamp: number };

interface PageImage {
  dataUrl: string;
  width: number;
  height: number;
}

interface FeedViewerProps {
  feedItems: FeedItem[];
  isStreaming: boolean;
  streamingText?: string;
  streamingTrace?: AgentTraceStep[];
  currentTool?: string | null;
  tutorialText?: string;
  tutorialStep?: string | null;
  onExpandedPageClose?: () => void;
}

// Cache for rendered page images (shared with PlanViewer if needed)
const pageImageCache = new Map<string, PageImage>();
const loadingPromises = new Map<string, Promise<PageImage | null>>();

// Welcome greetings for empty state
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

// Helper to load an image with retry logic
async function loadImageWithRetry(url: string, maxRetries = 3): Promise<HTMLImageElement> {
  let lastError: Error | null = null;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const img = new Image();
      img.src = url;
      await img.decode();
      return img;
    } catch (err) {
      lastError = err as Error;
      console.log(`[FeedViewer] Image decode attempt ${attempt}/${maxRetries} failed, retrying...`);
      // Wait a bit before retrying (exponential backoff)
      if (attempt < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, 100 * attempt));
      }
    }
  }

  throw lastError;
}

// Reusable function to load a page image
async function loadPageImage(page: AgentSelectedPage): Promise<PageImage | null> {
  const cached = pageImageCache.get(page.pageId);
  if (cached) return cached;

  const existing = loadingPromises.get(page.pageId);
  if (existing) return existing;

  const promise = (async () => {
    try {
      console.log('[FeedViewer] Loading page:', page.pageId, 'filePath:', page.filePath);

      // PNG path - use public URL for fast loading
      if (page.filePath.endsWith('.png')) {
        const url = getPublicUrl(page.filePath);
        console.log('[FeedViewer] PNG URL:', url);
        const img = await loadImageWithRetry(url);
        console.log('[FeedViewer] PNG loaded:', page.pageId, img.naturalWidth, 'x', img.naturalHeight);

        const pageImage: PageImage = {
          dataUrl: url,
          width: img.naturalWidth / RENDER_SCALE,
          height: img.naturalHeight / RENDER_SCALE,
        };

        pageImageCache.set(page.pageId, pageImage);
        return pageImage;
      }

      // PDF fallback - download and render via PDF.js
      console.log('[FeedViewer] PDF fallback for:', page.pageId);
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
      console.error('[FeedViewer] Failed to load page:', page.pageId, 'filePath:', page.filePath, err);
      return null;
    } finally {
      loadingPromises.delete(page.pageId);
    }
  })();

  loadingPromises.set(page.pageId, promise);
  return promise;
}

// Full-screen modal for expanded page viewing
const ExpandedPageModal: React.FC<{
  page: AgentSelectedPage;
  pageImage: PageImage;
  onClose: () => void;
  tutorialStep?: string | null;
}> = ({ page, pageImage, onClose, tutorialStep }) => {
  // Container size for fit calculation
  const [containerSize, setContainerSize] = useState({ width: 800, height: 600 });
  const containerRef = useRef<HTMLDivElement>(null);

  // Measure container size
  useEffect(() => {
    const updateSize = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        setContainerSize({ width: rect.width - 64, height: rect.height - 64 });
      }
    };

    // Delayed update for orientation change (iOS animation completion)
    const handleOrientationChange = () => {
      setTimeout(updateSize, 100);
    };

    const timer = setTimeout(updateSize, 50);
    window.addEventListener('resize', updateSize);
    window.addEventListener('orientationchange', handleOrientationChange);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', updateSize);
      window.removeEventListener('orientationchange', handleOrientationChange);
    };
  }, []);

  // Calculate display dimensions to fit container
  const displayDimensions = (() => {
    const imgWidth = pageImage.width;
    const imgHeight = pageImage.height;
    const scaleX = containerSize.width / imgWidth;
    const scaleY = containerSize.height / imgHeight;
    const fitScale = Math.min(scaleX, scaleY, 1);
    return {
      width: imgWidth * fitScale,
      height: imgHeight * fitScale,
    };
  })();

  // Close on escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm">
      {/* Close button - highlight during tutorial */}
      <button
        onClick={onClose}
        className={`absolute top-12 right-4 z-10 p-2 rounded-full bg-white/90 hover:bg-white shadow-lg transition-colors ${
          tutorialStep === 'result-page' ? 'ring-2 ring-cyan-400' : ''
        }`}
        style={tutorialStep === 'result-page' ? { animation: 'pulse-glow 2s ease-in-out infinite' } : undefined}
      >
        <X size={24} className="text-slate-700" />
      </button>

      {/* CSS for tutorial pulse animation */}
      {tutorialStep === 'result-page' && (
        <style>{`
          @keyframes pulse-glow {
            0%, 100% { box-shadow: 0 0 12px rgba(34, 211, 238, 0.5); }
            50% { box-shadow: 0 0 24px rgba(34, 211, 238, 0.8); }
          }
        `}</style>
      )}

      {/* Page name header */}
      <div className="absolute top-12 left-1/2 -translate-x-1/2 z-10 bg-white/90 backdrop-blur-md border border-slate-200/50 px-4 py-2 rounded-xl shadow-lg">
        <span className="text-sm font-medium text-slate-700">{page.pageName}</span>
      </div>

      {/* Full-screen viewer with zoom/pan */}
      <div
        ref={containerRef}
        className="w-full h-full flex items-center justify-center"
        onClick={(e) => {
          // Close when clicking backdrop (not the image)
          if (e.target === e.currentTarget) onClose();
        }}
      >
        <TransformWrapper
          initialScale={1}
          minScale={0.5}
          maxScale={5}
          centerOnInit={true}
          doubleClick={{ mode: 'reset' }}
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
                width: displayDimensions.width,
                height: displayDimensions.height,
              }}
            >
              <img
                src={pageImage.dataUrl}
                alt={page.pageName}
                className="max-w-none w-full h-full"
                draggable={false}
              />

              {/* Text highlights from agent */}
              {page.highlights && page.highlights.length > 0 && (
                <TextHighlightOverlay
                  highlights={page.highlights}
                  imageWidth={displayDimensions.width}
                  imageHeight={displayDimensions.height}
                  originalWidth={page.imageWidth}
                  originalHeight={page.imageHeight}
                />
              )}

              {/* Legacy pointer overlays */}
              {page.pointers.map((pointer) => (
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
      </div>
    </div>
  );
};

// Pages cluster with sequential loading to avoid memory pressure
const PagesCluster: React.FC<{
  pages: AgentSelectedPage[];
  containerWidth: number;
  onTap: (page: AgentSelectedPage, pageImage: PageImage) => void;
  isFirstCluster?: boolean;
}> = ({ pages, containerWidth, onTap, isFirstCluster = false }) => {
  // Track loaded images and current loading index
  const [loadedImages, setLoadedImages] = useState<Map<string, PageImage>>(new Map());
  const [loadingIndex, setLoadingIndex] = useState(0);
  const [currentlyLoading, setCurrentlyLoading] = useState(false);

  // Load pages one at a time
  useEffect(() => {
    if (loadingIndex >= pages.length || currentlyLoading) return;

    const page = pages[loadingIndex];

    // Skip if already loaded (from cache)
    const cached = pageImageCache.get(page.pageId);
    if (cached) {
      setLoadedImages(prev => new Map(prev).set(page.pageId, cached));
      setLoadingIndex(prev => prev + 1);
      return;
    }

    // Load this page
    setCurrentlyLoading(true);
    loadPageImage(page).then((img) => {
      if (img) {
        setLoadedImages(prev => new Map(prev).set(page.pageId, img));
      }
      setCurrentlyLoading(false);
      setLoadingIndex(prev => prev + 1);
    });
  }, [pages, loadingIndex, currentlyLoading]);

  return (
    <div className="space-y-8">
      {pages.map((page, index) => {
        const pageImage = loadedImages.get(page.pageId);
        const isWaiting = index > loadingIndex;
        const isLoading = index === loadingIndex && currentlyLoading;

        return (
          <FeedPageItemDisplay
            key={page.pageId}
            page={page}
            pageImage={pageImage}
            isLoading={isLoading}
            isWaiting={isWaiting}
            containerWidth={containerWidth}
            onTap={onTap}
            isFirstPage={isFirstCluster && index === 0}
          />
        );
      })}
    </div>
  );
};

// Display component for a single page (doesn't handle loading itself)
const FeedPageItemDisplay: React.FC<{
  page: AgentSelectedPage;
  pageImage: PageImage | null | undefined;
  isLoading: boolean;
  isWaiting: boolean;
  containerWidth: number;
  onTap: (page: AgentSelectedPage, pageImage: PageImage) => void;
  isFirstPage?: boolean;
}> = ({ page, pageImage, isLoading, isWaiting, containerWidth, onTap, isFirstPage = false }) => {
  // Loading or waiting state
  if (isLoading || isWaiting || !pageImage) {
    return (
      <div className="flex flex-col items-center w-[85%] max-w-[450px] mx-auto">
        <div className="mb-2 bg-white/90 backdrop-blur-md border border-slate-200/50 px-4 py-2 rounded-xl shadow-sm">
          <span className="text-sm font-medium text-slate-700">{page.pageName}</span>
        </div>
        <div className="flex items-center justify-center bg-slate-100 rounded-xl w-full aspect-[4/3]">
          {isLoading ? (
            <Loader2 size={48} className="text-cyan-500 animate-spin" />
          ) : isWaiting ? (
            <div className="text-slate-400 text-sm">Waiting...</div>
          ) : (
            <div className="text-slate-500">Failed to load</div>
          )}
        </div>
      </div>
    );
  }

  // Loaded state - clickable thumbnail
  return (
    <div className="flex flex-col items-center w-[85%] max-w-[450px] mx-auto">
      <div className="mb-2 bg-white/90 backdrop-blur-md border border-slate-200/50 px-4 py-2 rounded-xl shadow-sm">
        <span className="text-sm font-medium text-slate-700">{page.pageName}</span>
      </div>

      <button
        onClick={() => onTap(page, pageImage)}
        className="relative shadow-2xl select-none cursor-pointer hover:ring-4 hover:ring-cyan-400/50 transition-all rounded-sm overflow-hidden w-full"
        {...(isFirstPage && { 'data-tutorial': 'first-page-result' })}
      >
        <img
          src={pageImage.dataUrl}
          alt={page.pageName}
          className="w-full h-auto"
          draggable={false}
        />

        {/* Text highlights from agent */}
        {page.highlights && page.highlights.length > 0 && (
          <TextHighlightOverlay
            highlights={page.highlights}
            imageWidth={pageImage.width}
            imageHeight={pageImage.height}
            originalWidth={page.imageWidth}
            originalHeight={page.imageHeight}
          />
        )}

        {/* Legacy pointer overlays */}
        {page.pointers.map((pointer) => (
          <div
            key={pointer.pointerId}
            className="absolute border-2 border-cyan-500/70 bg-cyan-500/10"
            style={{
              left: `${pointer.bboxX * 100}%`,
              top: `${pointer.bboxY * 100}%`,
              width: `${pointer.bboxWidth * 100}%`,
              height: `${pointer.bboxHeight * 100}%`,
            }}
          />
        ))}

        {/* Tap hint overlay */}
        <div className="absolute inset-0 flex items-center justify-center bg-black/0 hover:bg-black/10 transition-colors">
          <span className="opacity-0 hover:opacity-100 text-white text-sm font-medium bg-black/50 px-3 py-1 rounded-full transition-opacity">
            Tap to zoom
          </span>
        </div>
      </button>
    </div>
  );
};

// Standalone page viewer - full-screen zoomable view for file tree selections
const StandalonePageViewer: React.FC<{
  page: AgentSelectedPage;
}> = ({ page }) => {
  const [pageImage, setPageImage] = useState<PageImage | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Load the page image
  useEffect(() => {
    setIsLoading(true);
    loadPageImage(page).then((img) => {
      setPageImage(img);
      setIsLoading(false);
    });
  }, [page.pageId, page.filePath]);

  if (isLoading) {
    return (
      <div className="w-full h-full flex items-center justify-center">
        <Loader2 size={48} className="text-cyan-500 animate-spin" />
      </div>
    );
  }

  if (!pageImage) {
    return (
      <div className="w-full h-full flex items-center justify-center text-slate-500">
        Failed to load page
      </div>
    );
  }

  return (
    <TransformWrapper
      initialScale={1}
      minScale={0.1}
      maxScale={8}
      centerOnInit={true}
      doubleClick={{ mode: 'reset' }}
      panning={{ velocityDisabled: true }}
      wheel={{ step: 0.05 }}
    >
      <TransformComponent
        wrapperStyle={{ width: '100%', height: '100%' }}
        contentStyle={{ width: '100%', height: '100%' }}
      >
        <div className="w-full h-full flex items-center justify-center p-4">
          <img
            src={pageImage.dataUrl}
            alt={page.pageName}
            style={{
              maxWidth: '100%',
              maxHeight: '100%',
              objectFit: 'contain',
            }}
            draggable={false}
          />
        </div>
      </TransformComponent>
    </TransformWrapper>
  );
};

export const FeedViewer: React.FC<FeedViewerProps> = ({
  feedItems,
  isStreaming,
  streamingText,
  streamingTrace = [],
  currentTool,
  tutorialText,
  tutorialStep,
  onExpandedPageClose,
}) => {
  // Scroll container ref and auto-scroll logic
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const isNearBottomRef = useRef(true);

  // Container width for page sizing
  const [containerWidth, setContainerWidth] = useState(800);

  // Random greeting for empty state
  const [greeting] = useState(
    () => WELCOME_GREETINGS[Math.floor(Math.random() * WELCOME_GREETINGS.length)]
  );

  // Expanded page state for modal
  const [expandedPage, setExpandedPage] = useState<{
    page: AgentSelectedPage;
    pageImage: PageImage;
  } | null>(null);

  // Handler for opening expanded view
  const handlePageTap = useCallback((page: AgentSelectedPage, pageImage: PageImage) => {
    setExpandedPage({ page, pageImage });
  }, []);

  // Handler for closing expanded view
  const handleCloseExpanded = useCallback(() => {
    setExpandedPage(null);
    onExpandedPageClose?.();
  }, [onExpandedPageClose]);

  // Track scroll position to enable smart auto-scroll
  const handleScroll = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const threshold = 100;
    isNearBottomRef.current =
      container.scrollHeight - container.scrollTop - container.clientHeight < threshold;
  }, []);

  // Auto-scroll when feedItems change (only if user was near bottom)
  useEffect(() => {
    if (isNearBottomRef.current && scrollContainerRef.current) {
      scrollContainerRef.current.scrollTo({
        top: scrollContainerRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, [feedItems.length]);

  // Measure container width
  useEffect(() => {
    const updateWidth = () => {
      if (scrollContainerRef.current) {
        // Leave padding on sides
        const width = scrollContainerRef.current.clientWidth - 48;
        setContainerWidth(Math.min(width, 1200)); // Cap at reasonable max
      }
    };

    // Delayed update for orientation change (iOS animation completion)
    const handleOrientationChange = () => {
      setTimeout(updateWidth, 100);
    };

    // Initial measurement - immediate + delayed to catch layout completion
    updateWidth();
    const initialTimer = setTimeout(updateWidth, 100);

    window.addEventListener('resize', updateWidth);
    window.addEventListener('orientationchange', handleOrientationChange);
    return () => {
      clearTimeout(initialTimer);
      window.removeEventListener('resize', updateWidth);
      window.removeEventListener('orientationchange', handleOrientationChange);
    };
  }, []);

  // Empty state - hide greeting during tutorial modal steps (modal covers it otherwise)
  if (feedItems.length === 0 && !isStreaming) {
    // Don't show greeting during CTA or pick-sheet steps - the modal would cover it
    if (tutorialStep === 'cta' || tutorialStep === 'pick-sheet') {
      return <div className="flex-1 blueprint-grid" />;
    }
    const displayText = tutorialText || greeting;
    return (
      <div className="flex-1 flex items-center justify-center h-full blueprint-grid">
        {(displayText || currentTool) && (
          <MaestroText
            text={displayText || ''}
            state={currentTool ? 'working' : 'typing'}
          />
        )}
      </div>
    );
  }

  // Standalone page view - full-screen zoomable viewer for file tree selection
  const standaloneItem = feedItems.find((item) => item.type === 'standalone-page');
  if (standaloneItem && standaloneItem.type === 'standalone-page') {
    return (
      <div className="flex-1 overflow-hidden blueprint-grid" data-tutorial="page-viewer">
        <StandalonePageViewer page={standaloneItem.page} />
      </div>
    );
  }

  // Track if we've seen the first pages cluster for tutorial targeting
  let isFirstPagesCluster = true;

  return (
    <div
      ref={scrollContainerRef}
      className="flex-1 overflow-y-auto blueprint-grid px-6 pt-8 pb-48 flex flex-col items-center"
      onScroll={handleScroll}
      data-scroll-container
    >
      <div className="space-y-6 w-full" style={{ maxWidth: containerWidth }}>
        {feedItems.map((item) => {
          switch (item.type) {
            case 'user-query':
              return (
                <div key={item.id} className="flex justify-end max-w-4xl mx-auto">
                  <div className="max-w-[80%] bg-blue-600 text-white rounded-2xl px-4 py-3 shadow-md">
                    {item.text}
                  </div>
                </div>
              );

            case 'pages': {
              // Pages cluster - thumbnails are sized in FeedPageItemDisplay
              // Uses sequential loading to avoid memory pressure
              const isFirst = isFirstPagesCluster;
              isFirstPagesCluster = false;
              return (
                <div key={item.id} className="mx-auto" style={{ maxWidth: containerWidth }}>
                  <PagesCluster
                    pages={item.pages}
                    containerWidth={containerWidth}
                    onTap={handlePageTap}
                    isFirstCluster={isFirst}
                  />
                </div>
              );
            }

            case 'text':
              return (
                <div key={item.id} className="py-2 mx-auto" style={{ maxWidth: containerWidth }}>
                  {/* ThinkingSection for completed responses */}
                  {item.trace.length > 0 && (
                    <div className="mb-3">
                      <ThinkingSection
                        reasoning={[]}
                        isStreaming={false}
                        autoCollapse={false}
                        trace={item.trace}
                        initialElapsedTime={item.elapsedTime}
                      />
                    </div>
                  )}
                  <div className="text-slate-700 text-base leading-relaxed">
                    <ReactMarkdown
                      components={{
                        p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
                        strong: ({ children }) => <strong className="font-semibold text-slate-800">{children}</strong>,
                        ul: ({ children }) => <ul className="mb-3 ml-4 list-disc space-y-1">{children}</ul>,
                        ol: ({ children }) => <ol className="mb-3 ml-4 list-decimal space-y-1">{children}</ol>,
                        li: ({ children }) => <li>{children}</li>,
                        h1: ({ children }) => <h1 className="text-lg font-semibold text-slate-800 mb-2 mt-4 first:mt-0">{children}</h1>,
                        h2: ({ children }) => <h2 className="text-base font-semibold text-slate-800 mb-2 mt-3 first:mt-0">{children}</h2>,
                        h3: ({ children }) => <h3 className="text-base font-medium text-slate-800 mb-1 mt-2 first:mt-0">{children}</h3>,
                        code: ({ children }) => <code className="bg-slate-100 px-1 py-0.5 rounded text-sm font-mono">{children}</code>,
                      }}
                    >
                      {item.content}
                    </ReactMarkdown>
                  </div>
                </div>
              );

            default:
              return null;
          }
        })}

        {/* Streaming response with live ThinkingSection */}
        {isStreaming && (
          <div className="py-2 mx-auto" style={{ maxWidth: containerWidth }}>
            {/* Live ThinkingSection during streaming */}
            <div className="mb-3">
              <ThinkingSection
                reasoning={[]}
                isStreaming={true}
                autoCollapse={false}
                trace={streamingTrace}
              />
            </div>
            {/* Streaming text (final answer) */}
            {streamingText && (
              <div className="text-slate-700 text-base leading-relaxed">
                <ReactMarkdown
                  components={{
                    p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
                    strong: ({ children }) => <strong className="font-semibold text-slate-800">{children}</strong>,
                    ul: ({ children }) => <ul className="mb-3 ml-4 list-disc space-y-1">{children}</ul>,
                    ol: ({ children }) => <ol className="mb-3 ml-4 list-decimal space-y-1">{children}</ol>,
                    li: ({ children }) => <li>{children}</li>,
                    h1: ({ children }) => <h1 className="text-lg font-semibold text-slate-800 mb-2 mt-4 first:mt-0">{children}</h1>,
                    h2: ({ children }) => <h2 className="text-base font-semibold text-slate-800 mb-2 mt-3 first:mt-0">{children}</h2>,
                    h3: ({ children }) => <h3 className="text-base font-medium text-slate-800 mb-1 mt-2 first:mt-0">{children}</h3>,
                    code: ({ children }) => <code className="bg-slate-100 px-1 py-0.5 rounded text-sm font-mono">{children}</code>,
                  }}
                >
                  {streamingText}
                </ReactMarkdown>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Expanded page modal */}
      {expandedPage && (
        <ExpandedPageModal
          page={expandedPage.page}
          pageImage={expandedPage.pageImage}
          onClose={handleCloseExpanded}
          tutorialStep={tutorialStep}
        />
      )}
    </div>
  );
};
