import React, { useState, useRef, useEffect, useCallback } from 'react';
import * as pdfjs from 'pdfjs-dist';
import { ZoomIn, ZoomOut, Maximize, MousePointer2, Square, ChevronLeft, ChevronRight, FileText, Loader2, AlertCircle } from 'lucide-react';
import { ContextPointer } from '../../types';
import { GeminiService } from '../../services/geminiService';

// Set up PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

// Render scale for PNG conversion (2 = retina quality)
const RENDER_SCALE = 2;

interface PageImage {
  dataUrl: string;
  width: number;
  height: number;
}

interface PdfViewerProps {
  file?: File;
  fileId?: string;
  pointers: ContextPointer[];
  setPointers: React.Dispatch<React.SetStateAction<ContextPointer[]>>;
  selectedPointerId: string | null;
  setSelectedPointerId: (id: string | null) => void;
  activeTool: 'select' | 'rect' | 'text';
  setActiveTool: (tool: 'select' | 'rect' | 'text') => void;
  onPointerCreate?: (data: {
    pageNumber: number;
    bounds: { xNorm: number; yNorm: number; wNorm: number; hNorm: number };
  }) => Promise<ContextPointer | null>;
  isLoadingFile?: boolean;
  fileLoadError?: string | null;
}

export const PdfViewer: React.FC<PdfViewerProps> = ({
  file,
  fileId,
  pointers,
  setPointers,
  selectedPointerId,
  setSelectedPointerId,
  activeTool,
  setActiveTool,
  onPointerCreate,
  isLoadingFile,
  fileLoadError,
}) => {
  // Page images (PNG data URLs)
  const [pageImages, setPageImages] = useState<PageImage[]>([]);
  const [isConverting, setIsConverting] = useState(false);
  const [conversionProgress, setConversionProgress] = useState({ current: 0, total: 0 });

  // Viewer state
  const [pageNumber, setPageNumber] = useState(1);
  const [zoom, setZoom] = useState(1);

  // Drawing state
  const [isDrawing, setIsDrawing] = useState(false);
  const [startPos, setStartPos] = useState({ x: 0, y: 0 });
  const [tempRect, setTempRect] = useState<{ x: number, y: number, w: number, h: number } | null>(null);

  // Container size for fit calculation
  const [containerSize, setContainerSize] = useState({ width: 800, height: 600 });

  // Refs
  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLDivElement>(null);

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

          // Create canvas
          const canvas = document.createElement('canvas');
          const context = canvas.getContext('2d')!;
          canvas.width = viewport.width;
          canvas.height = viewport.height;

          // Render page to canvas
          await page.render({
            canvasContext: context,
            viewport: viewport,
          }).promise;

          // Convert to PNG data URL
          const dataUrl = canvas.toDataURL('image/png');

          images.push({
            dataUrl,
            width: viewport.width / RENDER_SCALE,  // Display size (not render size)
            height: viewport.height / RENDER_SCALE,
          });

          setConversionProgress({ current: i, total: numPages });
        }

        setPageImages(images);
      } catch (error) {
        console.error('PDF conversion failed:', error);
      } finally {
        setIsConverting(false);
      }
    };

    convertPdfToImages();
  }, [file]);

  // Store center point for zoom operations
  const zoomCenterRef = useRef<{ x: number; y: number } | null>(null);

  // Capture current viewport center as fraction of content
  const captureCenter = () => {
    if (!containerRef.current) return;
    const container = containerRef.current;
    zoomCenterRef.current = {
      x: (container.scrollLeft + container.clientWidth / 2) / container.scrollWidth,
      y: (container.scrollTop + container.clientHeight / 2) / container.scrollHeight,
    };
  };

  // Zoom handlers
  const handleZoomIn = () => {
    captureCenter();
    setZoom(prev => Math.min(prev + 0.25, 4));
  };
  const handleZoomOut = () => {
    captureCenter();
    setZoom(prev => Math.max(prev - 0.25, 0.5));
  };
  const handleZoomReset = () => {
    zoomCenterRef.current = null; // Reset to default centering
    setZoom(1);
  };

  // Restore center position after zoom changes
  useEffect(() => {
    if (!containerRef.current || !zoomCenterRef.current) return;

    // Use requestAnimationFrame to ensure layout is complete
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

  // Drawing handlers
  const getNormalizedCoords = (e: React.MouseEvent) => {
    if (!imageRef.current) return { x: 0, y: 0 };
    const rect = imageRef.current.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left) / rect.width,
      y: (e.clientY - rect.top) / rect.height
    };
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (activeTool !== 'rect') return;
    const coords = getNormalizedCoords(e);
    setStartPos(coords);
    setIsDrawing(true);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDrawing || activeTool !== 'rect') return;
    const coords = getNormalizedCoords(e);

    setTempRect({
      x: Math.min(startPos.x, coords.x),
      y: Math.min(startPos.y, coords.y),
      w: Math.abs(coords.x - startPos.x),
      h: Math.abs(coords.y - startPos.y)
    });
  };

  const handleMouseUp = async () => {
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
    if (onPointerCreate) {
      const createdPointer = await onPointerCreate({ pageNumber, bounds });
      if (createdPointer) {
        setPointers(prev => [...prev, createdPointer]);
        setSelectedPointerId(createdPointer.id);
      }
      return;
    }

    // Fallback to local-only pointer creation
    const newPointer: ContextPointer = {
      id: crypto.randomUUID(),
      fileId: fileId || '',
      pageNumber: pageNumber,
      bounds,
      title: '',
      description: '',
      status: 'generating'
    };

    setPointers(prev => [...prev, newPointer]);
    setSelectedPointerId(newPointer.id);

    try {
      const analysis = await GeminiService.analyzePointer("dummy_base64", "Construction plan detail");
      setPointers(prev => prev.map(p =>
        p.id === newPointer.id
          ? { ...p, status: 'complete', description: analysis, title: "Detail Analysis" }
          : p
      ));
    } catch (e) {
      setPointers(prev => prev.map(p => p.id === newPointer.id ? { ...p, status: 'error' } : p));
    }
  };

  // Current page data
  const currentImage = pageImages[pageNumber - 1];
  const currentPagePointers = pointers.filter(p => p.fileId === fileId && p.pageNumber === pageNumber);

  // Center scroll position when page changes or images load
  useEffect(() => {
    if (!containerRef.current || !currentImage) return;

    // Use setTimeout to ensure layout is complete after render
    const timer = setTimeout(() => {
      const container = containerRef.current;
      if (!container) return;

      // Scroll to center the content
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

    // Calculate scale to fit within container (with some padding)
    const scaleX = containerSize.width / imgWidth;
    const scaleY = containerSize.height / imgHeight;
    const fitScale = Math.min(scaleX, scaleY, 1); // Don't scale up beyond 1

    return {
      width: imgWidth * fitScale,
      height: imgHeight * fitScale,
    };
  })() : { width: 800, height: 600 };

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

  // Empty state - no file selected or file not yet loaded
  if (!file) {
    return (
      <div className="flex-1 flex items-center justify-center h-full">
        <div className="text-center text-slate-500">
          <FileText size={48} className="mx-auto mb-3 text-slate-600" />
          <p className="text-sm">Select a PDF file to view</p>
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
          <p className="text-sm font-medium mb-2">Converting PDF to images...</p>
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
      {/* Toolbar */}
      <div className="absolute top-4 right-4 z-20 flex flex-col gap-1 glass rounded-xl p-1.5 toolbar-float animate-fade-in">
        <div className="flex flex-col gap-1 border-b border-white/10 pb-2 mb-1">
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
        <div className="flex flex-col gap-1">
          <button
            onClick={() => setActiveTool('select')}
            className={`p-2.5 rounded-lg transition-all ${activeTool === 'select' ? 'bg-cyan-500/20 text-cyan-400 shadow-glow-cyan-sm' : 'text-slate-400 hover:bg-white/10 hover:text-white'}`}
          >
            <MousePointer2 size={18} />
          </button>
          <button
            onClick={() => setActiveTool('rect')}
            className={`p-2.5 rounded-lg transition-all ${activeTool === 'rect' ? 'bg-cyan-500/20 text-cyan-400 shadow-glow-cyan-sm' : 'text-slate-400 hover:bg-white/10 hover:text-white'}`}
          >
            <Square size={18} />
          </button>
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

      {/* Canvas Area - scrollable surface */}
      <div
        ref={containerRef}
        className="flex-1 overflow-auto canvas-grid"
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
                className="relative shadow-2xl select-none"
                style={{
                  cursor: activeTool === 'rect' ? 'crosshair' : 'default',
                  width: contentWidth,
                  height: contentHeight,
                }}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
              >
                {/* The actual page image */}
                <img
                  src={currentImage.dataUrl}
                  alt={`Page ${pageNumber}`}
                  className="max-w-none w-full h-full"
                  draggable={false}
                />

              {/* Annotation overlays */}
              {currentPagePointers.map(p => (
                <div
                  key={p.id}
                  onClick={() => setSelectedPointerId(p.id)}
                  className={`absolute pointer-box cursor-pointer group animate-scale-in ${p.status === 'generating' ? 'generating' : ''} ${selectedPointerId === p.id ? 'selected' : ''}`}
                  style={{
                    left: `${p.bounds.xNorm * 100}%`,
                    top: `${p.bounds.yNorm * 100}%`,
                    width: `${p.bounds.wNorm * 100}%`,
                    height: `${p.bounds.hNorm * 100}%`,
                  }}
                >
                  <div className="opacity-0 group-hover:opacity-100 absolute -top-8 left-1/2 -translate-x-1/2 glass px-3 py-1.5 rounded-lg whitespace-nowrap z-10 pointer-events-none transition-opacity duration-200">
                    <span className="text-xs text-white font-medium">{p.title}</span>
                    {p.status === 'generating' && (
                      <span className="ml-2 inline-block w-1.5 h-1.5 bg-cyan-400 rounded-full animate-pulse"></span>
                    )}
                  </div>
                </div>
              ))}

              {/* Temp drawing rect */}
              {tempRect && (
                <div
                  className="absolute border-2 border-cyan-400 bg-cyan-400/15 rounded-sm shadow-glow-cyan animate-pulse"
                  style={{
                    left: `${tempRect.x * 100}%`,
                    top: `${tempRect.y * 100}%`,
                    width: `${tempRect.w * 100}%`,
                    height: `${tempRect.h * 100}%`,
                  }}
                />
              )}
              </div>
            </div>
          );
        })()}
      </div>
    </div>
  );
};
