import React, { useState, useRef, useEffect, useMemo } from 'react';
import * as pdfjs from 'pdfjs-dist';
import { TransformWrapper, TransformComponent, ReactZoomPanPinchRef } from 'react-zoom-pan-pinch';
import { Square, ChevronLeft, ChevronRight, FileText, Loader2, AlertCircle } from 'lucide-react';
import { ContextPointer } from '../../types';
import { api } from '../../lib/api';
import { getPublicUrl } from '../../lib/storage';

// Set up PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

// Render scale for PNG conversion (3 = sharp up to 3x zoom on iPad)
const RENDER_SCALE = 3;

interface PageImage {
  dataUrl: string;
  width: number;
  height: number;
}

// Cache for rendered page images (matches PlanViewer pattern)
const pageImageCache = new Map<string, PageImage>();

// Track in-flight loads to avoid duplicate renders
const loadingPromises = new Map<string, Promise<PageImage | null>>();

// Reusable function to render a single page (matches PlanViewer pattern)
async function renderPageImage(
  pdfDoc: pdfjs.PDFDocumentProxy,
  pageNum: number,
  cacheKey: string
): Promise<PageImage | null> {
  // Check cache first
  const cached = pageImageCache.get(cacheKey);
  if (cached) return cached;

  // Check if already loading
  const existing = loadingPromises.get(cacheKey);
  if (existing) return existing;

  // Start loading
  const promise = (async () => {
    try {
      const page = await pdfDoc.getPage(pageNum);
      const viewport = page.getViewport({ scale: RENDER_SCALE });

      const canvas = document.createElement('canvas');
      const context = canvas.getContext('2d')!;
      canvas.width = viewport.width;
      canvas.height = viewport.height;

      await page.render({
        canvasContext: context,
        viewport: viewport,
      }).promise;

      const dataUrl = canvas.toDataURL('image/png');

      // Pre-decode the image so it's ready for instant display (critical for iPad)
      const img = new Image();
      img.src = dataUrl;
      await img.decode();

      const pageImage: PageImage = {
        dataUrl,
        width: viewport.width / RENDER_SCALE,
        height: viewport.height / RENDER_SCALE,
      };

      pageImageCache.set(cacheKey, pageImage);
      return pageImage;
    } catch (err) {
      console.error('Failed to render page:', pageNum, err);
      return null;
    } finally {
      loadingPromises.delete(cacheKey);
    }
  })();

  loadingPromises.set(cacheKey, promise);
  return promise;
}

interface PdfViewerProps {
  file?: File;
  fileId?: string;
  pointers: ContextPointer[];
  setPointers?: React.Dispatch<React.SetStateAction<ContextPointer[]>>;  // Optional - only used as fallback
  selectedPointerId: string | null;
  setSelectedPointerId: (id: string | null) => void;
  isDrawingEnabled: boolean;
  setIsDrawingEnabled: (enabled: boolean) => void;
  onPointerCreate?: (data: {
    pageNumber: number;
    bounds: { xNorm: number; yNorm: number; wNorm: number; hNorm: number };
  }) => Promise<ContextPointer | null>;
  isLoadingFile?: boolean;
  fileLoadError?: string | null;
  highlightedBounds?: { x: number; y: number; w: number; h: number } | null;
  refreshTrigger?: number;  // Increment to re-check PNG availability
  leftSidebarWidth?: number;  // For visible-area centering
  rightSidebarWidth?: number;
}

