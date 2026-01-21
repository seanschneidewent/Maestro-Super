import { memo, useState, useEffect, useRef } from 'react';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';
import { X, ZoomIn, ZoomOut, RotateCcw } from 'lucide-react';
import { BboxOverlay } from './context-panel/BboxOverlay';
import { RoleLegend } from './context-panel/RoleLegend';
import type { SemanticWord } from '../../lib/api';

interface PageThumbnailModalProps {
  isOpen: boolean;
  onClose: () => void;
  imageUrl: string;
  pageName: string;
  words?: SemanticWord[];
  imageWidth?: number;
  imageHeight?: number;
}

function PageThumbnailModalComponent({
  isOpen,
  onClose,
  imageUrl,
  pageName,
  words = [],
  imageWidth = 2550,  // Default 8.5x11 at 300 DPI
  imageHeight = 3300,
}: PageThumbnailModalProps) {
  const [imageDimensions, setImageDimensions] = useState({ width: 0, height: 0 });
  const [displayDimensions, setDisplayDimensions] = useState({ width: 800, height: 600 });
  const containerRef = useRef<HTMLDivElement>(null);

  // Get unique roles for legend
  const visibleRoles = [...new Set(words.map((w) => w.role).filter(Boolean))] as string[];

  // Load image and measure dimensions
  useEffect(() => {
    if (!isOpen || !imageUrl) return;

    const img = new Image();
    img.onload = () => {
      setImageDimensions({ width: img.naturalWidth, height: img.naturalHeight });
    };
    img.src = imageUrl;
  }, [isOpen, imageUrl]);

  // Calculate display dimensions based on container
  useEffect(() => {
    if (!isOpen || !containerRef.current || imageDimensions.width === 0) return;

    const updateDisplaySize = () => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const padding = 48;
      const availWidth = rect.width - padding * 2;
      const availHeight = rect.height - padding * 2 - 80; // Account for header

      const scaleX = availWidth / imageDimensions.width;
      const scaleY = availHeight / imageDimensions.height;
      const scale = Math.min(scaleX, scaleY, 1);

      setDisplayDimensions({
        width: imageDimensions.width * scale,
        height: imageDimensions.height * scale,
      });
    };

    updateDisplaySize();
    window.addEventListener('resize', updateDisplaySize);
    return () => window.removeEventListener('resize', updateDisplaySize);
  }, [isOpen, imageDimensions]);

  // Handle escape key
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-950/90 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div
        ref={containerRef}
        className="relative w-full h-full max-w-[95vw] max-h-[95vh] m-4 flex flex-col"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 bg-slate-800/90 backdrop-blur rounded-t-lg border-b border-white/5">
          <div className="flex-1">
            <h3 className="text-sm font-medium text-slate-200">{pageName}</h3>
            {visibleRoles.length > 0 && (
              <div className="mt-2">
                <RoleLegend visibleRoles={visibleRoles} compact />
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-white/10 text-slate-400 hover:text-white transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Image viewer */}
        <div className="flex-1 bg-slate-900/90 backdrop-blur rounded-b-lg overflow-hidden">
          {imageDimensions.width > 0 ? (
            <TransformWrapper
              initialScale={1}
              minScale={0.5}
              maxScale={5}
              centerOnInit={true}
              doubleClick={{ mode: 'reset' }}
              panning={{ velocityDisabled: true }}
            >
              {({ zoomIn, zoomOut, resetTransform }) => (
                <>
                  {/* Zoom controls */}
                  <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 flex items-center gap-2 bg-slate-800/90 backdrop-blur px-3 py-2 rounded-lg border border-white/10">
                    <button
                      onClick={() => zoomOut()}
                      className="p-1.5 rounded hover:bg-white/10 text-slate-400 hover:text-white transition-colors"
                      title="Zoom out"
                    >
                      <ZoomOut size={18} />
                    </button>
                    <button
                      onClick={() => resetTransform()}
                      className="p-1.5 rounded hover:bg-white/10 text-slate-400 hover:text-white transition-colors"
                      title="Reset zoom"
                    >
                      <RotateCcw size={18} />
                    </button>
                    <button
                      onClick={() => zoomIn()}
                      className="p-1.5 rounded hover:bg-white/10 text-slate-400 hover:text-white transition-colors"
                      title="Zoom in"
                    >
                      <ZoomIn size={18} />
                    </button>
                  </div>

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
                      className="relative shadow-2xl"
                      style={{
                        width: displayDimensions.width,
                        height: displayDimensions.height,
                      }}
                    >
                      <img
                        src={imageUrl}
                        alt={pageName}
                        className="w-full h-full"
                        draggable={false}
                      />
                      {words.length > 0 && (
                        <BboxOverlay
                          words={words}
                          imageWidth={imageWidth || imageDimensions.width}
                          imageHeight={imageHeight || imageDimensions.height}
                          displayWidth={displayDimensions.width}
                          displayHeight={displayDimensions.height}
                          showTooltip={true}
                        />
                      )}
                    </div>
                  </TransformComponent>
                </>
              )}
            </TransformWrapper>
          ) : (
            <div className="flex items-center justify-center h-full">
              <div className="animate-pulse text-slate-500">Loading image...</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export const PageThumbnailModal = memo(PageThumbnailModalComponent);
