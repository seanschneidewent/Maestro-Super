import React, { useState, useEffect } from 'react';
import { Maximize2, FileText, Loader2 } from 'lucide-react';
import { getPublicUrl } from '../../lib/storage';
import { PointerResponse } from '../../lib/api';

interface PageContextAnchorProps {
  page: {
    pageId: string;
    pageName: string;
    filePath: string;
    disciplineId: string;
    pointers: PointerResponse[];
  };
  onExpand: () => void;
}

export const PageContextAnchor: React.FC<PageContextAnchorProps> = ({ page, onExpand }) => {
  const [thumbnailUrl, setThumbnailUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Load thumbnail
  useEffect(() => {
    let cancelled = false;

    const loadThumbnail = async () => {
      setIsLoading(true);
      try {
        const url = await getPublicUrl(page.filePath);
        if (!cancelled) {
          setThumbnailUrl(url);
        }
      } catch {
        // Silently fail - show placeholder
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    loadThumbnail();
    return () => { cancelled = true; };
  }, [page.filePath]);

  return (
    <div className="mx-auto max-w-xl w-full">
      <button
        onClick={onExpand}
        className="w-full group relative bg-white border border-slate-200/80 rounded-xl shadow-sm hover:shadow-md hover:border-cyan-300/50 transition-all overflow-hidden"
      >
        {/* Thumbnail preview */}
        <div className="relative h-32 bg-slate-100 overflow-hidden">
          {isLoading ? (
            <div className="absolute inset-0 flex items-center justify-center">
              <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
            </div>
          ) : thumbnailUrl ? (
            <img
              src={thumbnailUrl}
              alt={page.pageName}
              className="w-full h-full object-cover object-top"
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center">
              <FileText className="w-10 h-10 text-slate-300" />
            </div>
          )}

          {/* Expand overlay */}
          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center">
            <div className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-2 bg-white/90 backdrop-blur-sm px-3 py-1.5 rounded-full shadow-lg">
              <Maximize2 size={14} className="text-slate-700" />
              <span className="text-sm font-medium text-slate-700">Expand</span>
            </div>
          </div>

          {/* Context badge */}
          <div className="absolute top-2 left-2 bg-cyan-500/90 backdrop-blur-sm px-2 py-0.5 rounded-full text-xs font-medium text-white shadow">
            Page Context
          </div>
        </div>

        {/* Page info footer */}
        <div className="px-4 py-3 border-t border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2 min-w-0">
            <FileText size={16} className="text-slate-400 flex-shrink-0" />
            <span className="text-sm font-medium text-slate-700 truncate">
              {page.pageName}
            </span>
          </div>
          {page.pointers.length > 0 && (
            <span className="text-xs text-slate-400 flex-shrink-0">
              {page.pointers.length} pointer{page.pointers.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      </button>
    </div>
  );
};
