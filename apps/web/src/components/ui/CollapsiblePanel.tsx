import React, { useState, useRef, useCallback, useEffect } from 'react';

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

  useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isDragging, handleMouseMove, handleMouseUp]);

  const handleExpandClick = () => {
    setIsCollapsed(false);
  };

  const COLLAPSED_TAB_WIDTH = 36; // Width of the collapsed tab in pixels

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

      {/* Resize handle - shown when expanded */}
      {!isCollapsed && (
        <div
          className={`
            absolute top-0 ${side === 'left' ? 'right-0 translate-x-1/2' : 'left-0 -translate-x-1/2'}
            h-full w-4 z-40
            cursor-col-resize
            flex items-center justify-center
            group
          `}
          onMouseDown={handleMouseDown}
        >
          <div
            className={`
              h-16 w-1.5 rounded-full
              bg-slate-600/50
              group-hover:bg-cyan-500/70 group-hover:h-24
              transition-all duration-200
              ${isDragging ? 'bg-cyan-400 h-32' : ''}
            `}
          />
        </div>
      )}

      {/* Collapsed tab - shown when collapsed */}
      {isCollapsed && (
        <button
          onClick={handleExpandClick}
          className={`
            absolute top-1/2 -translate-y-1/2
            ${side === 'left' ? 'left-0' : 'right-0'}
            flex items-center gap-2 px-2 py-4
            bg-slate-800/90 backdrop-blur-sm
            border border-slate-700/50
            ${side === 'left' ? 'rounded-r-lg border-l-0' : 'rounded-l-lg border-r-0'}
            hover:bg-slate-700/90 hover:border-cyan-500/30
            transition-all duration-200
            text-slate-400 hover:text-cyan-400
            shadow-lg
            group
          `}
          title={collapsedLabel || 'Expand panel'}
        >
          <div className="flex flex-col items-center gap-3">
            <div className="transition-transform duration-200 group-hover:scale-110">
              {collapsedIcon}
            </div>
            {collapsedLabel && (
              <span
                className="text-xs font-medium"
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
