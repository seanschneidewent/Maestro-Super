import React, { useState, useRef, useCallback, useEffect } from 'react';
import { ChevronLeft } from 'lucide-react';

interface CollapsiblePanelProps {
  children: React.ReactNode;
  side: 'left' | 'right';
  defaultWidth: number;
  minWidth?: number;
  maxWidth?: number;
  collapsedIcon: React.ReactNode;
  collapsedLabel?: string;
  className?: string;
}

export const CollapsiblePanel: React.FC<CollapsiblePanelProps> = ({
  children,
  side,
  defaultWidth,
  minWidth = 200,
  maxWidth = 500,
  collapsedIcon,
  collapsedLabel,
  className = '',
}) => {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [width, setWidth] = useState(defaultWidth);
  const [isDragging, setIsDragging] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const dragStartRef = useRef<{ x: number; width: number; time: number } | null>(null);
  const wasClickRef = useRef(false);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragStartRef.current = {
      x: e.clientX,
      width: width,
      time: Date.now()
    };
    wasClickRef.current = true;
    setIsDragging(true);
  }, [width]);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!dragStartRef.current) return;

    const deltaX = side === 'left'
      ? e.clientX - dragStartRef.current.x
      : dragStartRef.current.x - e.clientX;

    // If moved more than 5px, it's a drag not a click
    if (Math.abs(deltaX) > 5) {
      wasClickRef.current = false;
    }

    const newWidth = Math.min(maxWidth, Math.max(minWidth, dragStartRef.current.width + deltaX));
    setWidth(newWidth);
  }, [side, minWidth, maxWidth]);

  const handleMouseUp = useCallback(() => {
    if (!dragStartRef.current) return;

    const timeDelta = Date.now() - dragStartRef.current.time;

    // If it was a quick click (< 200ms) and didn't move much, toggle collapse
    if (wasClickRef.current && timeDelta < 200) {
      setIsCollapsed(true);
    }

    dragStartRef.current = null;
    wasClickRef.current = false;
    setIsDragging(false);
  }, []);

  // Touch handlers for iPad support
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    const touch = e.touches[0];
    dragStartRef.current = {
      x: touch.clientX,
      width: width,
      time: Date.now()
    };
    wasClickRef.current = true;
    setIsDragging(true);
  }, [width]);

  const handleTouchMove = useCallback((e: TouchEvent) => {
    if (!dragStartRef.current) return;
    const touch = e.touches[0];
    const deltaX = side === 'left'
      ? touch.clientX - dragStartRef.current.x
      : dragStartRef.current.x - touch.clientX;
    if (Math.abs(deltaX) > 5) wasClickRef.current = false;
    const newWidth = Math.min(maxWidth, Math.max(minWidth, dragStartRef.current.width + deltaX));
    setWidth(newWidth);
  }, [side, minWidth, maxWidth]);

  const handleTouchEnd = useCallback(() => {
    dragStartRef.current = null;
    wasClickRef.current = false;
    setIsDragging(false);
  }, []);

  useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.addEventListener('touchmove', handleTouchMove);
      document.addEventListener('touchend', handleTouchEnd);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.removeEventListener('touchmove', handleTouchMove);
      document.removeEventListener('touchend', handleTouchEnd);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isDragging, handleMouseMove, handleMouseUp, handleTouchMove, handleTouchEnd]);

  const handleExpandClick = () => {
    setIsCollapsed(false);
  };

  const COLLAPSED_TAB_WIDTH = 44; // Width of the collapsed tab in pixels

  // Always render the same structure, just change width
  return (
    <div
      ref={panelRef}
      className={`
        relative flex-shrink-0 h-full
        transition-all duration-300 ease-out
      `}
      style={{
        width: isCollapsed ? COLLAPSED_TAB_WIDTH : width,
      }}
    >
      {/* Panel content - hidden when collapsed */}
      <div
        className={`
          absolute inset-0 overflow-hidden
          transition-all duration-300 ease-out
          ${isCollapsed ? 'opacity-0 pointer-events-none' : 'opacity-100'}
          ${className}
        `}
        style={{
          width: isCollapsed ? 0 : width,
        }}
      >
        {children}
      </div>

      {/* Expanded notch handle - spine with bulge, drag to resize, tap to collapse */}
      {!isCollapsed && (
        <div
          className={`
            absolute inset-y-0 w-[44px] z-40
            ${side === 'left' ? 'right-0 translate-x-1/2' : 'left-0 -translate-x-1/2'}
            flex items-center
            cursor-col-resize
            group
          `}
          onMouseDown={handleMouseDown}
          onTouchStart={handleTouchStart}
        >
          {/* Spine - thin vertical line */}
          <div
            className={`
              absolute inset-y-0 w-[3px]
              bg-slate-700/60
              left-1/2 -translate-x-1/2
              transition-colors duration-200
              group-hover:bg-slate-600/80
              ${isDragging ? 'bg-cyan-500/70' : ''}
            `}
          />

          {/* Bulge with chevron - tap to collapse */}
          <button
            onClick={(e) => { e.stopPropagation(); setIsCollapsed(true); }}
            className={`
              absolute top-1/2 -translate-y-1/2 left-1/2 -translate-x-1/2
              w-[44px] h-[150px]
              rounded-2xl
              bg-slate-800/90 backdrop-blur-sm
              border border-slate-700/50
              flex items-center justify-center
              transition-all duration-200
              hover:bg-slate-700/90
              hover:border-cyan-500/30
              hover:shadow-glow-cyan-sm
              text-slate-400 hover:text-cyan-400
              ${isDragging ? 'border-cyan-500/50 bg-slate-700/90' : ''}
            `}
          >
            <ChevronLeft size={20} className={side === 'right' ? 'rotate-180' : ''} />
          </button>
        </div>
      )}

      {/* Collapsed notch tab - spine with bulge */}
      {isCollapsed && (
        <button
          onClick={handleExpandClick}
          className={`
            absolute inset-y-0 w-[44px] flex items-center
            ${side === 'left' ? 'left-0' : 'right-0'}
            group
          `}
          title={collapsedLabel || 'Expand panel'}
        >
          {/* Spine - thin vertical line */}
          <div
            className={`
              absolute inset-y-0 w-[3px]
              bg-slate-800/80 backdrop-blur-sm
              ${side === 'left' ? 'left-0' : 'right-0'}
              transition-colors duration-200
              group-hover:bg-slate-700/90
            `}
          />

          {/* Bulge - curved protrusion with icon/label */}
          <div
            className={`
              absolute top-1/2 -translate-y-1/2
              ${side === 'left' ? 'left-0' : 'right-0'}
              w-[40px] h-[150px]
              ${side === 'left' ? 'rounded-r-2xl' : 'rounded-l-2xl'}
              bg-slate-800/90 backdrop-blur-sm
              border border-slate-700/50
              ${side === 'left' ? 'border-l-0' : 'border-r-0'}
              flex flex-col items-center justify-center gap-3
              transition-all duration-200
              group-hover:bg-slate-700/90
              group-hover:border-cyan-500/30
              group-hover:shadow-glow-cyan-sm
              text-slate-400 group-hover:text-cyan-400
            `}
          >
            <div className="transition-transform duration-200 group-hover:scale-110">
              {collapsedIcon}
            </div>
            {collapsedLabel && (
              <span
                className="text-xs font-medium transition-colors"
                style={{ writingMode: 'vertical-rl', textOrientation: 'mixed' }}
              >
                {collapsedLabel}
              </span>
            )}
          </div>
        </button>
      )}
    </div>
  );
};
