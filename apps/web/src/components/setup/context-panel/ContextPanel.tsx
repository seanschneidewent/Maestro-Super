import { ContextMindMap } from '../ContextMindMap';
import { DisciplineDetail } from './DisciplineDetail';
import { PageDetail } from './PageDetail';
import { PointerDetail } from './PointerDetail';
import type { ProjectHierarchy, DisciplineInHierarchy, PageInHierarchy } from '../../../types';

export type PanelView =
  | { type: 'mindmap' }
  | { type: 'discipline'; disciplineId: string }
  | { type: 'page'; pageId: string; disciplineId: string }
  | { type: 'pointer'; pointerId: string; pageId: string; disciplineId: string };

interface ContextPanelProps {
  projectId: string;
  hierarchy: ProjectHierarchy | null;
  panelView: PanelView;
  setPanelView: (view: PanelView) => void;
  activePageId?: string;
  refreshTrigger?: number;
  onNavigateToPage: (pageId: string) => void;
  onHighlightPointer?: (pointerId: string) => void;
}

export function ContextPanel({
  projectId,
  hierarchy,
  panelView,
  setPanelView,
  activePageId,
  refreshTrigger,
  onNavigateToPage,
  onHighlightPointer,
}: ContextPanelProps) {
  // Get data for current view from hierarchy
  const getDiscipline = (id: string): DisciplineInHierarchy | undefined => {
    return hierarchy?.disciplines.find((d) => d.id === id);
  };

  const getPages = (disciplineId: string): PageInHierarchy[] => {
    return getDiscipline(disciplineId)?.pages || [];
  };

  const getDisciplineForPage = (pageId: string): DisciplineInHierarchy | undefined => {
    return hierarchy?.disciplines.find((d) => d.pages.some((p) => p.id === pageId));
  };

  // Navigation handlers
  const goBack = () => {
    if (panelView.type === 'pointer') {
      setPanelView({
        type: 'page',
        pageId: panelView.pageId,
        disciplineId: panelView.disciplineId,
      });
    } else if (panelView.type === 'page') {
      setPanelView({
        type: 'discipline',
        disciplineId: panelView.disciplineId,
      });
    } else if (panelView.type === 'discipline') {
      setPanelView({ type: 'mindmap' });
    }
  };

  // Render based on current view
  if (panelView.type === 'mindmap') {
    return (
      <ContextMindMap
        projectId={projectId}
        activePageId={activePageId}
        refreshTrigger={refreshTrigger}
        onDisciplineClick={(disciplineId) => {
          setPanelView({ type: 'discipline', disciplineId });
        }}
        onPageClick={(pageId, disciplineId) => {
          setPanelView({ type: 'page', pageId, disciplineId });
          onNavigateToPage(pageId);
        }}
        onPointerClick={(pointerId, pageId) => {
          const disc = getDisciplineForPage(pageId);
          setPanelView({
            type: 'pointer',
            pointerId,
            pageId,
            disciplineId: disc?.id || '',
          });
          onNavigateToPage(pageId);
          onHighlightPointer?.(pointerId);
        }}
      />
    );
  }

  if (panelView.type === 'discipline') {
    const discipline = getDiscipline(panelView.disciplineId);
    return (
      <DisciplineDetail
        disciplineId={panelView.disciplineId}
        pages={getPages(panelView.disciplineId)}
        onBack={goBack}
        onPageClick={(pageId) => {
          setPanelView({
            type: 'page',
            pageId,
            disciplineId: panelView.disciplineId,
          });
          onNavigateToPage(pageId);
        }}
      />
    );
  }

  if (panelView.type === 'page') {
    const discipline = getDiscipline(panelView.disciplineId);
    return (
      <PageDetail
        pageId={panelView.pageId}
        disciplineName={discipline?.displayName || 'Unknown'}
        onBack={goBack}
        onPointerClick={(pointerId) => {
          setPanelView({
            type: 'pointer',
            pointerId,
            pageId: panelView.pageId,
            disciplineId: panelView.disciplineId,
          });
          onHighlightPointer?.(pointerId);
        }}
        onViewPage={() => {
          onNavigateToPage(panelView.pageId);
        }}
      />
    );
  }

  if (panelView.type === 'pointer') {
    return (
      <PointerDetail
        pointerId={panelView.pointerId}
        onBack={goBack}
        onReferenceClick={(targetPageId) => {
          // Navigate to the referenced page
          const disc = getDisciplineForPage(targetPageId);
          setPanelView({
            type: 'page',
            pageId: targetPageId,
            disciplineId: disc?.id || '',
          });
          onNavigateToPage(targetPageId);
        }}
      />
    );
  }

  return null;
}
