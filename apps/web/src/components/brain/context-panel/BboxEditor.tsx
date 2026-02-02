import { memo, useState, useRef, useCallback, useEffect } from 'react';
import type { Region } from '../../../lib/api';

/** Handle positions for resize */
type HandlePosition = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w';

interface DragState {
  mode: 'move' | 'resize';
  handle?: HandlePosition;
  startX: number;
  startY: number;
  startBbox: { x0: number; y0: number; x1: number; y1: number };
}

interface BboxEditorProps {
  regions: Region[];
  onRegionsChange: (regions: Region[]) => void;
  selectedId: string | null;
  onSelectId: (id: string | null) => void;
}

/** Color mapping by region type */
const REGION_COLORS: Record<Region['type'], { border: string; bg: string; text: string }> = {
  detail: { border: 'border-cyan-400', bg: 'bg-cyan-400/20', text: 'text-cyan-400' },
  legend: { border: 'border-purple-400', bg: 'bg-purple-400/20', text: 'text-purple-400' },
  notes: { border: 'border-yellow-400', bg: 'bg-yellow-400/20', text: 'text-yellow-400' },
  title_block: { border: 'border-slate-400', bg: 'bg-slate-400/20', text: 'text-slate-400' },
  schedule: { border: 'border-green-400', bg: 'bg-green-400/20', text: 'text-green-400' },
  plan: { border: 'border-blue-400', bg: 'bg-blue-400/20', text: 'text-blue-400' },
  general: { border: 'border-slate-500', bg: 'bg-slate-500/20', text: 'text-slate-500' },
};

/** Handle cursor styles */
const HANDLE_CURSORS: Record<HandlePosition, string> = {
  nw: 'nwse-resize',
  n: 'ns-resize',
  ne: 'nesw-resize',
  e: 'ew-resize',
  se: 'nwse-resize',
  s: 'ns-resize',
  sw: 'nesw-resize',
  w: 'ew-resize',
};

