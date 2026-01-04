import { MindMapNode, MindMapEdge, DEFAULT_LAYOUT_CONFIG, NODE_DIMENSIONS } from './types';
import type { ProjectHierarchy } from '../../../types';

interface LayoutCallbacks {
  onProjectExpand: () => void;
  onDisciplineClick: (id: string) => void;
  onDisciplineExpand: (id: string) => void;
  onPageClick: (id: string, disciplineId: string) => void;
  onPageExpand: (id: string) => void;
  onPointerClick: (id: string, pageId: string, disciplineId: string) => void;
}

interface LayoutOptions {
  expandedNodes: Set<string>;
  activePageId?: string;
  callbacks: LayoutCallbacks;
}

export interface ConnectionLine {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  color: string;
  width: number;
}

interface LayoutResult {
  nodes: MindMapNode[];
  edges: MindMapEdge[];
  lines: ConnectionLine[];
}

/**
 * Simple radial layout:
 * - Project center at origin (0, 0)
 * - Discipline centers at radius R, equal angles
 * - Lines from center to center, all same length
 */
export function layoutHierarchy(
  hierarchy: ProjectHierarchy,
  options: LayoutOptions
): LayoutResult {
  const { expandedNodes, activePageId, callbacks } = options;
  const config = DEFAULT_LAYOUT_CONFIG;

  const nodes: MindMapNode[] = [];
  const edges: MindMapEdge[] = [];
  const lines: ConnectionLine[] = [];

  const projectId = `project-${hierarchy.name}`;
  const isProjectExpanded = expandedNodes.has(projectId);

  // ===========================================
  // ORIGIN: The center of our radial layout
  // ===========================================
  const ORIGIN_X = 0;
  const ORIGIN_Y = 0;

  // ===========================================
  // PROJECT NODE
  // Position so its CENTER is at origin
  // ===========================================
  const projectWidth = NODE_DIMENSIONS.project.width;
  const projectHeight = NODE_DIMENSIONS.project.height;
  const projectNodeX = ORIGIN_X - projectWidth / 2;
  const projectNodeY = ORIGIN_Y - projectHeight / 2;

  nodes.push({
    id: projectId,
    type: 'project',
    position: { x: projectNodeX, y: projectNodeY },
    data: {
      type: 'project',
      id: projectId,
      name: hierarchy.name,
      disciplineCount: hierarchy.disciplines.length,
      onExpand: callbacks.onProjectExpand,
      isExpanded: isProjectExpanded,
    },
  });

  if (!isProjectExpanded || hierarchy.disciplines.length === 0) {
    return { nodes, edges, lines };
  }

  // ===========================================
  // DISCIPLINE NODES
  // All centers at radius R from origin
  // Equal angles: i * (2π / n), starting at top
  // ===========================================
  const n = hierarchy.disciplines.length;
  const radius = config.levelRadius[1];
  const discWidth = NODE_DIMENSIONS.discipline.width;
  const discHeight = NODE_DIMENSIONS.discipline.height;

  hierarchy.disciplines.forEach((discipline, i) => {
    // Angle: start at top (-π/2), equal spacing
    const angle = -Math.PI / 2 + (i * 2 * Math.PI / n);

    // Discipline CENTER position (on the circle)
    const discCenterX = ORIGIN_X + radius * Math.cos(angle);
    const discCenterY = ORIGIN_Y + radius * Math.sin(angle);

    // Node position (top-left, offset from center)
    const discNodeX = discCenterX - discWidth / 2;
    const discNodeY = discCenterY - discHeight / 2;

    const disciplineNodeId = discipline.id;
    const isDisciplineExpanded = expandedNodes.has(disciplineNodeId);
    const totalPointers = discipline.pages.reduce((sum, p) => sum + p.pointers.length, 0);

    nodes.push({
      id: disciplineNodeId,
      type: 'discipline',
      position: { x: discNodeX, y: discNodeY },
      data: {
        type: 'discipline',
        id: discipline.id,
        name: discipline.name,
        displayName: discipline.displayName,
        processed: discipline.processed,
        pageCount: discipline.pages.length,
        pointerCount: totalPointers,
        onExpand: () => callbacks.onDisciplineExpand(discipline.id),
        onClick: () => callbacks.onDisciplineClick(discipline.id),
        isExpanded: isDisciplineExpanded,
      },
    });

    // ReactFlow edge (for interaction/selection if needed)
    edges.push({
      id: `e-${projectId}-${disciplineNodeId}`,
      source: projectId,
      target: disciplineNodeId,
      type: 'straight',
      style: {
        stroke: discipline.processed ? '#f59e0b' : '#475569',
        strokeWidth: 2,
        opacity: 0.4,
      },
      zIndex: 0,
    });

    // SVG line: center-to-center (origin to discipline center)
    // All lines have the same length (radius)
    lines.push({
      x1: ORIGIN_X,
      y1: ORIGIN_Y,
      x2: discCenterX,
      y2: discCenterY,
      color: 'rgba(100, 116, 139, 0.5)',
      width: 2,
    });

    // ===========================================
    // PAGES (when discipline is expanded)
    // ===========================================
    if (isDisciplineExpanded && discipline.pages.length > 0) {
      const pageRadius = config.levelRadius[2];
      const pageWidth = NODE_DIMENSIONS.page.width;
      const pageHeight = NODE_DIMENSIONS.page.height;

      // Angular slice for this discipline's children
      const angleStep = (2 * Math.PI) / n;
      const sliceStart = angle - angleStep / 2;
      const sliceEnd = angle + angleStep / 2;

      // Distribute pages within slice
      const pageCount = discipline.pages.length;
      discipline.pages.forEach((page, pageIndex) => {
        // Page angle within slice
        const pageAngle = pageCount === 1
          ? angle
          : sliceStart + ((pageIndex + 0.5) / pageCount) * (sliceEnd - sliceStart);

        // Page CENTER position
        const pageCenterX = ORIGIN_X + pageRadius * Math.cos(pageAngle);
        const pageCenterY = ORIGIN_Y + pageRadius * Math.sin(pageAngle);

        // Node position (top-left)
        const pageNodeX = pageCenterX - pageWidth / 2;
        const pageNodeY = pageCenterY - pageHeight / 2;

        const pageNodeId = page.id;
        const isPageExpanded = expandedNodes.has(pageNodeId);

        nodes.push({
          id: pageNodeId,
          type: 'page',
          position: { x: pageNodeX, y: pageNodeY },
          data: {
            type: 'page',
            id: page.id,
            pageName: page.pageName,
            disciplineId: discipline.id,
            pointerCount: page.pointerCount,
            processedPass1: page.processedPass1,
            processedPass2: page.processedPass2,
            onExpand: () => callbacks.onPageExpand(page.id),
            onClick: () => callbacks.onPageClick(page.id, discipline.id),
            isExpanded: isPageExpanded,
            isActive: page.id === activePageId,
          },
        });

        // Edge: discipline → page
        edges.push({
          id: `e-${disciplineNodeId}-${pageNodeId}`,
          source: disciplineNodeId,
          target: pageNodeId,
          type: 'straight',
          style: {
            stroke: '#475569',
            strokeWidth: 1.5,
            opacity: 0.4,
          },
          zIndex: 0,
        });

        // ===========================================
        // POINTERS (when page is expanded)
        // ===========================================
        if (isPageExpanded && page.pointers.length > 0) {
          const pointerRadius = config.levelRadius[3];
          const pointerWidth = NODE_DIMENSIONS.pointer.width;
          const pointerHeight = NODE_DIMENSIONS.pointer.height;

          // Distribute pointers around the page's angle
          const pointerCount = page.pointers.length;
          const pointerSliceStart = pageAngle - angleStep / (2 * pageCount);
          const pointerSliceEnd = pageAngle + angleStep / (2 * pageCount);

          page.pointers.forEach((pointer, ptrIndex) => {
            const pointerAngle = pointerCount === 1
              ? pageAngle
              : pointerSliceStart + ((ptrIndex + 0.5) / pointerCount) * (pointerSliceEnd - pointerSliceStart);

            const pointerCenterX = ORIGIN_X + pointerRadius * Math.cos(pointerAngle);
            const pointerCenterY = ORIGIN_Y + pointerRadius * Math.sin(pointerAngle);

            const pointerNodeX = pointerCenterX - pointerWidth / 2;
            const pointerNodeY = pointerCenterY - pointerHeight / 2;

            const pointerNodeId = pointer.id;

            nodes.push({
              id: pointerNodeId,
              type: 'pointer',
              position: { x: pointerNodeX, y: pointerNodeY },
              data: {
                type: 'pointer',
                id: pointer.id,
                title: pointer.title,
                pageId: page.id,
                disciplineId: discipline.id,
                onClick: () => callbacks.onPointerClick(pointer.id, page.id, discipline.id),
              },
            });

            // Edge: page → pointer
            edges.push({
              id: `e-${pageNodeId}-${pointerNodeId}`,
              source: pageNodeId,
              target: pointerNodeId,
              type: 'straight',
              style: {
                stroke: '#8b5cf6',
                strokeWidth: 1,
                opacity: 0.4,
              },
              zIndex: 0,
            });
          });
        }
      });
    }
  });

  return { nodes, edges, lines };
}

/**
 * Initial expanded state: project expanded so disciplines are visible
 */
export function getInitialExpandedState(hierarchy: ProjectHierarchy): string[] {
  const projectId = `project-${hierarchy.name}`;
  return [projectId];
}
