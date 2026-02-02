import { memo, useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { ArrowLeft, Eye, Maximize2, Loader2, Check, AlertCircle, FileText } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { api, PageResponse } from '../../../lib/api';
import { getPublicUrl } from '../../../lib/storage';
import { PageThumbnailModal } from '../PageThumbnailModal';
import { RegionOverlay } from './RegionOverlay';

interface PageContextViewProps {
  pageId: string;
  disciplineName: string;
  onBack: () => void;
  onViewPage: () => void;
}

function PageContextViewComponent({
  pageId,
  disciplineName,
  onBack,
  onViewPage,
}: PageContextViewProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageDimensions, setImageDimensions] = useState({ width: 0, height: 0 });
  const [thumbnailDimensions, setThumbnailDimensions] = useState({ width: 0, height: 0 });
  const thumbnailContainerRef = useRef<HTMLDivElement>(null);

  // Fetch page data
  const { data: page, isLoading, error } = useQuery<PageResponse>({
    queryKey: ['page', pageId],
    queryFn: () => api.pages.get(pageId),
    staleTime: 60_000,
  });

  // Get image URL
  const imageUrl = page?.pageImagePath ? getPublicUrl(page.pageImagePath) : page?.filePath ? getPublicUrl(page.filePath) : null;

  // Load image and measure dimensions
  useEffect(() => {
    if (!imageUrl) {
      setImageLoaded(false);
      return;
    }

    setImageLoaded(false);
    const img = new Image();
    img.onload = () => {
      setImageDimensions({ width: img.naturalWidth, height: img.naturalHeight });
      setImageLoaded(true);
    };
    img.onerror = () => {
      setImageLoaded(false);
    };
    img.src = imageUrl;
  }, [imageUrl]);

  // Calculate thumbnail dimensions based on container
  useEffect(() => {
    if (!thumbnailContainerRef.current || imageDimensions.width === 0) return;

    const updateThumbnailSize = () => {
      if (!thumbnailContainerRef.current) return;
      const containerWidth = thumbnailContainerRef.current.offsetWidth;
      const maxHeight = 300;

      const scaleX = containerWidth / imageDimensions.width;
      const scaleY = maxHeight / imageDimensions.height;
      const scale = Math.min(scaleX, scaleY, 1);

      setThumbnailDimensions({
        width: imageDimensions.width * scale,
        height: imageDimensions.height * scale,
      });
    };

    updateThumbnailSize();
    window.addEventListener('resize', updateThumbnailSize);
    return () => window.removeEventListener('resize', updateThumbnailSize);
  }, [imageDimensions]);

  // Processing status badge
  const getStatusBadge = () => {
    const status = page?.processingStatus;
    switch (status) {
      case 'completed':
        return (
          <span className="flex items-center gap-1 px-2 py-0.5 bg-green-800/50 rounded text-green-300 text-xs">
            <Check size={12} /> Processed
          </span>
        );
      case 'processing':
        return (
          <span className="flex items-center gap-1 px-2 py-0.5 bg-cyan-800/50 rounded text-cyan-300 text-xs">
            <Loader2 size={12} className="animate-spin" /> Processing
          </span>
        );
      case 'failed':
        return (
          <span className="flex items-center gap-1 px-2 py-0.5 bg-red-800/50 rounded text-red-300 text-xs">
            <AlertCircle size={12} /> Failed
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 bg-slate-700 rounded text-slate-300 text-xs">
            Pending
          </span>
        );
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500">
        <div className="animate-pulse">Loading page...</div>
      </div>
    );
  }

  if (error || !page) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-red-400 gap-2">
        <p>{error ? 'Failed to load page details' : 'Page not found'}</p>
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
      {/* Sticky header */}
      <div className="sticky top-0 z-10 p-4 border-b border-white/5 bg-slate-900/95 backdrop-blur-sm">
        <button
          onClick={onBack}
          className="text-sm text-slate-400 hover:text-slate-300 flex items-center gap-1 mb-2"
        >
          <ArrowLeft size={14} /> Back
        </button>
        <h2 className="text-lg font-semibold text-slate-100">{page.pageName}</h2>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto dark-scroll">
        {/* Page metadata */}
        <div className="px-4 pt-3 pb-4 border-b border-white/5">
          <p className="text-xs text-slate-500">{disciplineName}</p>
          <div className="flex items-center gap-2 mt-2 text-xs">
            {getStatusBadge()}
          </div>
        </div>

        {/* Thumbnail */}
        <div className="p-4 border-b border-white/5">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium text-slate-300">Sheet Preview</h3>
          {imageLoaded && (
            <button
              onClick={() => setModalOpen(true)}
              className="flex items-center gap-1 text-xs text-slate-400 hover:text-cyan-400 transition-colors"
            >
              <Maximize2 size={12} /> Expand
            </button>
          )}
        </div>

        <div
          ref={thumbnailContainerRef}
          className="relative rounded-lg overflow-hidden bg-slate-800/50 cursor-pointer group"
          onClick={() => imageLoaded && setModalOpen(true)}
        >
          {imageUrl ? (
            imageLoaded ? (
              <div
                className="relative mx-auto"
                style={{
                  width: thumbnailDimensions.width,
                  height: thumbnailDimensions.height,
                }}
              >
                <img
                  src={imageUrl}
                  alt={page.pageName}
                  className="w-full h-full"
                />
                {/* Region bounding boxes overlay */}
                {page.regions && page.regions.length > 0 && (
                  <RegionOverlay regions={page.regions} />
                )}
                {/* Hover overlay */}
                <div className="absolute inset-0 bg-slate-900/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center pointer-events-none">
                  <span className="text-white text-sm font-medium flex items-center gap-1">
                    <Maximize2 size={16} /> Click to expand
                  </span>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-center h-48">
                <Loader2 className="text-slate-500 animate-spin" size={24} />
              </div>
            )
          ) : (
            <div className="flex items-center justify-center h-48 text-slate-500">
              <span>No image available</span>
            </div>
          )}
        </div>
      </div>

        {/* Sheet Analysis - Agentic Vision output */}
        <div className="p-4 pb-0">
          <h3 className="text-sm font-medium text-slate-300 mb-3 flex items-center gap-2">
            <FileText size={14} /> Sheet Analysis
          </h3>

        {/* Sheet Info Header */}
        {page.sheetInfo && (
          <div className="mb-4 p-3 rounded-lg bg-slate-800/50 border border-slate-700/50">
            {page.sheetInfo.sheetNumber && (
              <p className="text-cyan-400 font-mono text-sm mb-1">
                {page.sheetInfo.sheetNumber}
              </p>
            )}
            {page.sheetInfo.sheetTitle && (
              <p className="text-slate-200 font-medium">{page.sheetInfo.sheetTitle}</p>
            )}
            {page.pageType && (
              <p className="text-xs text-slate-500 mt-1 capitalize">{page.pageType.replace(/_/g, ' ')}</p>
            )}
          </div>
        )}

        {/* Sheet Reflection (main analysis) */}
        {page.sheetReflection ? (
          <div className="prose prose-sm prose-invert prose-slate max-w-none">
            <div
              className="text-sm text-slate-400 leading-relaxed whitespace-pre-wrap"
              style={{ fontFamily: 'inherit' }}
            >
              {page.sheetReflection.split('\n').map((line, i) => {
                if (line.startsWith('### ')) {
                  return (
                    <h4 key={i} className="text-cyan-400 font-semibold mt-4 mb-2 text-sm">
                      {line.slice(4)}
                    </h4>
                  );
                }
                if (line.startsWith('## ')) {
                  return (
                    <h3 key={i} className="text-slate-200 font-semibold mt-4 mb-2">
                      {line.slice(3)}
                    </h3>
                  );
                }
                if (line.startsWith('**') && line.endsWith('**')) {
                  return (
                    <p key={i} className="text-slate-300 font-medium mt-2">
                      {line.slice(2, -2)}
                    </p>
                  );
                }
                if (line.startsWith('- ')) {
                  const content = line.slice(2);
                  const boldMatch = content.match(/^\*\*([^*]+)\*\*\s*(.*)$/);
                  if (boldMatch) {
                    return (
                      <p key={i} className="text-slate-400 pl-4 py-0.5">
                        <span className="text-slate-300 font-medium">{boldMatch[1]}</span>
                        {boldMatch[2] && <span> {boldMatch[2]}</span>}
                      </p>
                    );
                  }
                  return (
                    <p key={i} className="text-slate-400 pl-4 py-0.5">
                      {content}
                    </p>
                  );
                }
                if (line.trim() === '') {
                  return <div key={i} className="h-2" />;
                }
                return (
                  <p key={i} className="text-slate-400">
                    {line}
                  </p>
                );
              })}
            </div>
          </div>
        ) : page.contextMarkdown ? (
          // Fallback to legacy contextMarkdown
          <div className="prose prose-sm prose-invert prose-slate max-w-none">
            <div className="text-sm text-slate-400 leading-relaxed whitespace-pre-wrap">
              {page.contextMarkdown}
            </div>
          </div>
        ) : page.fullContext || page.initialContext ? (
          <p className="text-sm text-slate-400 leading-relaxed">
            {page.fullContext || page.initialContext}
          </p>
        ) : (
          <p className="text-sm text-slate-500 italic">
            {page.processingStatus === 'pending'
              ? 'This page has not been processed yet.'
              : page.processingStatus === 'processing'
              ? 'Processing in progress...'
              : 'No analysis available for this page.'}
          </p>
        )}

        {/* Cross References */}
        {page.crossReferences && page.crossReferences.length > 0 && (
          <div className="mt-4">
            <h4 className="text-xs font-medium text-slate-400 mb-2">Referenced Sheets</h4>
            <div className="flex flex-wrap gap-1">
              {page.crossReferences.map((ref, idx) => (
                <span
                  key={idx}
                  className="px-2 py-0.5 bg-slate-700/50 rounded text-xs text-cyan-400"
                >
                  {ref}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Questions This Sheet Answers */}
        {page.questionsAnswered && page.questionsAnswered.length > 0 && (
          <div className="mt-4">
            <h4 className="text-xs font-medium text-slate-400 mb-2">Questions This Sheet Answers</h4>
            <ul className="space-y-1">
              {page.questionsAnswered.map((q, idx) => (
                <li key={idx} className="text-sm text-slate-400 pl-3 relative">
                  <span className="absolute left-0 text-cyan-500">•</span>
                  {q}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Regions (structural areas identified on the sheet) */}
        {page.regions && page.regions.length > 0 && (
          <div className="mt-6">
            <h3 className="text-sm font-medium text-slate-300 mb-3">
              Identified Regions ({page.regions.length})
            </h3>
            <div className="space-y-2">
              {page.regions.map((region, idx) => (
                <div
                  key={region.id || idx}
                  className="p-3 rounded-lg bg-slate-800/50 border border-slate-700/50"
                >
                  <div className="flex items-start gap-2">
                    <span className="text-cyan-400 font-mono text-xs uppercase">
                      {region.type || 'region'}
                    </span>
                    <div className="flex-1 min-w-0">
                      {region.label && (
                        <p className="text-slate-200 text-sm font-medium">{region.label}</p>
                      )}
                      {region.content && (
                        <p className="text-xs text-slate-500 mt-1 line-clamp-2">{region.content}</p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Legacy details fallback */}
        {!page.regions?.length && page.details && page.details.length > 0 && (
          <div className="mt-6">
            <h3 className="text-sm font-medium text-slate-300 mb-3">
              Extracted Details ({page.details.length})
            </h3>
            <div className="space-y-2">
              {page.details.map((detail, idx) => (
                <div
                  key={detail.id || idx}
                  className="p-3 rounded-lg bg-slate-800/50 border border-slate-700/50"
                >
                  <div className="flex items-start gap-2">
                    <span className="text-cyan-400 font-mono text-xs">
                      {detail.number || `#${idx + 1}`}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-slate-200 text-sm font-medium">{detail.title}</p>
                      {detail.shows && (
                        <p className="text-xs text-slate-500 mt-1">{detail.shows}</p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        </div>

        {/* View Page Button */}
        <div className="p-4 pt-2">
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

      {/* Thumbnail Modal - rendered via portal to escape panel bounds on mobile */}
      {imageUrl && modalOpen && createPortal(
        <PageThumbnailModal
          isOpen={modalOpen}
          onClose={() => setModalOpen(false)}
          imageUrl={imageUrl}
          pageName={page.pageName}
          regions={page.regions}
        />,
        document.body
      )}
    </div>
  );
}

export const PageContextView = memo(PageContextViewComponent);