function BboxEditorComponent({ regions, onRegionsChange, selectedId, onSelectId }: BboxEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  /** Convert mouse event to normalized coordinates (0-1) */
  const getNormalizedCoords = useCallback((e: MouseEvent | React.MouseEvent): { x: number; y: number } => {
    if (!containerRef.current) return { x: 0, y: 0 };
    const rect = containerRef.current.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height)),
    };
  }, []);

  /** Start moving a region */
  const handleMoveStart = useCallback((e: React.MouseEvent, region: Region) => {
    e.stopPropagation();
    e.preventDefault();
    onSelectId(region.id);
    const coords = getNormalizedCoords(e);
    setDragState({
      mode: 'move',
      startX: coords.x,
      startY: coords.y,
      startBbox: { ...region.bbox },
    });
  }, [getNormalizedCoords, onSelectId]);

  /** Start resizing a region */
  const handleResizeStart = useCallback((e: React.MouseEvent, region: Region, handle: HandlePosition) => {
    e.stopPropagation();
    e.preventDefault();
    const coords = getNormalizedCoords(e);
    setDragState({
      mode: 'resize',
      handle,
      startX: coords.x,
      startY: coords.y,
      startBbox: { ...region.bbox },
    });
  }, [getNormalizedCoords]);

  /** Handle mouse move during drag */
  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!dragState || !selectedId) return;

    const coords = getNormalizedCoords(e);
    const dx = coords.x - dragState.startX;
    const dy = coords.y - dragState.startY;

    const updatedRegions = regions.map(region => {
      if (region.id !== selectedId) return region;

      let newBbox = { ...dragState.startBbox };

      if (dragState.mode === 'move') {
        const width = newBbox.x1 - newBbox.x0;
        const height = newBbox.y1 - newBbox.y0;
        newBbox.x0 = Math.max(0, Math.min(1 - width, dragState.startBbox.x0 + dx));
        newBbox.y0 = Math.max(0, Math.min(1 - height, dragState.startBbox.y0 + dy));
        newBbox.x1 = newBbox.x0 + width;
        newBbox.y1 = newBbox.y0 + height;
      } else if (dragState.mode === 'resize' && dragState.handle) {
        const handle = dragState.handle;

        // Update coordinates based on handle
        if (handle.includes('w')) {
          newBbox.x0 = Math.max(0, Math.min(newBbox.x1 - 0.01, dragState.startBbox.x0 + dx));
        }
        if (handle.includes('e')) {
          newBbox.x1 = Math.max(newBbox.x0 + 0.01, Math.min(1, dragState.startBbox.x1 + dx));
        }
        if (handle.includes('n')) {
          newBbox.y0 = Math.max(0, Math.min(newBbox.y1 - 0.01, dragState.startBbox.y0 + dy));
        }
        if (handle.includes('s')) {
          newBbox.y1 = Math.max(newBbox.y0 + 0.01, Math.min(1, dragState.startBbox.y1 + dy));
        }
      }

      return { ...region, bbox: newBbox };
    });

    onRegionsChange(updatedRegions);
  }, [dragState, selectedId, regions, getNormalizedCoords, onRegionsChange]);

  /** Handle mouse up - end drag */
  const handleMouseUp = useCallback(() => {
    setDragState(null);
  }, []);

  /** Add/remove document listeners for drag operations */
  useEffect(() => {
    if (dragState) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [dragState, handleMouseMove, handleMouseUp]);

  /** Handle click on container background to deselect */
  const handleBackgroundClick = useCallback((e: React.MouseEvent) => {
    if (e.target === containerRef.current) {
      onSelectId(null);
    }
  }, [onSelectId]);

  /** Render resize handles for selected region */
  const renderHandles = (region: Region) => {
    const handleSize = 8;
    const handles: { pos: HandlePosition; style: React.CSSProperties }[] = [
      { pos: 'nw', style: { left: -handleSize / 2, top: -handleSize / 2 } },
      { pos: 'n', style: { left: '50%', top: -handleSize / 2, transform: 'translateX(-50%)' } },
      { pos: 'ne', style: { right: -handleSize / 2, top: -handleSize / 2 } },
      { pos: 'e', style: { right: -handleSize / 2, top: '50%', transform: 'translateY(-50%)' } },
      { pos: 'se', style: { right: -handleSize / 2, bottom: -handleSize / 2 } },
      { pos: 's', style: { left: '50%', bottom: -handleSize / 2, transform: 'translateX(-50%)' } },
      { pos: 'sw', style: { left: -handleSize / 2, bottom: -handleSize / 2 } },
      { pos: 'w', style: { left: -handleSize / 2, top: '50%', transform: 'translateY(-50%)' } },
    ];

    return handles.map(({ pos, style }) => (
      <div
        key={pos}
        className="absolute bg-white border-2 border-cyan-500 rounded-sm z-20"
        style={{
          width: handleSize,
          height: handleSize,
          cursor: HANDLE_CURSORS[pos],
          ...style,
        }}
        onMouseDown={(e) => handleResizeStart(e, region, pos)}
      />
    ));
  };

  if (!regions || regions.length === 0) {
    return null;
  }

  return (
    <div
      ref={containerRef}
      className="absolute inset-0"
      onClick={handleBackgroundClick}
      style={{ cursor: dragState ? (dragState.mode === 'move' ? 'grabbing' : 'default') : 'default' }}
    >
      {regions.map((region) => {
        const { bbox } = region;
        if (!bbox) return null;

        const colors = REGION_COLORS[region.type] || REGION_COLORS.general;
        const isSelected = selectedId === region.id;
        const isHovered = hoveredId === region.id;

        // Convert normalized coords (0-1) to percentages
        const style: React.CSSProperties = {
          left: `${bbox.x0 * 100}%`,
          top: `${bbox.y0 * 100}%`,
          width: `${(bbox.x1 - bbox.x0) * 100}%`,
          height: `${(bbox.y1 - bbox.y0) * 100}%`,
          cursor: isSelected ? 'grab' : 'pointer',
        };

        return (
          <div
            key={region.id}
            className={`absolute border-2 ${colors.border} ${colors.bg} transition-all duration-150 ${
              isSelected
                ? 'border-opacity-100 bg-opacity-30 border-[3px] shadow-lg'
                : isHovered
                  ? 'border-opacity-100 bg-opacity-20'
                  : 'border-opacity-60 bg-opacity-10'
            }`}
            style={style}
            onMouseDown={(e) => handleMoveStart(e, region)}
            onMouseEnter={() => setHoveredId(region.id)}
            onMouseLeave={() => setHoveredId(null)}
          >
            {/* Label tooltip */}
            {(isHovered || isSelected) && (
              <div
                className={`absolute -top-7 left-0 px-2 py-1 rounded text-xs font-medium whitespace-nowrap z-10 ${colors.bg} ${colors.text} border ${colors.border}`}
                style={{ backgroundColor: 'rgba(15, 23, 42, 0.95)' }}
              >
                <span className="uppercase text-[10px] opacity-70">{region.type}</span>
                {region.label && (
                  <>
                    <span className="mx-1 opacity-50">|</span>
                    <span>{region.label}</span>
                  </>
                )}
                {region.detailNumber && (
                  <>
                    <span className="mx-1 opacity-50">|</span>
                    <span className="font-mono">{region.detailNumber}</span>
                  </>
                )}
              </div>
            )}

            {/* Resize handles for selected region */}
            {isSelected && renderHandles(region)}
          </div>
        );
      })}
    </div>
  );
}

export const BboxEditor = memo(BboxEditorComponent);
