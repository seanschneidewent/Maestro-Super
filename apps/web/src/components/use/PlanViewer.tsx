import React, { useState, useRef, useEffect, useCallback } from 'react';
import * as pdfjs from 'pdfjs-dist';
import { TransformWrapper, TransformComponent, useControls } from 'react-zoom-pan-pinch';
import { ZoomIn, ZoomOut, Maximize, ChevronLeft, ChevronRight, FileText, Loader2, AlertCircle } from 'lucide-react';
import { api, PointerResponse } from '../../lib/api';
import { downloadFile, blobToFile } from '../../lib/storage';
import { AgentSelectedPage } from '../field';

// Set up PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

// Render scale for PNG conversion (2 = retina quality)
const RENDER_SCALE = 2;

// Zoom controls component that uses the library's API
const ZoomControls: React.FC = () => {
  const { zoomIn, zoomOut, resetTransform } = useControls();

  return (
    <div className="absolute top-4 right-4 z-20 flex flex-col gap-1 bg-white/90 backdrop-blur-md border border-slate-200/50 rounded-xl p-1.5 shadow-sm">
      <button
        onClick={() => zoomIn()}
        className="p-2.5 hover:bg-slate-100 rounded-lg text-slate-500 hover:text-slate-700 transition-all"
        title="Zoom In"
      >
        <ZoomIn size={18} />
      </button>
      <button
        onClick={() => zoomOut()}
        className="p-2.5 hover:bg-slate-100 rounded-lg text-slate-500 hover:text-slate-700 transition-all"
        title="Zoom Out"
      >
        <ZoomOut size={18} />
      </button>
      <button
        onClick={() => resetTransform()}
        className="p-2.5 hover:bg-slate-100 rounded-lg text-slate-500 hover:text-slate-700 transition-all"
        title="Reset Zoom"
      >
        <Maximize size={18} />
      </button>
    </div>
  );
};

interface PageImage {
  dataUrl: string;
  width: number;
  height: number;
}

interface PlanViewerProps {
  pageId: string | null;
  onPointerClick?: (pointer: PointerResponse) => void;
  selectedPointerIds?: string[];
  // Multi-page mode props
  selectedPages?: AgentSelectedPage[];
  onVisiblePageChange?: (pageId: string, disciplineId: string) => void;
}

// Cache for rendered page images
const pageImageCache = new Map<string, PageImage>();

