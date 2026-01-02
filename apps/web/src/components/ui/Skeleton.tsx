import React from 'react';

interface SkeletonProps {
  className?: string;
}

/**
 * Base skeleton component with pulse animation
 */
export const Skeleton: React.FC<SkeletonProps> = ({ className = '' }) => (
  <div className={`animate-pulse bg-slate-700/50 rounded ${className}`} />
);

/**
 * Skeleton for mind map tree structure (hierarchy view)
 */
export const MindMapSkeleton: React.FC = () => (
  <div className="p-4 space-y-4">
    {/* Project title */}
    <div className="flex items-center gap-3">
      <Skeleton className="w-5 h-5 rounded" />
      <Skeleton className="h-6 w-48" />
    </div>

    {/* Discipline folders */}
    {[1, 2, 3].map((i) => (
      <div key={i} className="ml-6 space-y-2">
        <div className="flex items-center gap-3">
          <Skeleton className="w-4 h-4 rounded" />
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-4 w-16 ml-auto" />
        </div>

        {/* Pages within discipline */}
        {i === 1 && (
          <div className="ml-6 space-y-2">
            {[1, 2, 3, 4].map((j) => (
              <div key={j} className="flex items-center gap-3">
                <Skeleton className="w-3 h-3 rounded" />
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-3 w-12 ml-auto" />
              </div>
            ))}
          </div>
        )}
      </div>
    ))}
  </div>
);

/**
 * Skeleton for pointer/detail cards
 */
export const PointerCardSkeleton: React.FC = () => (
  <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700/50 space-y-3">
    <div className="flex items-start gap-3">
      <Skeleton className="w-10 h-10 rounded" />
      <div className="flex-1 space-y-2">
        <Skeleton className="h-5 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
      </div>
    </div>
    <Skeleton className="h-16 w-full" />
    <div className="flex gap-2">
      <Skeleton className="h-6 w-16 rounded-full" />
      <Skeleton className="h-6 w-20 rounded-full" />
    </div>
  </div>
);

/**
 * Skeleton for page detail panel
 */
export const PageDetailSkeleton: React.FC = () => (
  <div className="p-4 space-y-4">
    {/* Header */}
    <div className="flex items-center justify-between">
      <Skeleton className="h-6 w-32" />
      <Skeleton className="h-8 w-8 rounded" />
    </div>

    {/* Context section */}
    <div className="space-y-2">
      <Skeleton className="h-4 w-24" />
      <Skeleton className="h-20 w-full rounded-lg" />
    </div>

    {/* Pointers list */}
    <div className="space-y-2">
      <Skeleton className="h-4 w-28" />
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <PointerCardSkeleton key={i} />
        ))}
      </div>
    </div>
  </div>
);

/**
 * Skeleton for discipline detail panel
 */
export const DisciplineDetailSkeleton: React.FC = () => (
  <div className="p-4 space-y-4">
    {/* Header */}
    <div className="flex items-center gap-3">
      <Skeleton className="w-10 h-10 rounded-lg" />
      <div className="space-y-1">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-4 w-24" />
      </div>
    </div>

    {/* Summary */}
    <div className="space-y-2">
      <Skeleton className="h-4 w-20" />
      <Skeleton className="h-24 w-full rounded-lg" />
    </div>

    {/* Pages list */}
    <div className="space-y-2">
      <Skeleton className="h-4 w-16" />
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="flex items-center gap-3 p-2">
          <Skeleton className="w-4 h-4 rounded" />
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-3 w-16 ml-auto" />
        </div>
      ))}
    </div>
  </div>
);

/**
 * Skeleton for plans panel list
 */
export const PlansPanelSkeleton: React.FC = () => (
  <div className="p-3 space-y-2">
    {[1, 2, 3, 4, 5].map((i) => (
      <div key={i} className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/30">
        <Skeleton className="w-5 h-5 rounded" />
        <div className="flex-1 space-y-1">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-3 w-20" />
        </div>
        <Skeleton className="h-5 w-8" />
      </div>
    ))}
  </div>
);

/**
 * Inline skeleton for text placeholders
 */
export const TextSkeleton: React.FC<{ width?: string }> = ({ width = 'w-32' }) => (
  <Skeleton className={`h-4 ${width} inline-block`} />
);
