import React from 'react';
import { FileText } from 'lucide-react';
import type { PageVisit } from '../../types';

interface PagesVisitedBadgesProps {
  pages: PageVisit[];
  onPageClick?: (pageId: string) => void;
}

export const PagesVisitedBadges: React.FC<PagesVisitedBadgesProps> = ({
  pages,
  onPageClick,
}) => {
  if (pages.length === 0) {
    return null;
  }

  // Deduplicate pages by ID (agent may visit same page multiple times)
  const uniquePages = pages.reduce<PageVisit[]>((acc, page) => {
    if (!acc.find(p => p.pageId === page.pageId)) {
      acc.push(page);
    }
    return acc;
  }, []);

  return (
    <div className="flex flex-wrap gap-1.5">
      <span className="text-[10px] text-slate-400 uppercase tracking-wider font-medium self-center mr-1">
        Pages viewed:
      </span>
      {uniquePages.map((page) => (
        <button
          key={page.pageId}
          onClick={() => onPageClick?.(page.pageId)}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-cyan-50 hover:bg-cyan-100 text-cyan-700 rounded-full text-xs font-medium transition-colors border border-cyan-200 hover:border-cyan-300"
        >
          <FileText size={12} className="text-cyan-500" />
          <span className="truncate max-w-[120px]">{page.pageName}</span>
        </button>
      ))}
    </div>
  );
};
