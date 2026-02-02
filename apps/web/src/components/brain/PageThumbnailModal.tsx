import { memo, useState, useEffect, useRef, useCallback } from 'react';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';
import { X, Edit3, Save, RotateCcw, Undo2, Redo2 } from 'lucide-react';
import type { Region } from '../../lib/api';
import { RegionOverlay } from './context-panel/RegionOverlay';
import { BboxEditor } from './context-panel/BboxEditor';

interface PageThumbnailModalProps {
  isOpen: boolean;
  onClose: () => void;
  imageUrl: string;
  pageName: string;
  pageId?: string;
  regions?: Region[];
  onRegionsSave?: (regions: Region[]) => Promise<void>;
}

function PageThumbnailModalComponent({
  isOpen,
  onClose,
  imageUrl,
  pageName,
  pageId,
  regions,
  onRegionsSave,
}: PageThumbnailModalProps) {
  const [imageDimensions, setImageDimensions] = useState({ width: 0, height: 0 });
  const [displayDimensions, setDisplayDimensions] = useState({ width: 800, height: 600 });
  const [isVisible, setIsVisible] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Edit mode state
  const [isEditMode, setIsEditMode] = useState(false);
  const [editedRegions, setEditedRegions] = useState<Region[]>([]);
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  // Undo/redo state
  const [history, setHistory] = useState<Region[][]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);

  // Initialize edited regions when entering edit mode
  useEffect(() => {
    if (isEditMode && regions) {
      setEditedRegions([...regions]);
      setHistory([[...regions]]);
      setHistoryIndex(0);
      setHasChanges(false);
    }
  }, [isEditMode, regions]);

  // Reset edit state when modal closes
  useEffect(() => {
    if (!isOpen) {
      setIsEditMode(false);
      setSelectedRegionId(null);
      setHasChanges(false);
    }
  }, [isOpen]);

  /** Handle regions change from BboxEditor */
  const handleRegionsChange = useCallback((newRegions: Region[]) => {
    setEditedRegions(newRegions);
    setHasChanges(true);

    // Add to history (truncate any redo history)
    setHistory(prev => [...prev.slice(0, historyIndex + 1), newRegions]);
    setHistoryIndex(prev => prev + 1);
  }, [historyIndex]);

  /** Undo last change */
  const handleUndo = useCallback(() => {
    if (historyIndex > 0) {
      setHistoryIndex(prev => prev - 1);
      setEditedRegions(history[historyIndex - 1]);
      setHasChanges(historyIndex - 1 > 0);
    }
  }, [history, historyIndex]);

  /** Redo last undone change */
  const handleRedo = useCallback(() => {
    if (historyIndex < history.length - 1) {
      setHistoryIndex(prev => prev + 1);
      setEditedRegions(history[historyIndex + 1]);
      setHasChanges(true);
    }
  }, [history, historyIndex]);

  /** Save changes */
  const handleSave = useCallback(async () => {
    if (!onRegionsSave || !hasChanges) return;

    setIsSaving(true);
    try {
      await onRegionsSave(editedRegions);
      setHasChanges(false);
      setIsEditMode(false);
    } catch (err) {
      console.error('Failed to save regions:', err);
    } finally {
      setIsSaving(false);
    }
  }, [onRegionsSave, editedRegions, hasChanges]);

  /** Cancel changes and exit edit mode */
  const handleCancel = useCallback(() => {
    setEditedRegions(regions || []);
    setSelectedRegionId(null);
    setIsEditMode(false);
    setHasChanges(false);
  }, [regions]);

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

  // Handle keyboard shortcuts
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      // Escape - deselect or exit edit mode or close modal
      if (e.key === 'Escape') {
        if (selectedRegionId) {
          setSelectedRegionId(null);
        } else if (isEditMode) {
          handleCancel();
        } else {
          onClose();
        }
        return;
      }

      // Edit mode shortcuts
      if (isEditMode) {
        // Undo: Ctrl/Cmd + Z
        if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
          e.preventDefault();
          handleUndo();
          return;
        }
        // Redo: Ctrl/Cmd + Shift + Z or Ctrl/Cmd + Y
        if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
          e.preventDefault();
          handleRedo();
          return;
        }
        // Arrow keys for fine adjustment
        if (selectedRegionId && ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
          e.preventDefault();
          const delta = e.shiftKey ? 0.01 : 0.002; // Larger step with shift
          setEditedRegions(prev => prev.map(region => {
            if (region.id !== selectedRegionId) return region;
            const newBbox = { ...region.bbox };
            switch (e.key) {
              case 'ArrowUp':
                newBbox.y0 = Math.max(0, newBbox.y0 - delta);
                newBbox.y1 = Math.max(newBbox.y0 + 0.01, newBbox.y1 - delta);
                break;
              case 'ArrowDown':
                newBbox.y1 = Math.min(1, newBbox.y1 + delta);
                newBbox.y0 = Math.min(newBbox.y1 - 0.01, newBbox.y0 + delta);
                break;
              case 'ArrowLeft':
                newBbox.x0 = Math.max(0, newBbox.x0 - delta);
                newBbox.x1 = Math.max(newBbox.x0 + 0.01, newBbox.x1 - delta);
                break;
              case 'ArrowRight':
                newBbox.x1 = Math.min(1, newBbox.x1 + delta);
                newBbox.x0 = Math.min(newBbox.x1 - 0.01, newBbox.x0 + delta);
                break;
            }
            return { ...region, bbox: newBbox };
          }));
          setHasChanges(true);
        }
        // Delete key to remove region
        if ((e.key === 'Delete' || e.key === 'Backspace') && selectedRegionId) {
          e.preventDefault();
          const newRegions = editedRegions.filter(r => r.id !== selectedRegionId);
          handleRegionsChange(newRegions);
          setSelectedRegionId(null);
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose, isEditMode, selectedRegionId, handleUndo, handleRedo, handleCancel, editedRegions, handleRegionsChange]);

  if (!isOpen) return null;

  const canUndo = historyIndex > 0;
  const canRedo = historyIndex < history.length - 1;
  const canEdit = !!onRegionsSave && !!pageId && regions && regions.length > 0;

  return (
    <div
      ref={containerRef}
      className={`fixed inset-0 z-50 flex items-center justify-center transition-all duration-300 ease-out ${
        isVisible ? 'opacity-100' : 'opacity-0'
      }`}
    >
      {/* Backdrop - tap to close (only in view mode) */}
      <div
        className="absolute inset-0 bg-slate-950/85 backdrop-blur-sm"
        onClick={isEditMode ? undefined : onClose}
      />

      {/* Top toolbar */}
      <div className="fixed top-4 left-1/2 -translate-x-1/2 z-[60] flex items-center gap-2">
        {/* Edit mode controls */}
        {isEditMode ? (
          <>
            {/* Undo/Redo */}
            <div className="flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-800/90 backdrop-blur-md border border-slate-700/50">
              <button
                onClick={handleUndo}
                disabled={!canUndo}
                className="p-2 rounded text-white hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                title="Undo (Ctrl+Z)"
              >
                <Undo2 size={18} />
              </button>
              <button
                onClick={handleRedo}
                disabled={!canRedo}
                className="p-2 rounded text-white hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                title="Redo (Ctrl+Shift+Z)"
              >
                <Redo2 size={18} />
              </button>
            </div>

            {/* Unsaved indicator */}
            {hasChanges && (
              <div className="px-3 py-2 rounded-lg bg-amber-500/20 border border-amber-500/50 text-amber-400 text-sm">
                Unsaved changes
              </div>
            )}

            {/* Save/Cancel */}
            <div className="flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-800/90 backdrop-blur-md border border-slate-700/50">
              <button
                onClick={handleCancel}
                className="px-3 py-2 rounded text-slate-300 hover:bg-slate-700 transition-colors text-sm"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={!hasChanges || isSaving}
                className="flex items-center gap-2 px-3 py-2 rounded bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed text-white transition-colors text-sm"
              >
                <Save size={16} />
                {isSaving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </>
        ) : (
          <>
            {/* View mode - Edit button */}
            {canEdit && (
              <button
                onClick={() => setIsEditMode(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800/90 backdrop-blur-md border border-slate-700/50 text-white hover:bg-slate-700 transition-colors"
              >
                <Edit3 size={18} />
                Edit Regions
              </button>
            )}
          </>
        )}
      </div>

      {/* Close button - fixed in top right */}
      <button
        onClick={isEditMode ? handleCancel : onClose}
        className="fixed top-4 right-4 z-[60] p-3 rounded-full bg-slate-800/90 backdrop-blur-md border border-slate-700/50 text-white hover:bg-slate-700 transition-all duration-200 shadow-lg"
        aria-label={isEditMode ? "Cancel editing" : "Close"}
      >
        <X size={24} />
      </button>

      {/* Keyboard shortcuts hint */}
      {isEditMode && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[60] px-4 py-2 rounded-lg bg-slate-800/90 backdrop-blur-md border border-slate-700/50 text-slate-400 text-xs">
          <span className="mr-4">Arrow keys: nudge</span>
          <span className="mr-4">Shift+Arrow: bigger nudge</span>
          <span className="mr-4">Delete: remove region</span>
          <span>Esc: deselect/cancel</span>
        </div>
      )}

      {/* Image container with pinch-to-zoom */}
      {imageDimensions.width > 0 ? (
        <TransformWrapper
          initialScale={1}
          minScale={0.5}
          maxScale={5}
          centerOnInit={true}
          doubleClick={{ mode: isEditMode ? 'zoomIn' : 'reset' }}
          panning={{ disabled: isEditMode, velocityDisabled: true }}
          pinch={{ disabled: isEditMode }}
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
              } ${isEditMode ? 'ring-2 ring-cyan-500/50' : ''}`}
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
              {isEditMode ? (
                <BboxEditor
                  regions={editedRegions}
                  onRegionsChange={handleRegionsChange}
                  selectedId={selectedRegionId}
                  onSelectId={setSelectedRegionId}
                />
              ) : (
                regions && regions.length > 0 && (
                  <RegionOverlay regions={regions} />
                )
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
