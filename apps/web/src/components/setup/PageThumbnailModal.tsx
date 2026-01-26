import { memo, useState, useEffect, useRef } from 'react';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';
import { X } from 'lucide-react';

interface PageThumbnailModalProps {
  isOpen: boolean;
  onClose: () => void;
  imageUrl: string;
  pageName: string;
}

function PageThumbnailModalComponent({
  isOpen,
  onClose,
  imageUrl,
  pageName,
}: PageThumbnailModalProps) {
  const [imageDimensions, setImageDimensions] = useState({ width: 0, height: 0 });
  const [displayDimensions, setDisplayDimensions] = useState({ width: 800, height: 600 });
  const containerRef = useRef<HTMLDivElement>(null);

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
          <h3 className="text-sm font-medium text-slate-200">{pageName}</h3>
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
                </div>
              </TransformComponent>
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
