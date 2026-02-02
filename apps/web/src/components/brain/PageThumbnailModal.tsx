import { memo, useState, useEffect, useRef } from 'react';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';
import { X } from 'lucide-react';
import type { Region } from '../../lib/api';
import { RegionOverlay } from './context-panel/RegionOverlay';

interface PageThumbnailModalProps {
  isOpen: boolean;
  onClose: () => void;
  imageUrl: string;
  pageName: string;
  regions?: Region[];
}

function PageThumbnailModalComponent({
  isOpen,
  onClose,
  imageUrl,
  pageName,
  regions,
}: PageThumbnailModalProps) {
  const [imageDimensions, setImageDimensions] = useState({ width: 0, height: 0 });
  const [displayDimensions, setDisplayDimensions] = useState({ width: 800, height: 600 });
  const [isVisible, setIsVisible] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Handle mount animation
  useEffect(() => {
    if (isOpen) {
      // Small delay to trigger CSS transition
      requestAnimationFrame(() => setIsVisible(true));
    } else {
      setIsVisible(false);
    }
  }, [isOpen]);

  // Load image and measure dimensions
  useEffect(() => {
    if (!isOpen || !imageUrl) return;

    const img = new Image();
    img.onload = () => {
      setImageDimensions({ width: img.naturalWidth, height: img.naturalHeight });
    };
    img.src = imageUrl;
  }, [isOpen, imageUrl]);

  // Calculate display dimensions based on viewport
  useEffect(() => {
    if (!isOpen || imageDimensions.width === 0) return;

    const updateDisplaySize = () => {
      const padding = 48;
      const availWidth = window.innerWidth - padding * 2;
      const availHeight = window.innerHeight - padding * 2;

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
    <div
      ref={containerRef}
      className={`fixed inset-0 z-50 flex items-center justify-center transition-all duration-300 ease-out ${
        isVisible ? 'opacity-100' : 'opacity-0'
      }`}
    >
      {/* Backdrop - tap to close */}
      <div
        className="absolute inset-0 bg-slate-950/85 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Close button - fixed in top right with safe area insets */}
      <button
        onClick={onClose}
        className="fixed top-12 right-4 z-[60] p-3 rounded-full bg-slate-800/90 backdrop-blur-md border border-slate-700/50 text-white hover:bg-slate-700 transition-all duration-200 shadow-lg"
        aria-label="Close"
      >
        <X size={24} />
      </button>

      {/* Image container with pinch-to-zoom */}
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
              className={`relative rounded-lg overflow-hidden shadow-2xl shadow-black/50 transition-transform duration-300 ease-out ${
                isVisible ? 'scale-100' : 'scale-95'
              }`}
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
              {/* Region bounding boxes overlay */}
              {regions && regions.length > 0 && (
                <RegionOverlay regions={regions} />
              )}
            </div>
          </TransformComponent>
        </TransformWrapper>
      ) : (
        <div className="flex items-center justify-center h-full">
          <div className="animate-pulse text-slate-500">Loading...</div>
        </div>
      )}
    </div>
  );
}

export const PageThumbnailModal = memo(PageThumbnailModalComponent);
