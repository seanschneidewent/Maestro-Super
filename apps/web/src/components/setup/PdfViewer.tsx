import React, { useState, useRef, useEffect } from 'react';
import * as pdfjs from 'pdfjs-dist';
import { TransformWrapper, TransformComponent, ReactZoomPanPinchRef } from 'react-zoom-pan-pinch';
import { Square, ChevronLeft, ChevronRight, FileText, Loader2, AlertCircle } from 'lucide-react';
import { ContextPointer } from '../../types';

// Set up PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

// Render scale for PNG conversion (2 = retina quality)
// Higher values cause canvas/dataURL failures on iPad
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
  isDrawingEnabled: boolean;
  setIsDrawingEnabled: (enabled: boolean) => void;
  onPointerCreate?: (data: {
    pageNumber: number;
    bounds: { xNorm: number; yNorm: number; wNorm: number; hNorm: number };
  }) => Promise<ContextPointer | null>;
  isLoadingFile?: boolean;
  fileLoadError?: string | null;
  highlightedBounds?: { x: number; y: number; w: number; h: number } | null;
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
}) => {
  // Page images (PNG data URLs)
  const [pageImages, setPageImages] = useState<PageImage[]>([]);
  const [isConverting, setIsConverting] = useState(false);
  const [conversionProgress, setConversionProgress] = useState({ current: 0, total: 0 });

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
      transformRef.current?.resetTransform();

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

  // Reset transform when page changes
  useEffect(() => {
    transformRef.current?.resetTransform();
  }, [pageNumber]);

  // Page navigation
  const goToPrevPage = () => setPageNumber(prev => Math.max(prev - 1, 1));
  const goToNextPage = () => setPageNumber(prev => Math.min(prev + 1, pageImages.length));

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
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    const coords = getNormalizedCoords(e);
    setStartPos(coords);
    setIsDrawing(true);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDrawing || !isDrawingEnabled) return;
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
  };

  // Current page data
  const currentImage = pageImages[pageNumber - 1];
  const currentPagePointers = pointers.filter(p => p.pageId === fileId);

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
      {/* Toolbar - Single rectangle toggle button */}
      <div className="absolute top-4 right-4 z-20 glass rounded-xl p-1.5 toolbar-float animate-fade-in">
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

      {/* Canvas Area - pinch-to-zoom enabled */}
      <div
        ref={containerRef}
        className="flex-1 canvas-grid"
        style={{ position: 'relative' }}
      >
        {currentImage && (
          <TransformWrapper
            ref={transformRef}
            initialScale={1}
            minScale={0.5}
            maxScale={5}
            centerOnInit={true}
            doubleClick={{ mode: 'reset' }}
            panning={{ disabled: isDrawingEnabled, velocityDisabled: true }}
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
                }}
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                onPointerCancel={handlePointerUp}
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
                    className={`absolute pointer-box cursor-pointer group animate-scale-in ${selectedPointerId === p.id ? 'selected' : ''} ${p.isGenerating ? 'generating' : ''}`}
                    style={{
                      left: `${p.bboxX * 100}%`,
                      top: `${p.bboxY * 100}%`,
                      width: `${p.bboxWidth * 100}%`,
                      height: `${p.bboxHeight * 100}%`,
                    }}
                  >
                    {p.isGenerating ? (
                      <div className="absolute inset-0 flex items-center justify-center bg-cyan-500/10">
                        <Loader2 className="w-5 h-5 text-cyan-400 animate-spin" />
                      </div>
                    ) : (
                      <div className="opacity-0 group-hover:opacity-100 absolute -top-8 left-1/2 -translate-x-1/2 glass px-3 py-1.5 rounded-lg whitespace-nowrap z-10 pointer-events-none transition-opacity duration-200">
                        <span className="text-xs text-white font-medium">{p.title}</span>
                      </div>
                    )}
                  </div>
                ))}

                {/* Highlighted pointer (from context panel) */}
                {highlightedBounds && (
                  <div
                    className="absolute border-2 border-orange-400 bg-orange-400/20 rounded-sm
                               shadow-[0_0_20px_rgba(249,115,22,0.5)] animate-pulse pointer-events-none z-20"
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
            </TransformComponent>
          </TransformWrapper>
        )}
      </div>
    </div>
  );
};