export const PlanViewer: React.FC<PlanViewerProps> = ({
  pageId,
  onPointerClick,
  selectedPointerIds = [],
  selectedPages = [],
  onVisiblePageChange,
}) => {
  // =====================================
  // ALL HOOKS MUST BE AT THE TOP (unconditionally)
  // =====================================

  // Page data (single-page mode)
  const [pageName, setPageName] = useState<string>('');
  const [pointers, setPointers] = useState<PointerResponse[]>([]);

  // File state (single-page mode)
  const [file, setFile] = useState<File | null>(null);
  const [isLoadingPage, setIsLoadingPage] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Page images (PNG data URLs)
  const [pageImages, setPageImages] = useState<PageImage[]>([]);
  const [isConverting, setIsConverting] = useState(false);
  const [conversionProgress, setConversionProgress] = useState({ current: 0, total: 0 });

  // Viewer state
  const [pageNumber, setPageNumber] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [hoveredPointerId, setHoveredPointerId] = useState<string | null>(null);

  // Container size for fit calculation
  const [containerSize, setContainerSize] = useState({ width: 800, height: 600 });

  // Refs
  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLDivElement>(null);
  const zoomCenterRef = useRef<{ x: number; y: number } | null>(null);

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
    if (touchStartY.current === null || zoom !== 1) return;

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
  }, [zoom, goToNextAgentPage, goToPrevAgentPage]);

  // Current agent page
  const currentAgentPage = selectedPages[agentPageIndex];

  // Agent page image state
  const [agentPageImage, setAgentPageImage] = useState<PageImage | null>(null);
  const [isLoadingAgentPage, setIsLoadingAgentPage] = useState(false);

  // Load agent page image when currentAgentPage changes
  useEffect(() => {
    if (!currentAgentPage) {
      setAgentPageImage(null);
      return;
    }

    // Check cache first
    const cached = pageImageCache.get(currentAgentPage.pageId);
    if (cached) {
      setAgentPageImage(cached);
      return;
    }

    const loadPage = async () => {
      setIsLoadingAgentPage(true);
      try {
        const blob = await downloadFile(currentAgentPage.filePath);
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
        const pageImage: PageImage = {
          dataUrl,
          width: viewport.width / RENDER_SCALE,
          height: viewport.height / RENDER_SCALE,
        };

        pageImageCache.set(currentAgentPage.pageId, pageImage);
        setAgentPageImage(pageImage);
      } catch (err) {
        console.error('Failed to load agent page:', currentAgentPage.pageId, err);
      } finally {
        setIsLoadingAgentPage(false);
      }
    };

    loadPage();
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

  // Load page data when pageId changes
  useEffect(() => {
    if (!pageId) {
      setFile(null);
      setPageImages([]);
      setPointers([]);
      setPageName('');
      return;
    }

    const loadPage = async () => {
      setIsLoadingPage(true);
      setLoadError(null);
      setFile(null);
      setPageImages([]);

      try {
        // Load page data and pointers in parallel
        const [pageData, pointersData] = await Promise.all([
          api.pages.get(pageId),
          api.pointers.list(pageId),
        ]);

        setPageName(pageData.pageName);
        setPointers(pointersData);

        // Download file from storage
        const blob = await downloadFile(pageData.filePath);
        const fileObj = blobToFile(blob, pageData.pageName);
        setFile(fileObj);
      } catch (err) {
        console.error('Failed to load page:', err);
        setLoadError(err instanceof Error ? err.message : 'Failed to load page');
      } finally {
        setIsLoadingPage(false);
      }
    };

    loadPage();
  }, [pageId]);

  // Convert PDF to PNGs when file changes
  useEffect(() => {
    if (!file) {
      setPageImages([]);
      setPageNumber(1);
      return;
    }

    const convertPdfToImages = async () => {
      setIsConverting(true);
      setPageImages([]);
      setPageNumber(1);
      setZoom(1);

      try {
        const arrayBuffer = await file.arrayBuffer();
        const pdf = await pdfjs.getDocument({ data: arrayBuffer }).promise;
        const numPages = pdf.numPages;

        setConversionProgress({ current: 0, total: numPages });

        const images: PageImage[] = [];

        for (let i = 1; i <= numPages; i++) {
          const page = await pdf.getPage(i);
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

          images.push({
            dataUrl,
            width: viewport.width / RENDER_SCALE,
            height: viewport.height / RENDER_SCALE,
          });

          setConversionProgress({ current: i, total: numPages });
        }

        setPageImages(images);
      } catch (error) {
        console.error('PDF conversion failed:', error);
        setLoadError('Failed to render PDF');
      } finally {
        setIsConverting(false);
      }
    };

    convertPdfToImages();
  }, [file]);

  // Zoom handlers
  const captureCenter = () => {
    if (!containerRef.current) return;
    const container = containerRef.current;
    zoomCenterRef.current = {
      x: (container.scrollLeft + container.clientWidth / 2) / container.scrollWidth,
      y: (container.scrollTop + container.clientHeight / 2) / container.scrollHeight,
    };
  };

  const handleZoomIn = () => {
    captureCenter();
    setZoom(prev => Math.min(prev + 0.25, 4));
  };

  const handleZoomOut = () => {
    captureCenter();
    setZoom(prev => Math.max(prev - 0.25, 0.5));
  };

  const handleZoomReset = () => {
    zoomCenterRef.current = null;
    setZoom(1);
  };

  // Restore center position after zoom changes
  useEffect(() => {
    if (!containerRef.current || !zoomCenterRef.current) return;

    requestAnimationFrame(() => {
      const container = containerRef.current;
      if (!container || !zoomCenterRef.current) return;

      const { x, y } = zoomCenterRef.current;
      container.scrollLeft = x * container.scrollWidth - container.clientWidth / 2;
      container.scrollTop = y * container.scrollHeight - container.clientHeight / 2;
      zoomCenterRef.current = null;
    });
  }, [zoom]);

  // Page navigation
  const goToPrevPage = () => setPageNumber(prev => Math.max(prev - 1, 1));
  const goToNextPage = () => setPageNumber(prev => Math.min(prev + 1, pageImages.length));

  // Current page data
  const currentImage = pageImages[pageNumber - 1];

  // Center scroll position when page changes or images load
  useEffect(() => {
    if (!containerRef.current || !currentImage) return;

    const timer = setTimeout(() => {
      const container = containerRef.current;
      if (!container) return;

      const scrollLeft = Math.max(0, (container.scrollWidth - container.clientWidth) / 2);
      const scrollTop = Math.max(0, (container.scrollHeight - container.clientHeight) / 2);
      container.scrollLeft = scrollLeft;
      container.scrollTop = scrollTop;
    }, 100);

    return () => clearTimeout(timer);
  }, [pageNumber, currentImage, pageImages.length]);

  // Calculate display dimensions to fit container at zoom=1
  const displayDimensions = currentImage ? (() => {
    const imgWidth = currentImage.width;
    const imgHeight = currentImage.height;

    const scaleX = containerSize.width / imgWidth;
    const scaleY = containerSize.height / imgHeight;
    const fitScale = Math.min(scaleX, scaleY, 1);

    return {
      width: imgWidth * fitScale,
      height: imgHeight * fitScale,
    };
  })() : { width: 800, height: 600 };

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

        {/* Loading state */}
        {isLoadingAgentPage && (
          <div className="flex-1 flex items-center justify-center h-full bg-slate-100">
            <Loader2 size={48} className="text-cyan-500 animate-spin" />
          </div>
        )}

        {/* Pinch-to-zoom enabled viewer */}
        {agentPageImage && (
          <TransformWrapper
            initialScale={1}
            minScale={0.5}
            maxScale={5}
            centerOnInit={true}
            doubleClick={{ mode: "reset" }}
            panning={{ velocityDisabled: true }}
          >
            {/* Zoom controls - must be inside TransformWrapper to use useControls */}
            <ZoomControls />

            <TransformComponent
              wrapperStyle={{
                width: '100%',
                height: '100%',
                backgroundColor: '#f1f5f9', // bg-slate-100
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
                className="relative select-none rounded-sm"
                style={{
                  width: agentDisplayDimensions.width,
                  height: agentDisplayDimensions.height,
                  boxShadow: '0 4px 20px rgba(0, 0, 0, 0.15), 0 8px 40px rgba(0, 0, 0, 0.1)',
                }}
              >
                <img
                  src={agentPageImage.dataUrl}
                  alt={currentAgentPage.pageName}
                  className="max-w-none w-full h-full"
                  draggable={false}
                />

                {/* Pointer overlays - scale with zoom since they're inside TransformComponent */}
                {currentAgentPage.pointers.map((pointer) => (
                  <div
                    key={pointer.pointerId}
                    className="absolute border-2 border-cyan-500 bg-cyan-500/20 hover:bg-cyan-500/30 transition-colors cursor-pointer group"
                    style={{
                      left: `${pointer.bboxX * 100}%`,
                      top: `${pointer.bboxY * 100}%`,
                      width: `${pointer.bboxWidth * 100}%`,
                      height: `${pointer.bboxHeight * 100}%`,
                    }}
                  >
                    <div className="absolute -top-8 left-1/2 -translate-x-1/2 bg-slate-800/90 backdrop-blur-sm px-2 py-1 rounded text-xs text-white whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                      {pointer.title}
                    </div>
                  </div>
                ))}
              </div>
            </TransformComponent>
          </TransformWrapper>
        )}
      </div>
    );
  }

  // =====================================
  // SINGLE-PAGE MODE (manual page selection)
  // =====================================

  // Empty state - no page selected
  if (!pageId) {
    return (
      <div className="flex-1 flex items-center justify-center h-full">
        <div className="text-center text-slate-500">
          <FileText size={48} className="mx-auto mb-3 text-slate-600" />
          <p className="text-sm">Select a page to view</p>
        </div>
      </div>
    );
  }

  // Loading state
  if (isLoadingPage) {
    return (
      <div className="flex-1 flex items-center justify-center h-full">
        <div className="text-center text-slate-400">
          <Loader2 size={48} className="mx-auto mb-4 text-cyan-400 animate-spin" />
          <p className="text-sm font-medium">Loading page...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (loadError) {
    return (
      <div className="flex-1 flex items-center justify-center h-full">
        <div className="text-center text-slate-400 max-w-md px-4">
          <AlertCircle size={48} className="mx-auto mb-4 text-amber-400" />
          <p className="text-sm font-medium text-amber-300 mb-2">Unable to load page</p>
          <p className="text-xs text-slate-500">{loadError}</p>
        </div>
      </div>
    );
  }

  // Converting state
  if (isConverting) {
    return (
      <div className="flex-1 flex items-center justify-center h-full">
        <div className="text-center text-slate-400">
          <Loader2 size={48} className="mx-auto mb-4 text-cyan-400 animate-spin" />
          <p className="text-sm font-medium mb-2">Rendering page...</p>
          <p className="text-xs text-slate-500">
            Page {conversionProgress.current} of {conversionProgress.total}
          </p>
          <div className="w-48 h-1.5 bg-slate-700 rounded-full mt-3 mx-auto overflow-hidden">
            <div
              className="h-full bg-cyan-500 transition-all duration-300"
              style={{ width: `${(conversionProgress.current / conversionProgress.total) * 100}%` }}
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col h-full relative overflow-hidden">
      {/* Page name header */}
      {pageName && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 glass-light px-4 py-2 rounded-xl animate-fade-in">
          <span className="text-sm font-medium text-slate-700">{pageName}</span>
        </div>
      )}

      {/* Toolbar */}
      <div className="absolute top-4 right-4 z-20 flex flex-col gap-1 glass rounded-xl p-1.5 toolbar-float animate-fade-in">
        <button
          onClick={handleZoomIn}
          disabled={zoom >= 4}
          className="p-2.5 hover:bg-white/10 rounded-lg text-slate-300 hover:text-white transition-all disabled:opacity-30 disabled:cursor-not-allowed"
          title="Zoom In"
        >
          <ZoomIn size={18} />
        </button>
        <button
          onClick={handleZoomOut}
          disabled={zoom <= 0.5}
          className="p-2.5 hover:bg-white/10 rounded-lg text-slate-300 hover:text-white transition-all disabled:opacity-30 disabled:cursor-not-allowed"
          title="Zoom Out"
        >
          <ZoomOut size={18} />
        </button>
        <button
          onClick={handleZoomReset}
          className="p-2.5 hover:bg-white/10 rounded-lg text-slate-300 hover:text-white transition-all"
          title="Reset Zoom"
        >
          <Maximize size={18} />
        </button>
        <div className="text-[10px] text-slate-400 text-center py-1 border-t border-white/10 mt-1">
          {Math.round(zoom * 100)}%
        </div>
      </div>

      {/* Page Navigation */}
      {pageImages.length > 1 && (
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 glass rounded-xl px-3 py-2 animate-fade-in">
          <button
            onClick={goToPrevPage}
            disabled={pageNumber <= 1}
            className="p-1.5 hover:bg-white/10 rounded-lg text-slate-300 hover:text-white transition-all disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronLeft size={18} />
          </button>
          <span className="text-sm text-slate-300 min-w-[80px] text-center">
            {pageNumber} / {pageImages.length}
          </span>
          <button
            onClick={goToNextPage}
            disabled={pageNumber >= pageImages.length}
            className="p-1.5 hover:bg-white/10 rounded-lg text-slate-300 hover:text-white transition-all disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronRight size={18} />
          </button>
        </div>
      )}

      {/* Canvas Area */}
      <div
        ref={containerRef}
        className="flex-1 overflow-auto bg-slate-100"
        style={{ position: 'relative' }}
      >
        {currentImage && (() => {
          const contentWidth = displayDimensions.width * zoom;
          const contentHeight = displayDimensions.height * zoom;

          return (
            <div
              style={{
                minWidth: '100%',
                minHeight: '100%',
                width: contentWidth + 64,
                height: contentHeight + 64,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <div
                ref={imageRef}
                className="relative select-none rounded-sm"
                style={{
                  width: contentWidth,
                  height: contentHeight,
                  boxShadow: '0 4px 20px rgba(0, 0, 0, 0.15), 0 8px 40px rgba(0, 0, 0, 0.1)',
                }}
              >
                {/* The actual page image */}
                <img
                  src={currentImage.dataUrl}
                  alt={`Page ${pageNumber}`}
                  className="max-w-none w-full h-full"
                  draggable={false}
                />

                {/* Pointer overlays (only show selected pointers) */}
                {pointers
                  .filter(p => selectedPointerIds.includes(p.id))
                  .map(p => (
                  <div
                    key={p.id}
                    onClick={() => onPointerClick?.(p)}
                    onMouseEnter={() => setHoveredPointerId(p.id)}
                    onMouseLeave={() => setHoveredPointerId(null)}
                    className={`absolute pointer-box cursor-pointer group animate-scale-in ${
                      hoveredPointerId === p.id ? 'selected' : ''
                    }`}
                    style={{
                      left: `${p.bboxX * 100}%`,
                      top: `${p.bboxY * 100}%`,
                      width: `${p.bboxWidth * 100}%`,
                      height: `${p.bboxHeight * 100}%`,
                    }}
                  >
                    {/* Tooltip on hover */}
                    <div className={`absolute -top-10 left-1/2 -translate-x-1/2 glass px-3 py-1.5 rounded-lg whitespace-nowrap z-10 pointer-events-none transition-opacity duration-200 ${
                      hoveredPointerId === p.id ? 'opacity-100' : 'opacity-0'
                    }`}>
                      <span className="text-xs text-white font-medium">{p.title}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })()}
      </div>
    </div>
  );
};
