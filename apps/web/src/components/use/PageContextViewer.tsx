import React, { useState, useEffect, useRef } from 'react';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';
import { Loader2 } from 'lucide-react';
import { getPublicUrl } from '../../lib/storage';
import { PointerResponse } from '../../lib/api';

interface PageImage {
  dataUrl: string;
  width: number;
  height: number;
}

interface PageContextViewerProps {
  page: {
    pageId: string;
    pageName: string;
    filePath: string;
    disciplineId: string;
    pointers: PointerResponse[];
  };
}

export const PageContextViewer: React.FC<PageContextViewerProps> = ({ page }) => {
  const [pageImage, setPageImage] = useState<PageImage | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [containerSize, setContainerSize] = useState({ width: 800, height: 600 });
  const containerRef = useRef<HTMLDivElement>(null);

  // Load page image
  useEffect(() => {
    let cancelled = false;

    const loadImage = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const url = await getPublicUrl(page.filePath);
        if (cancelled) return;

        const img = new Image();
        img.crossOrigin = 'anonymous';

        await new Promise<void>((resolve, reject) => {
          img.onload = () => resolve();
          img.onerror = () => reject(new Error('Failed to load image'));
          img.src = url;
        });

        if (cancelled) return;

        // Create canvas and draw image
        const canvas = document.createElement('canvas');
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        const ctx = canvas.getContext('2d');
        if (!ctx) throw new Error('Failed to get canvas context');
        ctx.drawImage(img, 0, 0);

        setPageImage({
          dataUrl: canvas.toDataURL('image/jpeg', 0.85),
          width: img.naturalWidth,
          height: img.naturalHeight,
        });
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load page');
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    loadImage();
    return () => { cancelled = true; };
  }, [page.filePath]);

  // Measure container size
  useEffect(() => {
    const updateSize = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        // Leave space for the query input bar at bottom (about 150px)
        setContainerSize({ width: rect.width - 32, height: rect.height - 32 });
      }
    };

    const timer = setTimeout(updateSize, 50);
    window.addEventListener('resize', updateSize);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', updateSize);
    };
  }, []);

  // Calculate display dimensions to fit container
  const displayDimensions = pageImage ? (() => {
    const imgWidth = pageImage.width;
    const imgHeight = pageImage.height;
    const scaleX = containerSize.width / imgWidth;
    const scaleY = containerSize.height / imgHeight;
    const fitScale = Math.min(scaleX, scaleY, 1);
    return {
      width: imgWidth * fitScale,
      height: imgHeight * fitScale,
    };
  })() : { width: 0, height: 0 };

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center bg-slate-50">
        <div className="text-center">
          <p className="text-slate-500 mb-2">Failed to load page</p>
          <p className="text-sm text-slate-400">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-slate-100">
      {/* Page name header */}
      <div className="flex items-center justify-center py-3 bg-white/80 backdrop-blur-md border-b border-slate-200/50 shadow-sm">
        <span className="text-sm font-medium text-slate-700">{page.pageName}</span>
        {page.pointers.length > 0 && (
          <span className="ml-2 text-xs text-slate-400">
            ({page.pointers.length} pointers)
          </span>
        )}
      </div>

      {/* Full-screen viewer with zoom/pan */}
      <div
        ref={containerRef}
        className="flex-1 flex items-center justify-center overflow-hidden"
      >
        {isLoading ? (
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="w-8 h-8 animate-spin text-cyan-500" />
            <span className="text-sm text-slate-500">Loading page...</span>
          </div>
        ) : pageImage ? (
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
                className="relative shadow-2xl select-none rounded-lg overflow-hidden"
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

                {/* Pointer overlays - visible but subtle */}
                {page.pointers.map((pointer) => (
                  <div
                    key={pointer.id}
                    className="absolute border-2 border-cyan-500/40 bg-cyan-500/5 hover:bg-cyan-500/15 hover:border-cyan-500/70 cursor-pointer group transition-colors"
                    style={{
                      left: `${pointer.bboxX * 100}%`,
                      top: `${pointer.bboxY * 100}%`,
                      width: `${pointer.bboxWidth * 100}%`,
                      height: `${pointer.bboxHeight * 100}%`,
                    }}
                  >
                    <div className="opacity-0 group-hover:opacity-100 absolute -top-8 left-1/2 -translate-x-1/2 bg-slate-800/90 px-2 py-1 rounded text-xs text-white whitespace-nowrap z-10 pointer-events-none max-w-[200px] truncate">
                      {pointer.title}
                    </div>
                  </div>
                ))}
              </div>
            </TransformComponent>
          </TransformWrapper>
        ) : null}
      </div>

      {/* Hint text at bottom */}
      <div className="py-2 text-center bg-white/60 border-t border-slate-200/50">
        <span className="text-xs text-slate-400">
          Ask a question about this page below
        </span>
      </div>
    </div>
  );
};
