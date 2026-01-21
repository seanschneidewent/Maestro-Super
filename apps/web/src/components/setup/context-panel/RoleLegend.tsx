import { memo } from 'react';
import { ROLE_COLORS } from './BboxOverlay';

// Human-readable labels for roles
const ROLE_LABELS: Record<string, string> = {
  detail_title: 'Detail Title',
  dimension: 'Dimension',
  material_spec: 'Material Spec',
  reference: 'Reference',
  note_text: 'Note',
  sheet_number: 'Sheet Number',
  schedule_title: 'Schedule Title',
  schedule_text: 'Schedule Text',
  legend_text: 'Legend Text',
  plan_text: 'Plan Text',
};

interface RoleLegendProps {
  /** Only show roles that appear in the data */
  visibleRoles?: string[];
  /** Compact mode for smaller spaces */
  compact?: boolean;
}

function RoleLegendComponent({ visibleRoles, compact = false }: RoleLegendProps) {
  // Filter to only visible roles, or show all if not specified
  const rolesToShow = visibleRoles
    ? visibleRoles.filter((role) => role !== 'default' && ROLE_LABELS[role])
    : Object.keys(ROLE_LABELS);

  if (rolesToShow.length === 0) return null;

  return (
    <div className={`flex flex-wrap gap-2 ${compact ? 'gap-1.5' : 'gap-2'}`}>
      {rolesToShow.map((role) => {
        const colors = ROLE_COLORS[role] || ROLE_COLORS.default;
        const label = ROLE_LABELS[role] || role;

        return (
          <div
            key={role}
            className={`flex items-center gap-1.5 ${compact ? 'text-[10px]' : 'text-xs'}`}
          >
            <div
              className={`${compact ? 'w-2.5 h-2.5' : 'w-3 h-3'} rounded-sm`}
              style={{
                backgroundColor: colors.bg,
                border: `1.5px solid ${colors.border}`,
              }}
            />
            <span className="text-slate-400">{label}</span>
          </div>
        );
      })}
    </div>
  );
}

export const RoleLegend = memo(RoleLegendComponent);
