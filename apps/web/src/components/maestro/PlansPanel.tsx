import React, { useState, useEffect } from 'react';
import { ChevronRight, Folder, FileText, Loader2, AlertCircle } from 'lucide-react';
import { api } from '../../lib/api';
import { ProjectHierarchy, DisciplineInHierarchy, PageInHierarchy } from '../../types';

interface PageNodeProps {
  page: PageInHierarchy;
  isSelected: boolean;
  onSelect: (page: PageInHierarchy) => void;
  dataTutorial?: string;
}

const PageNode: React.FC<PageNodeProps> = ({ page, isSelected, onSelect, dataTutorial }) => {
  return (
    <button
      onClick={() => onSelect(page)}
      className={`w-full flex items-center gap-2 py-2 px-3 rounded-lg text-sm transition-all duration-150 ${
        isSelected
          ? 'bg-cyan-50 border-l-2 border-cyan-500 text-cyan-700 font-medium'
          : 'border-l-2 border-transparent hover:bg-slate-100 text-slate-600 hover:text-slate-800'
      }`}
      data-tutorial={dataTutorial}
    >
      <FileText size={14} className={isSelected ? 'text-cyan-500' : 'text-slate-400'} />
      <span className="truncate">{page.pageName}</span>
    </button>
  );
};

interface DisciplineNodeProps {
  discipline: DisciplineInHierarchy;
  selectedPageId: string | null;
  onPageSelect: (page: PageInHierarchy, disciplineId: string) => void;
  defaultExpanded?: boolean;
  firstPageTutorial?: string; // data-tutorial attribute for the first page in this discipline
}

const DisciplineNode: React.FC<DisciplineNodeProps> = ({
  discipline,
  selectedPageId,
  onPageSelect,
  defaultExpanded = false,
  firstPageTutorial,
}) => {
  const [isOpen, setIsOpen] = useState(defaultExpanded);

  // Auto-expand if a page in this discipline is selected
  useEffect(() => {
    if (selectedPageId && discipline.pages.some(p => p.id === selectedPageId)) {
      setIsOpen(true);
    }
  }, [selectedPageId, discipline.pages]);

  const pageCount = discipline.pages.length;

  return (
    <div className="mb-1">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`w-full flex items-center gap-2 py-2.5 px-3 rounded-lg transition-all duration-150 ${
          isOpen
            ? 'sticky top-0 z-10 bg-slate-100 text-slate-800 shadow-sm'
            : 'hover:bg-slate-50 text-slate-600'
        }`}
      >
        <span className={`transition-transform duration-200 ${isOpen ? 'rotate-90' : ''}`}>
          <ChevronRight size={14} className="text-slate-400" />
        </span>
        <Folder size={16} className={isOpen ? 'text-cyan-500' : 'text-slate-400'} />
        <span className="font-medium truncate">{discipline.displayName}</span>
        <span className="ml-auto text-xs text-slate-400">{pageCount}</span>
      </button>

      {isOpen && discipline.pages.length > 0 && (
        <div className="ml-6 mt-1 space-y-0.5 animate-fade-in">
          {discipline.pages.map((page, pageIndex) => (
            <PageNode
              key={page.id}
              page={page}
              isSelected={selectedPageId === page.id}
              onSelect={(p) => onPageSelect(p, discipline.id)}
              dataTutorial={pageIndex === 0 ? firstPageTutorial : undefined}
            />
          ))}
        </div>
      )}
    </div>
  );
};

interface PlansPanelProps {
  projectId: string;
  selectedPageId: string | null;
  onPageSelect: (pageId: string, disciplineId: string, pageName: string, filePath?: string) => void;
}

export const PlansPanel: React.FC<PlansPanelProps> = ({
  projectId,
  selectedPageId,
  onPageSelect,
}) => {
  const [hierarchy, setHierarchy] = useState<ProjectHierarchy | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadHierarchy = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await api.projects.getHierarchy(projectId);
        setHierarchy(data);
      } catch (err) {
        console.error('Failed to load hierarchy:', err);
        setError(err instanceof Error ? err.message : 'Failed to load plans');
      } finally {
        setIsLoading(false);
      }
    };

    loadHierarchy();
  }, [projectId]);

  const handlePageSelect = (page: PageInHierarchy, disciplineId: string) => {
    // PageInHierarchy doesn't have filePath, we'll need to fetch it
    // For now, pass what we have and let UseMode handle loading the page
    onPageSelect(page.id, disciplineId, page.pageName);
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-3">
        <Loader2 size={24} className="animate-spin text-cyan-500" />
        <span className="text-sm">Loading plans...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-3 px-4">
        <AlertCircle size={24} className="text-red-500" />
        <span className="text-sm text-center">{error}</span>
      </div>
    );
  }

  if (!hierarchy || hierarchy.disciplines.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-3 px-4">
        <Folder size={32} className="text-slate-300" />
        <span className="text-sm text-center">No plans uploaded yet</span>
        <span className="text-xs text-slate-400 text-center">
          Switch to Setup mode to upload plans
        </span>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto px-2 py-2 space-y-1">
      {hierarchy.disciplines.map((discipline, index) => (
        <DisciplineNode
          key={discipline.id}
          discipline={discipline}
          selectedPageId={selectedPageId}
          onPageSelect={handlePageSelect}
          defaultExpanded={index === 0} // Expand first discipline by default
          firstPageTutorial={index === 0 ? 'first-page' : undefined} // Tutorial highlights first page
        />
      ))}
    </div>
  );
};
