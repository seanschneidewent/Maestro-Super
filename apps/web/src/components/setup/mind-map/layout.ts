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
  lines: ConnectionLine[];  // For custom SVG rendering
}

/**
 * Distributes items radially around a center point within an angular range.
 */
function distributeRadially(
  count: number,
  centerX: number,
  centerY: number,
  radius: number,
  startAngle: number,
  endAngle: number
): { x: number; y: number; angle: number }[] {
  if (count === 0) return [];
  if (count === 1) {
    const midAngle = (startAngle + endAngle) / 2;
    return [{
      x: centerX + radius * Math.cos(midAngle),
      y: centerY + radius * Math.sin(midAngle),
      angle: midAngle,
    }];
  }

  const positions: { x: number; y: number; angle: number }[] = [];
  const angleStep = (endAngle - startAngle) / (count - 1);

  for (let i = 0; i < count; i++) {
    const angle = startAngle + i * angleStep;
    positions.push({
      x: centerX + radius * Math.cos(angle),
      y: centerY + radius * Math.sin(angle),
      angle,
    });
  }

  return positions;
}


/**
 * Creates a straight line edge for radial connections
 */
function createEdge(
  sourceId: string,
  targetId: string,
  color: string,
  width: number = 2
): MindMapEdge {
  return {
    id: `e-${sourceId}-${targetId}`,
    source: sourceId,
    target: targetId,
    type: 'straight',
    style: {
      stroke: color,
      strokeWidth: width,
      opacity: 0.4,
    },
    zIndex: 0, // Ensure edges render behind nodes
  };
}

/**
 * Converts hierarchy data to positioned ReactFlow nodes and edges.
 * Uses radial layout with project at center and floating bezier edges.
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

  // Project center position (for SVG lines)
  const projectCenterX = config.centerX;
  const projectCenterY = config.centerY;

  // --- Project Node (center) - offset by half dimensions so node is centered ---
  const projectOffset = {
    x: NODE_DIMENSIONS.project.width / 2,
    y: NODE_DIMENSIONS.project.height / 2,
  };
  nodes.push({
    id: projectId,
    type: 'project',
    position: {
      x: projectCenterX - projectOffset.x,
      y: projectCenterY - projectOffset.y
    },
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

  // --- Calculate angular positions for disciplines ---
  // Use equal angular spacing for disciplines (even distribution around circle)
  const disciplineCount = hierarchy.disciplines.length;
  const fullCircle = Math.PI * 2;
  const anglePerDiscipline = fullCircle / disciplineCount;
  const startAngle = -Math.PI / 2; // Start from top

  // Discipline node offset for centering
  const discOffset = {
    x: NODE_DIMENSIONS.discipline.width / 2,
    y: NODE_DIMENSIONS.discipline.height / 2,
  };

  hierarchy.disciplines.forEach((discipline, discIndex) => {
    // Equal angular spacing: each discipline at index * (360/count) degrees
    const discMidAngle = startAngle + (discIndex * anglePerDiscipline);

    // Allocate angular slice for children (pages/pointers within this discipline)
    const sliceStartAngle = discMidAngle - anglePerDiscipline / 2;
    const sliceEndAngle = discMidAngle + anglePerDiscipline / 2;

    // Calculate discipline CENTER position (for SVG lines)
    const discCenterX = config.centerX + config.levelRadius[1] * Math.cos(discMidAngle);
    const discCenterY = config.centerY + config.levelRadius[1] * Math.sin(discMidAngle);

    const disciplineNodeId = discipline.id;
    const isDisciplineExpanded = expandedNodes.has(disciplineNodeId);
    const totalPointers = discipline.pages.reduce((sum, p) => sum + p.pointers.length, 0);

    // Position node offset by half dimensions so center aligns with calculated position
    nodes.push({
      id: disciplineNodeId,
      type: 'discipline',
      position: {
        x: discCenterX - discOffset.x,
        y: discCenterY - discOffset.y
      },
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

    // Edge: project → discipline (for ReactFlow)
    edges.push(createEdge(
      projectId,
      disciplineNodeId,
      discipline.processed ? '#f59e0b' : '#475569',
      2
    ));

    // SVG line: project center → discipline center
    lines.push({
      x1: projectCenterX,
      y1: projectCenterY,
      x2: discCenterX,
      y2: discCenterY,
      color: discipline.processed ? 'rgba(245, 158, 11, 0.5)' : 'rgba(100, 116, 139, 0.4)',
      width: 2,
    });

    // --- Pages within discipline ---
    if (isDisciplineExpanded && discipline.pages.length > 0) {
      const pageWeights = discipline.pages.map(page =>
        expandedNodes.has(page.id) ? 1 + page.pointers.length : 1
      );
      const pageTotalWeight = pageWeights.reduce((a, b) => a + b, 0);
      const sliceAngle = sliceEndAngle - sliceStartAngle;

      let pageCurrentAngle = sliceStartAngle;

      discipline.pages.forEach((page, pageIndex) => {
        const pageWeight = pageWeights[pageIndex];
        const pageAllocatedAngle = (pageWeight / pageTotalWeight) * sliceAngle;
        const pageMidAngle = pageCurrentAngle + pageAllocatedAngle / 2;

        const pageX = config.centerX + config.levelRadius[2] * Math.cos(pageMidAngle);
        const pageY = config.centerY + config.levelRadius[2] * Math.sin(pageMidAngle);

        const pageNodeId = page.id;
        const isPageExpanded = expandedNodes.has(pageNodeId);

        nodes.push({
          id: pageNodeId,
          type: 'page',
          position: { x: pageX, y: pageY },
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
        edges.push(createEdge(
          disciplineNodeId,
          pageNodeId,
          '#475569',
          1.5
        ));

        // --- Pointers within page ---
        if (isPageExpanded && page.pointers.length > 0) {
          const pointerPositions = distributeRadially(
            page.pointers.length,
            config.centerX,
            config.centerY,
            config.levelRadius[3],
            pageCurrentAngle,
            pageCurrentAngle + pageAllocatedAngle
          );

          page.pointers.forEach((pointer, ptrIndex) => {
            const pos = pointerPositions[ptrIndex];
            const pointerNodeId = pointer.id;

            nodes.push({
              id: pointerNodeId,
              type: 'pointer',
              position: { x: pos.x, y: pos.y },
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
            edges.push(createEdge(
              pageNodeId,
              pointerNodeId,
              '#8b5cf6',
              1
            ));
          });
        }

        pageCurrentAngle += pageAllocatedAngle;
      });
    }
  });

  return { nodes, edges, lines };
}

/**
 * Generates initial expanded state (project expanded, disciplines visible)
 */
export function getInitialExpandedState(hierarchy: ProjectHierarchy): string[] {
  const projectId = `project-${hierarchy.name}`;
  return [projectId];
}
