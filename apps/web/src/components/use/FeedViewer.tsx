import React, { useState, useRef, useEffect, useCallback } from 'react';
import * as pdfjs from 'pdfjs-dist';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';
import { Loader2 } from 'lucide-react';
import { downloadFile, getPublicUrl } from '../../lib/storage';
import { AgentSelectedPage } from '../field';
import { MaestroText } from './MaestroText';

// Set up PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

// Render scale for PNG conversion (3x for sharp rendering on iPad)
const RENDER_SCALE = 3;

// Feed item types
export type FeedItem =
  | { type: 'user-query'; id: string; text: string; timestamp: number }
  | { type: 'pages'; id: string; pages: AgentSelectedPage[]; timestamp: number }
  | { type: 'text'; id: string; content: string; timestamp: number };

interface PageImage {
  dataUrl: string;
  width: number;
  height: number;
}

interface FeedViewerProps {
  feedItems: FeedItem[];
  isStreaming: boolean;
  streamingText?: string;
  currentTool?: string | null;
  tutorialText?: string;
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

// Reusable function to load a page image
async function loadPageImage(page: AgentSelectedPage): Promise<PageImage | null> {
  const cached = pageImageCache.get(page.pageId);
  if (cached) return cached;

  const existing = loadingPromises.get(page.pageId);
  if (existing) return existing;

  const promise = (async () => {
    try {
      // PNG path - use public URL for fast loading
      if (page.filePath.endsWith('.png')) {
        const url = getPublicUrl(page.filePath);
        const img = new Image();
        img.src = url;
        await img.decode();

        const pageImage: PageImage = {
          dataUrl: url,
          width: img.naturalWidth / RENDER_SCALE,
          height: img.naturalHeight / RENDER_SCALE,
        };

        pageImageCache.set(page.pageId, pageImage);
        return pageImage;
      }

      // PDF fallback - download and render via PDF.js
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
      console.error('Failed to load page:', page.pageId, err);
      return null;
    } finally {
      loadingPromises.delete(page.pageId);
    }
  })();

  loadingPromises.set(page.pageId, promise);
  return promise;
}

// Single page component with its own TransformWrapper
const FeedPageItem: React.FC<{
  page: AgentSelectedPage;
  containerWidth: number;
}> = ({ page, containerWidth }) => {
  const [pageImage, setPageImage] = useState<PageImage | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setIsLoading(true);
    loadPageImage(page).then((img) => {
      setPageImage(img);
      setIsLoading(false);
    });
  }, [page.pageId, page.filePath]);

  // Calculate display dimensions to fit container width
  const displayDimensions = pageImage
    ? (() => {
        const imgWidth = pageImage.width;
        const imgHeight = pageImage.height;
        // Fit to container width, maintain aspect ratio
        const scale = Math.min(containerWidth / imgWidth, 1);
        return {
          width: imgWidth * scale,
          height: imgHeight * scale,
        };
      })()
    : { width: containerWidth, height: 600 };

  if (isLoading) {
    return (
      <div
        className="flex items-center justify-center bg-slate-100 rounded-xl"
        style={{ width: containerWidth, height: 400 }}
      >
        <Loader2 size={48} className="text-cyan-500 animate-spin" />
      </div>
    );
  }

  if (!pageImage) {
    return (
      <div
        className="flex items-center justify-center bg-slate-100 rounded-xl text-slate-500"
        style={{ width: containerWidth, height: 200 }}
      >
        Failed to load page
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center">
      {/* Page name badge */}
      <div className="mb-2 bg-white/90 backdrop-blur-md border border-slate-200/50 px-4 py-2 rounded-xl shadow-sm">
        <span className="text-sm font-medium text-slate-700">{page.pageName}</span>
      </div>

      {/* Page with zoom/pan */}
      <div
        style={{
          width: displayDimensions.width,
          height: displayDimensions.height,
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
            wrapperStyle={{ width: '100%', height: '100%' }}
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

              {/* Pointer overlays */}
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

export const FeedViewer: React.FC<FeedViewerProps> = ({
  feedItems,
  isStreaming,
  streamingText,
  currentTool,
  tutorialText,
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

    updateWidth();
    window.addEventListener('resize', updateWidth);
    return () => window.removeEventListener('resize', updateWidth);
  }, []);

  // Empty state
  if (feedItems.length === 0 && !isStreaming) {
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

  return (
    <div
      ref={scrollContainerRef}
      className="flex-1 overflow-y-auto blueprint-grid px-6 py-8"
      onScroll={handleScroll}
    >
      <div className="max-w-4xl mx-auto space-y-6">
        {feedItems.map((item) => {
          switch (item.type) {
            case 'user-query':
              return (
                <div key={item.id} className="flex justify-end">
                  <div className="max-w-[80%] bg-blue-600 text-white rounded-2xl px-4 py-3 shadow-md">
                    {item.text}
                  </div>
                </div>
              );

            case 'pages':
              return (
                <div key={item.id} className="space-y-8">
                  {item.pages.map((page) => (
                    <FeedPageItem
                      key={page.pageId}
                      page={page}
                      containerWidth={containerWidth}
                    />
                  ))}
                </div>
              );

            case 'text':
              return (
                <div key={item.id} className="max-w-2xl">
                  <div className="bg-white/80 backdrop-blur-md border border-slate-200/50 rounded-2xl shadow-lg p-4">
                    <p className="text-slate-700 whitespace-pre-wrap">{item.content}</p>
                  </div>
                </div>
              );

            default:
              return null;
          }
        })}

        {/* Streaming indicator while processing */}
        {isStreaming && (
          <div className="max-w-2xl">
            <div className="bg-white/80 backdrop-blur-md border border-slate-200/50 rounded-2xl shadow-lg p-4 animate-pulse">
              {streamingText ? (
                <p className="text-slate-700 whitespace-pre-wrap">{streamingText}</p>
              ) : currentTool ? (
                <div className="flex items-center gap-2 text-slate-500">
                  <Loader2 size={16} className="animate-spin" />
                  <span>Working...</span>
                </div>
              ) : (
                <div className="flex items-center gap-2 text-slate-500">
                  <Loader2 size={16} className="animate-spin" />
                  <span>Thinking...</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
