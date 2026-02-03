import type { FC } from 'react';
import type { AgentFinding } from '../../types';

interface FindingBboxOverlayProps {
  findings: AgentFinding[];
  pageId: string;
  interactive?: boolean;
}

interface FindingRect {
  finding: AgentFinding;
  left: number;
  top: number;
  width: number;
  height: number;
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function toFindingRect(finding: AgentFinding): FindingRect | null {
  if (!finding.bbox || finding.bbox.length !== 4) return null;

  const [rawX0, rawY0, rawX1, rawY1] = finding.bbox;
  if (![rawX0, rawY0, rawX1, rawY1].every((value) => Number.isFinite(value))) {
    return null;
  }

  const left = clamp01(Math.min(rawX0, rawX1));
  const top = clamp01(Math.min(rawY0, rawY1));
  const right = clamp01(Math.max(rawX0, rawX1));
  const bottom = clamp01(Math.max(rawY0, rawY1));

  const width = right - left;
  const height = bottom - top;
  if (width <= 0 || height <= 0) return null;

  return { finding, left, top, width, height };
}

function getFindingColorClasses(confidence?: string): string {
  if (confidence === 'verified_via_zoom') {
    return 'border-emerald-500/80 bg-emerald-500/10';
  }
  if (confidence === 'high') {
    return 'border-cyan-500/75 bg-cyan-500/10';
  }
  return 'border-amber-500/70 bg-amber-500/10';
}

export const FindingBboxOverlay: FC<FindingBboxOverlayProps> = ({
  findings,
  pageId,
  interactive = false,
}) => {
  if (!findings || findings.length === 0 || !pageId) return null;

  const findingRects = findings
    .filter((finding) => finding.pageId === pageId)
    .map((finding) => toFindingRect(finding))
    .filter((rect): rect is FindingRect => rect !== null);

  if (findingRects.length === 0) return null;

  return (
    <>
      {findingRects.map((rect, idx) => (
        <div
          key={`${rect.finding.pageId}-${idx}-${rect.left}-${rect.top}`}
          className={`absolute border-2 rounded-sm ${getFindingColorClasses(rect.finding.confidence)} ${
            interactive ? 'group cursor-help pointer-events-auto' : 'pointer-events-none'
          }`}
          style={{
            left: `${rect.left * 100}%`,
            top: `${rect.top * 100}%`,
            width: `${rect.width * 100}%`,
            height: `${rect.height * 100}%`,
          }}
          title={interactive ? rect.finding.content : undefined}
        >
          {interactive && (
            <div className="pointer-events-none absolute left-0 top-0 -translate-y-[calc(100%+4px)] rounded bg-slate-800/90 px-2 py-1 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100 max-w-xs z-20 whitespace-normal">
              {rect.finding.content}
              {rect.finding.confidence ? ` (${rect.finding.confidence.replace(/_/g, ' ')})` : ''}
            </div>
          )}
        </div>
      ))}
    </>
  );
};
