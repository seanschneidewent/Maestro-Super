import { memo, useState } from 'react';
import type { Region } from '../../../lib/api';

interface RegionOverlayProps {
  regions: Region[];
  /** Whether to show region labels on hover */
  showLabels?: boolean;
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

function RegionOverlayComponent({ regions, showLabels = true }: RegionOverlayProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  if (!regions || regions.length === 0) {
    return null;
  }

  return (
    <div className="absolute inset-0 pointer-events-none">
      {regions.map((region) => {
        const { bbox } = region;
        if (!bbox) return null;

        const colors = REGION_COLORS[region.type] || REGION_COLORS.general;
        const isHovered = hoveredId === region.id;

        // Convert normalized coords (0-1) to percentages
        const style = {
          left: `${bbox.x0 * 100}%`,
          top: `${bbox.y0 * 100}%`,
          width: `${(bbox.x1 - bbox.x0) * 100}%`,
          height: `${(bbox.y1 - bbox.y0) * 100}%`,
        };

        return (
          <div
            key={region.id}
            className={`absolute border-2 ${colors.border} ${colors.bg} pointer-events-auto cursor-pointer transition-all duration-150 ${
              isHovered ? 'border-opacity-100 bg-opacity-30' : 'border-opacity-60 bg-opacity-10'
            }`}
            style={style}
            onMouseEnter={() => setHoveredId(region.id)}
            onMouseLeave={() => setHoveredId(null)}
          >
            {/* Label tooltip on hover */}
            {showLabels && isHovered && (
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
          </div>
        );
      })}
    </div>
  );
}

export const RegionOverlay = memo(RegionOverlayComponent);
