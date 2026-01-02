import { useEffect, useState } from 'react';
import { ArrowLeft, Star, FileText } from 'lucide-react';
import { api, DisciplineResponse } from '../../../lib/api';
import type { PageInHierarchy } from '../../../types';

interface DisciplineDetailProps {
  disciplineId: string;
  pages: PageInHierarchy[];
  onBack: () => void;
  onPageClick: (pageId: string) => void;
  onProcess?: () => void;
}

function getPageIcon(page: PageInHierarchy): string {
  if (page.pointerCount === 0) return '\u25CB'; // ○
  if (!page.processedPass2) return '\u25D0'; // ◐
  return '\u25CF'; // ●
}

export function DisciplineDetail({
  disciplineId,
  pages,
  onBack,
  onPageClick,
  onProcess,
}: DisciplineDetailProps) {
  const [discipline, setDiscipline] = useState<DisciplineResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadDiscipline() {
      setLoading(true);
      setError(null);
      try {
        const data = await api.disciplines.get(disciplineId);
        setDiscipline(data);
      } catch (err) {
        console.error('Failed to load discipline:', err);
        setError('Failed to load discipline details');
      } finally {
        setLoading(false);
      }
    }
    loadDiscipline();
  }, [disciplineId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500">
        <div className="animate-pulse">Loading discipline...</div>
      </div>
    );
  }

  if (error || !discipline) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-red-400 gap-2">
        <p>{error || 'Discipline not found'}</p>
        <button
          onClick={onBack}
          className="text-sm text-slate-400 hover:text-slate-300 flex items-center gap-1"
        >
          <ArrowLeft size={14} /> Go back
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-white/5">
        <button
          onClick={onBack}
          className="text-sm text-slate-400 hover:text-slate-300 flex items-center gap-1 mb-2"
        >
          <ArrowLeft size={14} /> Back to Map
        </button>
        <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
          {discipline.displayName}
          {discipline.processed && (
            <Star size={16} className="text-yellow-400 fill-yellow-400" />
          )}
        </h2>
        <p className="text-xs text-slate-500 mt-1">
          {pages.length} page{pages.length !== 1 ? 's' : ''}
        </p>
      </div>

      {/* Summary */}
      {discipline.summary && (
        <div className="p-4 border-b border-white/5">
          <h3 className="text-sm font-medium text-slate-300 mb-2">Summary</h3>
          <p className="text-sm text-slate-400 leading-relaxed">
            {discipline.summary}
          </p>
        </div>
      )}

      {/* Pages List */}
      <div className="flex-1 overflow-y-auto p-4">
        <h3 className="text-sm font-medium text-slate-300 mb-3">Pages</h3>
        <div className="space-y-2">
          {pages.map((page) => (
            <button
              key={page.id}
              onClick={() => onPageClick(page.id)}
              className="w-full text-left p-3 rounded-lg bg-slate-800/50 hover:bg-slate-700/50
                         border border-slate-700/50 hover:border-slate-600/50 transition-colors"
            >
              <div className="flex items-center gap-2">
                <span className="text-slate-400">{getPageIcon(page)}</span>
                <span className="text-slate-200 font-medium">{page.pageName}</span>
                <span className="text-xs text-slate-500 ml-auto">
                  {page.pointerCount} pointer{page.pointerCount !== 1 ? 's' : ''}
                </span>
              </div>
              <div className="flex items-center gap-2 mt-1 text-xs text-slate-500">
                {page.processedPass1 && <span>Pass 1</span>}
                {page.processedPass2 && <span>Pass 2</span>}
                {!page.processedPass1 && !page.processedPass2 && (
                  <span className="text-slate-600">Not processed</span>
                )}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Process Button */}
      {!discipline.processed && onProcess && (
        <div className="p-4 border-t border-white/5">
          <button
            onClick={onProcess}
            className="w-full py-2 px-4 bg-cyan-600 hover:bg-cyan-500 text-white
                       rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
          >
            <FileText size={16} />
            Process Discipline
          </button>
        </div>
      )}
    </div>
  );
}