export const PdfViewer: React.FC<PdfViewerProps> = ({
  file,
  fileId,
  pointers,
  setPointers,
  selectedPointerId,
  setSelectedPointerId,
  isDrawingEnabled,
  setIsDrawingEnabled,
  onPointerCreate,
  isLoadingFile,
  fileLoadError,
  highlightedBounds,
  refreshTrigger,
  leftSidebarWidth = 288,
  rightSidebarWidth = 400,
}) => {
  // PDF document state (on-demand rendering like PlanViewer)
  const [pdfDoc, setPdfDoc] = useState<pdfjs.PDFDocumentProxy | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [isLoadingPdf, setIsLoadingPdf] = useState(false);

  // Current page image (rendered on-demand or from pre-rendered PNG)
  const [currentPageImage, setCurrentPageImage] = useState<PageImage | null>(null);
  const [isRenderingPage, setIsRenderingPage] = useState(false);

  // Pre-rendered PNG state
  const [preRenderedImageUrl, setPreRenderedImageUrl] = useState<string | null>(null);
  const [usePreRendered, setUsePreRendered] = useState(false);

  // Viewer state
  const [pageNumber, setPageNumber] = useState(1);

  // Drawing state
  const [isDrawing, setIsDrawing] = useState(false);
  const [startPos, setStartPos] = useState({ x: 0, y: 0 });
  const [tempRect, setTempRect] = useState<{ x: number, y: number, w: number, h: number } | null>(null);

  // Container size for fit calculation
  const [containerSize, setContainerSize] = useState({ width: 800, height: 600 });

  // Refs
  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLDivElement>(null);
  const transformRef = useRef<ReactZoomPanPinchRef>(null);

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

  // Check for pre-rendered PNG when fileId changes
  useEffect(() => {
    if (!fileId) {
      setPreRenderedImageUrl(null);
      setUsePreRendered(false);
      return;
    }

    const checkPreRendered = async () => {
      try {
        const pageData = await api.pages.get(fileId);
        if (pageData.pageImageReady && pageData.pageImagePath) {
          // Use pre-rendered PNG
          const url = getPublicUrl(pageData.pageImagePath);
          setPreRenderedImageUrl(url);
          setUsePreRendered(true);
          setNumPages(1); // Single-page PDFs for now
          setIsLoadingPdf(false);
        } else {
          // Fall back to PDF.js rendering
          setPreRenderedImageUrl(null);
          setUsePreRendered(false);
        }
      } catch (err) {
        // Page data not available, fall back to PDF.js
        console.log('Pre-rendered check failed, using PDF.js:', err);
        setPreRenderedImageUrl(null);
        setUsePreRendered(false);
      }
    };

    checkPreRendered();
  }, [fileId, refreshTrigger]);

  // Load PDF document when file changes (don't render all pages upfront)
  // Skip if we're using pre-rendered PNG
  useEffect(() => {
    if (!file || usePreRendered) {
      if (!usePreRendered) {
        setPdfDoc(null);
        setNumPages(0);
        setCurrentPageImage(null);
        setPageNumber(1);
      }
      return;
    }

    const loadPdf = async () => {
      setIsLoadingPdf(true);
      setPdfDoc(null);
      setCurrentPageImage(null);
      setPageNumber(1);
      // Reset will be applied with offset when image loads

      try {
        const arrayBuffer = await file.arrayBuffer();
        const pdf = await pdfjs.getDocument({ data: arrayBuffer }).promise;
        setPdfDoc(pdf);
        setNumPages(pdf.numPages);
      } catch (error) {
        console.error('PDF loading failed:', error);
      } finally {
        setIsLoadingPdf(false);
      }
    };

    loadPdf();
  }, [file, usePreRendered]);

  // Render current page on-demand when page changes (matches PlanViewer pattern)
  // If using pre-rendered PNG, load it instead of PDF.js rendering
  useEffect(() => {
    // Case 1: Using pre-rendered PNG
    if (usePreRendered && preRenderedImageUrl) {
      setIsRenderingPage(true);

      // Load pre-rendered PNG
      const img = new Image();
      img.onload = () => {
        const pageImage: PageImage = {
          dataUrl: preRenderedImageUrl,
          width: img.naturalWidth,
          height: img.naturalHeight,
        };
        setCurrentPageImage(pageImage);
        setIsRenderingPage(false);
      };
      img.onerror = () => {
        console.error('Failed to load pre-rendered PNG, falling back to PDF.js');
        setUsePreRendered(false);
        setPreRenderedImageUrl(null);
        setIsRenderingPage(false);
      };
      img.src = preRenderedImageUrl;
      return;
    }

    // Case 2: Using PDF.js rendering
    if (!pdfDoc || !fileId) {
      setCurrentPageImage(null);
      return;
    }

    const cacheKey = `${fileId}-page-${pageNumber}`;

    // Check cache first for instant display
    const cached = pageImageCache.get(cacheKey);
    if (cached) {
      setCurrentPageImage(cached);
      return;
    }

    // Render the page
    setIsRenderingPage(true);
    renderPageImage(pdfDoc, pageNumber, cacheKey).then(pageImage => {
      if (pageImage) {
        setCurrentPageImage(pageImage);
      }
      setIsRenderingPage(false);
    });
  }, [pdfDoc, pageNumber, fileId, usePreRendered, preRenderedImageUrl]);

  // Calculate X offset to center in visible area (between sidebars)
  // Offset = (leftSidebarWidth - rightSidebarWidth) / 2
  // Negative offset shifts content left when right sidebar is wider
  const visibleAreaOffset = useMemo(() => {
    return (leftSidebarWidth - rightSidebarWidth) / 2;
  }, [leftSidebarWidth, rightSidebarWidth]);

  // Reset transform when page changes or image loads, applying visible-area centering offset
  useEffect(() => {
    if (transformRef.current && currentPageImage) {
      transformRef.current.resetTransform();
      // Apply offset after reset to center in visible area
      // Small delay to ensure reset completes first
      setTimeout(() => {
        transformRef.current?.setTransform(visibleAreaOffset, 0, 1);
      }, 50);
    }
  }, [pageNumber, currentPageImage, visibleAreaOffset]);

  // Page navigation
  const goToPrevPage = () => setPageNumber(prev => Math.max(prev - 1, 1));
  const goToNextPage = () => setPageNumber(prev => Math.min(prev + 1, numPages));

  // Drawing handlers (Pointer Events for mouse, touch, and Apple Pencil support)
  const getNormalizedCoords = (e: React.PointerEvent) => {
    if (!imageRef.current) return { x: 0, y: 0 };
    const rect = imageRef.current.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left) / rect.width,
      y: (e.clientY - rect.top) / rect.height
    };
  };

  const handlePointerDown = (e: React.PointerEvent) => {
    // Only pen (Apple Pencil) and mouse can draw - finger touch passes through to pan/zoom
    if (!isDrawingEnabled || e.pointerType === 'touch') return;
    e.preventDefault();
    e.stopPropagation();
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    const coords = getNormalizedCoords(e);
    setStartPos(coords);
    setIsDrawing(true);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDrawing || !isDrawingEnabled) return;
    e.preventDefault();
    e.stopPropagation();
    const coords = getNormalizedCoords(e);

    setTempRect({
      x: Math.min(startPos.x, coords.x),
      y: Math.min(startPos.y, coords.y),
      w: Math.abs(coords.x - startPos.x),
      h: Math.abs(coords.y - startPos.y)
    });
  };

  const handlePointerUp = async (e: React.PointerEvent) => {
    (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    if (!isDrawing || !tempRect) {
      setIsDrawing(false);
      return;
    }

    const bounds = {
      xNorm: tempRect.x,
      yNorm: tempRect.y,
      wNorm: tempRect.w,
      hNorm: tempRect.h
    };

    setIsDrawing(false);
    setTempRect(null);

    // Use callback if provided (for API integration)
    // State updates are handled by SetupMode's handlePointerCreate
    if (onPointerCreate) {
      await onPointerCreate({ pageNumber, bounds });
      return;
    }

    // Fallback to local-only pointer creation (should not normally reach here)
    if (setPointers) {
      const newPointer: ContextPointer = {
        id: crypto.randomUUID(),
        pageId: fileId || '',
        title: 'New Context',
        description: 'Add description...',
        bboxX: bounds.xNorm,
        bboxY: bounds.yNorm,
        bboxWidth: bounds.wNorm,
        bboxHeight: bounds.hNorm,
      };

      setPointers(prev => [...prev, newPointer]);
      setSelectedPointerId(newPointer.id);
    }
  };

  // Current page data - memoized to prevent unnecessary re-renders
  const currentPagePointers = useMemo(
    () => pointers.filter(p => p.pageId === fileId),
    [pointers, fileId]
  );

  // Diagnostic logging for pointer-page mismatches
  useEffect(() => {
    if (pointers.length > 0) {
      const matching = currentPagePointers.length;
      const nonMatching = pointers.length - matching;
      if (nonMatching > 0) {
        console.warn(`[PdfViewer] ${nonMatching} pointers don't match current page!`);
        console.warn(`  Current page: ${fileId}`);
        console.warn(`  Non-matching pointers:`, pointers.filter(p => p.pageId !== fileId).map(p => ({
          id: p.id,
          pageId: p.pageId,
          title: p.title,
        })));
      }
    }
  }, [pointers, fileId, currentPagePointers.length]);

  // Calculate display dimensions to fit container at zoom=1 - memoized
  const displayDimensions = useMemo(() => {
    if (!currentPageImage) return { width: 800, height: 600 };

    const imgWidth = currentPageImage.width;
    const imgHeight = currentPageImage.height;

    // Calculate scale to fit within container (with some padding)
    const scaleX = containerSize.width / imgWidth;
    const scaleY = containerSize.height / imgHeight;
    const fitScale = Math.min(scaleX, scaleY, 1); // Don't scale up beyond 1

    return {
      width: imgWidth * fitScale,
      height: imgHeight * fitScale,
    };
  }, [currentPageImage, containerSize.width, containerSize.height]);

  // Loading state - file is being fetched from storage
  if (isLoadingFile) {
    return (
      <div className="flex-1 flex items-center justify-center h-full">
        <div className="text-center text-slate-400">
          <Loader2 size={48} className="mx-auto mb-4 text-cyan-400 animate-spin" />
          <p className="text-sm font-medium">Loading file from storage...</p>
        </div>
      </div>
    );
  }

  // Error state - file failed to load
  if (fileLoadError) {
    return (
      <div className="flex-1 flex items-center justify-center h-full">
        <div className="text-center text-slate-400 max-w-md px-4">
          <AlertCircle size={48} className="mx-auto mb-4 text-amber-400" />
          <p className="text-sm font-medium text-amber-300 mb-2">Unable to load file</p>
          <p className="text-xs text-slate-500">{fileLoadError}</p>
        </div>
      </div>
    );
  }

  // Empty state - no file selected and no pre-rendered image
  if (!file && !usePreRendered) {
    return (
      <div className="flex-1 flex items-center justify-center h-full">
        <div className="text-center text-slate-500">
          <FileText size={48} className="mx-auto mb-3 text-slate-600" />
          <p className="text-sm">Select a PDF file to view</p>
        </div>
      </div>
    );
  }

  // Loading PDF state (only when not using pre-rendered)
  if (isLoadingPdf && !usePreRendered) {
    return (
      <div className="flex-1 flex items-center justify-center h-full">
        <div className="text-center text-slate-400">
          <Loader2 size={48} className="mx-auto mb-4 text-cyan-400 animate-spin" />
          <p className="text-sm font-medium">Loading PDF...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col h-full relative overflow-hidden">
      {/* Fallback rendering warning */}
      {!usePreRendered && fileId && (
        <div className="absolute top-4 left-4 z-20 bg-yellow-500/20 text-yellow-300 px-3 py-1.5 rounded-lg text-xs flex items-center gap-1.5 animate-fade-in">
          <AlertCircle size={14} />
          Using local rendering
        </div>
      )}

      {/* Toolbar - Single rectangle toggle button */}
      <div className="absolute top-4 right-4 z-40 glass rounded-xl p-1.5 toolbar-float animate-fade-in">
        <button
          onClick={() => setIsDrawingEnabled(!isDrawingEnabled)}
          className={`p-2.5 rounded-lg transition-all ${
            isDrawingEnabled
              ? 'bg-cyan-500/20 text-cyan-400 shadow-glow-cyan-sm'
              : 'text-slate-400 hover:bg-white/10 hover:text-white'
          }`}
          title={isDrawingEnabled ? 'Drawing enabled - click to disable' : 'Click to enable drawing'}
        >
          <Square size={18} />
        </button>
      </div>

      {/* Page Navigation */}
      {numPages > 1 && (
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 glass rounded-xl px-3 py-2 animate-fade-in">
          <button
            onClick={goToPrevPage}
            disabled={pageNumber <= 1}
            className="p-1.5 hover:bg-white/10 rounded-lg text-slate-300 hover:text-white transition-all disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronLeft size={18} />
          </button>
          <span className="text-sm text-slate-300 min-w-[80px] text-center">
            {pageNumber} / {numPages}
          </span>
          <button
            onClick={goToNextPage}
            disabled={pageNumber >= numPages}
            className="p-1.5 hover:bg-white/10 rounded-lg text-slate-300 hover:text-white transition-all disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronRight size={18} />
          </button>
        </div>
      )}

      {/* Canvas Area - pinch-to-zoom enabled */}
      <div
        ref={containerRef}
        className="flex-1 canvas-grid"
        style={{ position: 'relative' }}
      >
        {/* Page rendering indicator */}
        {isRenderingPage && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900/50 z-10">
            <Loader2 size={48} className="text-cyan-500 animate-spin" />
          </div>
        )}

        {currentPageImage && (
          <TransformWrapper
            ref={transformRef}
            initialScale={1}
            minScale={0.5}
            maxScale={5}
            centerOnInit={true}
            doubleClick={{ mode: 'reset' }}
            panning={{ disabled: isDrawingEnabled, velocityDisabled: true }}
            pinch={{ disabled: isDrawingEnabled }}
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
                ref={imageRef}
                className="relative shadow-2xl select-none"
                style={{
                  cursor: isDrawingEnabled ? 'crosshair' : 'default',
                  width: displayDimensions.width,
                  height: displayDimensions.height,
                  touchAction: isDrawingEnabled ? 'none' : 'auto',
                }}
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                onPointerCancel={handlePointerUp}
              >
                {/* The actual page image */}
                <img
                  src={currentPageImage.dataUrl}
                  alt={`Page ${pageNumber}`}
                  className="max-w-none w-full h-full"
                  draggable={false}
                />

                {/* Annotation overlays - simplified for iOS Safari compatibility */}
                {currentPagePointers.map(p => (
                  <div
                    key={p.id}
                    onClick={() => setSelectedPointerId(p.id)}
                    className={`absolute border cursor-pointer group ${
                      selectedPointerId === p.id
                        ? 'border-cyan-400 bg-cyan-400/25'
                        : 'border-cyan-500/70 bg-cyan-500/10 hover:bg-cyan-500/20'
                    }`}
                    style={{
                      left: `${p.bboxX * 100}%`,
                      top: `${p.bboxY * 100}%`,
                      width: `${p.bboxWidth * 100}%`,
                      height: `${p.bboxHeight * 100}%`,
                    }}
                  >
                    <div className="opacity-0 group-hover:opacity-100 absolute -top-8 left-1/2 -translate-x-1/2 bg-slate-800/90 px-2 py-1 rounded text-xs text-white whitespace-nowrap z-10 pointer-events-none transition-opacity">
                      {p.title}
                    </div>
                  </div>
                ))}

                {/* Highlighted pointer (from context panel) */}
                {highlightedBounds && (
                  <div
                    className="absolute border border-orange-400 bg-orange-400/20 rounded-sm
                               shadow-[0_0_20px_rgba(249,115,22,0.5)] pointer-events-none z-20"
                    style={{
                      left: `${highlightedBounds.x * 100}%`,
                      top: `${highlightedBounds.y * 100}%`,
                      width: `${highlightedBounds.w * 100}%`,
                      height: `${highlightedBounds.h * 100}%`,
                    }}
                  />
                )}

                {/* Temp drawing rect */}
                {tempRect && (
                  <div
                    className="absolute border border-cyan-400 bg-cyan-400/15 rounded-sm shadow-glow-cyan"
                    style={{
                      left: `${tempRect.x * 100}%`,
                      top: `${tempRect.y * 100}%`,
                      width: `${tempRect.w * 100}%`,
                      height: `${tempRect.h * 100}%`,
                    }}
                  />
                )}
              </div>
            </TransformComponent>
          </TransformWrapper>
        )}
      </div>
    </div>
  );
};
