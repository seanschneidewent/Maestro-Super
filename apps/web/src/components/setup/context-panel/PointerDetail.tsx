import { useEffect, useState } from 'react';
import { ArrowLeft, ExternalLink, FileText, Link2 } from 'lucide-react';
import { api, PointerResponse } from '../../../lib/api';
import { getSignedUrl } from '../../../lib/storage';

interface PointerDetailProps {
  pointerId: string;
  onBack: () => void;
  onReferenceClick: (pageId: string) => void;
}

export function PointerDetail({
  pointerId,
  onBack,
  onReferenceClick,
}: PointerDetailProps) {
  const [pointer, setPointer] = useState<PointerResponse | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadPointer() {
      setLoading(true);
      setError(null);
      setImageUrl(null);
      try {
        const data = await api.pointers.get(pointerId);
        setPointer(data);

        // Get signed URL for image if available
        if (data.pngPath) {
          try {
            const url = await getSignedUrl(data.pngPath);
            setImageUrl(url);
          } catch (imgErr) {
            console.warn('Failed to get image URL:', imgErr);
          }
        }
      } catch (err) {
        console.error('Failed to load pointer:', err);
        setError('Failed to load pointer details');
      } finally {
        setLoading(false);
      }
    }
    loadPointer();
  }, [pointerId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500">
        <div className="animate-pulse">Loading pointer...</div>
      </div>
    );
  }

  if (error || !pointer) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-red-400 gap-2">
        <p>{error || 'Pointer not found'}</p>
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
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-white/5 shrink-0">
        <button
          onClick={onBack}
          className="text-sm text-slate-400 hover:text-slate-300 flex items-center gap-1 mb-2"
        >
          <ArrowLeft size={14} /> Back
        </button>
        <h2 className="text-lg font-semibold text-slate-100">{pointer.title}</h2>
      </div>

      {/* Scrollable Content */}
      <div className="flex-1 overflow-y-auto">
        {/* Thumbnail */}
        {imageUrl && (
          <div className="p-4 border-b border-white/5">
            <div className="rounded-lg overflow-hidden bg-slate-900 border border-slate-700">
              <img
                src={imageUrl}
                alt={pointer.title}
                className="w-full h-auto max-h-48 object-contain"
              />
            </div>
          </div>
        )}

        {/* Description */}
        <div className="p-4 border-b border-white/5">
          <h3 className="text-sm font-medium text-slate-300 mb-2 flex items-center gap-2">
            <FileText size={14} />
            Description
          </h3>
          <p className="text-sm text-slate-400 leading-relaxed whitespace-pre-wrap">
            {pointer.description}
          </p>
        </div>

        {/* Text Spans */}
        {pointer.textSpans && pointer.textSpans.length > 0 && (
          <div className="p-4 border-b border-white/5">
            <h3 className="text-sm font-medium text-slate-300 mb-2">Extracted Text</h3>
            <ul className="space-y-1">
              {pointer.textSpans.map((span, i) => (
                <li key={i} className="text-sm text-slate-400 pl-3 border-l-2 border-slate-700">
                  {span}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* References */}
        {pointer.references && pointer.references.length > 0 && (
          <div className="p-4">
            <h3 className="text-sm font-medium text-slate-300 mb-3 flex items-center gap-2">
              <Link2 size={14} />
              References ({pointer.references.length})
            </h3>
            <div className="space-y-2">
              {pointer.references.map((ref) => (
                <button
                  key={ref.id}
                  onClick={() => onReferenceClick(ref.targetPageId)}
                  className="w-full text-left p-3 rounded-lg bg-slate-800/50 hover:bg-slate-700/50
                             border border-slate-700/50 hover:border-slate-600/50 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <ExternalLink size={14} className="text-cyan-400 shrink-0" />
                    <span className="text-slate-200 font-medium">{ref.targetPageName}</span>
                  </div>
                  <p className="text-xs text-slate-500 mt-1 pl-5">
                    {ref.justification}
                  </p>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
