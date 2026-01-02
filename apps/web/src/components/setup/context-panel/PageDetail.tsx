import { useEffect, useState } from 'react';
import { ArrowLeft, Eye, Crosshair } from 'lucide-react';
import { api, PageResponse, PointerResponse } from '../../../lib/api';

interface PageDetailProps {
  pageId: string;
  disciplineName: string;
  onBack: () => void;
  onPointerClick: (pointerId: string) => void;
  onViewPage: () => void;
}

export function PageDetail({
  pageId,
  disciplineName,
  onBack,
  onPointerClick,
  onViewPage,
}: PageDetailProps) {
  const [page, setPage] = useState<PageResponse | null>(null);
  const [pointers, setPointers] = useState<PointerResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      setError(null);
      try {
        const [pageData, pointersData] = await Promise.all([
          api.pages.get(pageId),
          api.pointers.list(pageId),
        ]);
        setPage(pageData);
        setPointers(pointersData);
      } catch (err) {
        console.error('Failed to load page:', err);
        setError('Failed to load page details');
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [pageId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500">
        <div className="animate-pulse">Loading page...</div>
      </div>
    );
  }

  if (error || !page) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-red-400 gap-2">
        <p>{error || 'Page not found'}</p>
        <button
          onClick={onBack}
          className="text-sm text-slate-400 hover:text-slate-300 flex items-center gap-1"
        >
          <ArrowLeft size={14} /> Go back
        </button>
      </div>
    );
  }

  const summary = page.fullContext || page.initialContext;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-white/5">
        <button
          onClick={onBack}
          className="text-sm text-slate-400 hover:text-slate-300 flex items-center gap-1 mb-2"
        >
          <ArrowLeft size={14} /> Back
        </button>
        <h2 className="text-lg font-semibold text-slate-100">{page.pageName}</h2>
        <p className="text-xs text-slate-500 mt-1">{disciplineName}</p>
        <div className="flex items-center gap-2 mt-2 text-xs">
          {page.processedPass1 && (
            <span className="px-2 py-0.5 bg-slate-700 rounded text-slate-300">Pass 1</span>
          )}
          {page.processedPass2 && (
            <span className="px-2 py-0.5 bg-green-800/50 rounded text-green-300">Pass 2</span>
          )}
        </div>
      </div>

      {/* Summary */}
      {summary && (
        <div className="p-4 border-b border-white/5">
          <h3 className="text-sm font-medium text-slate-300 mb-2">Page Summary</h3>
          <p className="text-sm text-slate-400 leading-relaxed line-clamp-6">
            {summary}
          </p>
        </div>
      )}

      {/* Pointers List */}
      <div className="flex-1 overflow-y-auto p-4">
        <h3 className="text-sm font-medium text-slate-300 mb-3">
          Pointers ({pointers.length})
        </h3>
        {pointers.length === 0 ? (
          <p className="text-sm text-slate-500">No pointers on this page yet.</p>
        ) : (
          <div className="space-y-2">
            {pointers.map((pointer) => (
              <button
                key={pointer.id}
                onClick={() => onPointerClick(pointer.id)}
                className="w-full text-left p-3 rounded-lg bg-slate-800/50 hover:bg-slate-700/50
                           border border-slate-700/50 hover:border-slate-600/50 transition-colors"
              >
                <div className="flex items-start gap-2">
                  <Crosshair size={14} className="text-green-400 mt-0.5 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="text-slate-200 font-medium truncate">{pointer.title}</p>
                    <p className="text-xs text-slate-500 mt-1 line-clamp-2">
                      {pointer.description.slice(0, 100)}
                      {pointer.description.length > 100 ? '...' : ''}
                    </p>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* View Page Button */}
      <div className="p-4 border-t border-white/5">
        <button
          onClick={onViewPage}
          className="w-full py-2 px-4 bg-slate-700 hover:bg-slate-600 text-white
                     rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
        >
          <Eye size={16} />
          View Page in PDF
        </button>
      </div>
    </div>
  );
}
