import { memo, useState } from 'react';
import type { SemanticWord } from '../../../lib/api';

// Role-based color scheme for semantic classification
export const ROLE_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  detail_title: { bg: 'rgba(6, 182, 212, 0.15)', border: 'rgb(6, 182, 212)', text: 'text-cyan-400' },
  dimension: { bg: 'rgba(96, 165, 250, 0.15)', border: 'rgb(96, 165, 250)', text: 'text-blue-400' },
  material_spec: { bg: 'rgba(251, 146, 60, 0.15)', border: 'rgb(251, 146, 60)', text: 'text-orange-400' },
  reference: { bg: 'rgba(168, 85, 247, 0.15)', border: 'rgb(168, 85, 247)', text: 'text-purple-400' },
  note_text: { bg: 'rgba(250, 204, 21, 0.15)', border: 'rgb(250, 204, 21)', text: 'text-yellow-400' },
  sheet_number: { bg: 'rgba(34, 197, 94, 0.15)', border: 'rgb(34, 197, 94)', text: 'text-green-400' },
  schedule_title: { bg: 'rgba(248, 113, 113, 0.15)', border: 'rgb(248, 113, 113)', text: 'text-red-400' },
  schedule_text: { bg: 'rgba(248, 113, 113, 0.10)', border: 'rgb(248, 113, 113)', text: 'text-red-300' },
  legend_text: { bg: 'rgba(244, 114, 182, 0.15)', border: 'rgb(244, 114, 182)', text: 'text-pink-400' },
  plan_text: { bg: 'rgba(148, 163, 184, 0.10)', border: 'rgb(148, 163, 184)', text: 'text-slate-400' },
  // Default for unknown roles
  default: { bg: 'rgba(148, 163, 184, 0.10)', border: 'rgb(148, 163, 184)', text: 'text-slate-400' },
};

interface BboxOverlayProps {
  words: SemanticWord[];
  imageWidth: number;  // Original image width in pixels
  imageHeight: number; // Original image height in pixels
  displayWidth: number;  // Display width (scaled)
  displayHeight: number; // Display height (scaled)
  showTooltip?: boolean;
  onWordClick?: (word: SemanticWord) => void;
}

function BboxOverlayComponent({
  words,
  imageWidth,
  imageHeight,
  displayWidth,
  displayHeight,
  showTooltip = true,
  onWordClick,
}: BboxOverlayProps) {
  const [hoveredWordId, setHoveredWordId] = useState<number | null>(null);

  // Calculate scale factors
  const scaleX = displayWidth / imageWidth;
  const scaleY = displayHeight / imageHeight;

  return (
    <svg
      width={displayWidth}
      height={displayHeight}
      className="absolute top-0 left-0 pointer-events-none"
      style={{ overflow: 'visible' }}
    >
      {words.map((word) => {
        const role = word.role || 'default';
        const colors = ROLE_COLORS[role] || ROLE_COLORS.default;

        // Scale bbox coordinates to display size
        const x = word.bbox.x0 * scaleX;
        const y = word.bbox.y0 * scaleY;
        const width = word.bbox.width * scaleX;
        const height = word.bbox.height * scaleY;

        const isHovered = hoveredWordId === word.id;

        return (
          <g key={word.id}>
            {/* Background rect */}
            <rect
              x={x}
              y={y}
              width={width}
              height={height}
              fill={colors.bg}
              stroke={colors.border}
              strokeWidth={isHovered ? 2 : 1}
              opacity={isHovered ? 1 : 0.7}
              className="pointer-events-auto cursor-pointer transition-all duration-150"
              onMouseEnter={() => setHoveredWordId(word.id)}
              onMouseLeave={() => setHoveredWordId(null)}
              onClick={() => onWordClick?.(word)}
            />

            {/* Tooltip on hover */}
            {showTooltip && isHovered && (
              <g>
                {/* Tooltip background */}
                <rect
                  x={x}
                  y={y - 28}
                  width={Math.max(word.text.length * 7 + 16, 60)}
                  height={24}
                  rx={4}
                  fill="rgba(15, 23, 42, 0.95)"
                  stroke="rgba(255, 255, 255, 0.1)"
                />
                {/* Tooltip text */}
                <text
                  x={x + 8}
                  y={y - 12}
                  fill="white"
                  fontSize={11}
                  fontFamily="monospace"
                >
                  {word.text}
                </text>
                {/* Role badge */}
                <text
                  x={x + 8 + word.text.length * 7 + 8}
                  y={y - 12}
                  fill={colors.border}
                  fontSize={9}
                  fontFamily="sans-serif"
                >
                  {role.replace(/_/g, ' ')}
                </text>
              </g>
            )}
          </g>
        );
      })}
    </svg>
  );
}

export const BboxOverlay = memo(BboxOverlayComponent);
