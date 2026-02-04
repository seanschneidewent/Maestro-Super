import React, { useState, useCallback } from 'react';
import { Pin, PinOff, Loader2 } from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type PageState = 'queued' | 'processing' | 'done';

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
  label?: string;
}

export interface WorkspacePage {
  pageId: string;
  pageName: string;
  imageUrl: string;
  state: PageState;
  pinned: boolean;
  bboxes: BoundingBox[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STATE_BADGES: Record<PageState, { emoji: string; label: string; classes: string }> = {
  queued: {
    emoji: '⏳',
    label: 'Queued',
    classes: 'bg-slate-100 text-slate-600 border-slate-200',
  },
  processing: {
    emoji: '🔬',
    label: 'Processing',
    classes: 'bg-amber-100 text-amber-700 border-amber-200',
  },
  done: {
    emoji: '✅',
    label: 'Done',
    classes: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  },
};

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** SVG overlay layer that renders normalised bounding boxes on top of a page image. */
const BboxOverlay: React.FC<{ bboxes: BoundingBox[] }> = ({ bboxes }) => {
  if (bboxes.length === 0) return null;

  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none"
      viewBox="0 0 1 1"
      preserveAspectRatio="none"
    >
      {bboxes.map((box, idx) => {
        const x = clamp01(box.x);
        const y = clamp01(box.y);
        const w = clamp01(box.width);
        const h = clamp01(box.height);

        return (
          <g key={`${box.label ?? ''}-${idx}`}>
            <rect
              x={x}
              y={y}
              width={w}
              height={h}
              fill="rgba(6, 182, 212, 0.10)"
              stroke="rgba(6, 182, 212, 0.70)"
              strokeWidth={0.003}
              rx={0.002}
            />
            {box.label && (
              <text
                x={x}
                y={y - 0.005}
                fill="rgba(6, 182, 212, 0.90)"
                fontSize={0.014}
                fontFamily="ui-sans-serif, system-ui, sans-serif"
                fontWeight="600"
              >
                {box.label}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
};

/** Small badge indicating the processing state of a page. */
const StateBadge: React.FC<{ state: PageState }> = ({ state }) => {
  const badge = STATE_BADGES[state];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide select-none ${badge.classes}`}
    >
      <span>{badge.emoji}</span>
      {badge.label}
    </span>
  );
};

// ---------------------------------------------------------------------------
// WorkspacePageCard
// ---------------------------------------------------------------------------

interface WorkspacePageCardProps {
  page: WorkspacePage;
  onTogglePin?: (pageId: string) => void;
}

/**
 * Individual page card for the Agent Workspace.
 *
 * Displays a page image with optional bbox overlays, a processing state badge,
 * and a pin/unpin toggle. Designed for vertical scroll within `<PageWorkspace>`.
 */
export const WorkspacePageCard: React.FC<WorkspacePageCardProps> = ({
  page,
  onTogglePin,
}) => {
  const [imgLoaded, setImgLoaded] = useState(false);
  const [imgError, setImgError] = useState(false);

  const handleTogglePin = useCallback(() => {
    onTogglePin?.(page.pageId);
  }, [onTogglePin, page.pageId]);

  return (
    <div className="bg-white/90 backdrop-blur-md border border-slate-200/60 rounded-2xl shadow-sm overflow-hidden transition-shadow hover:shadow-md">
      {/* Header row: page name, state badge, pin button */}
      <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-slate-200/40">
        <div className="flex items-center gap-2 min-w-0">
          <h3 className="text-sm font-semibold text-slate-800 truncate">
            {page.pageName}
          </h3>
          <StateBadge state={page.state} />
        </div>

        <button
          onClick={handleTogglePin}
          className={`shrink-0 p-1.5 rounded-lg transition-colors ${
            page.pinned
              ? 'bg-cyan-100 text-cyan-700 hover:bg-cyan-200'
              : 'bg-slate-100 text-slate-400 hover:bg-slate-200 hover:text-slate-600'
          }`}
          title={page.pinned ? 'Unpin page' : 'Pin page'}
          aria-label={page.pinned ? 'Unpin page' : 'Pin page'}
        >
          {page.pinned ? <Pin size={16} /> : <PinOff size={16} />}
        </button>
      </div>

      {/* Image area with bbox overlay */}
      <div className="relative w-full bg-slate-50">
        {/* Loading / error state */}
        {!imgLoaded && !imgError && (
          <div className="flex items-center justify-center w-full aspect-[4/3]">
            <Loader2 size={32} className="text-cyan-500 animate-spin" />
          </div>
        )}

        {imgError && (
          <div className="flex items-center justify-center w-full aspect-[4/3] text-slate-400 text-sm">
            Failed to load image
          </div>
        )}

        <img
          src={page.imageUrl}
          alt={page.pageName}
          onLoad={() => setImgLoaded(true)}
          onError={() => setImgError(true)}
          className={`w-full h-auto select-none ${imgLoaded ? 'block' : 'hidden'}`}
          draggable={false}
        />

        {/* Bbox overlay — only rendered once the image has loaded */}
        {imgLoaded && page.bboxes.length > 0 && (
          <BboxOverlay bboxes={page.bboxes} />
        )}

        {/* Processing shimmer for queued/processing states */}
        {page.state !== 'done' && imgLoaded && (
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-pulse pointer-events-none" />
        )}
      </div>
    </div>
  );
};
