import { MindMapNode, MindMapEdge, DEFAULT_LAYOUT_CONFIG } from './types';
import type { ProjectHierarchy, DisciplineInHierarchy } from '../../../types';

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

interface LayoutResult {
  nodes: MindMapNode[];
  edges: MindMapEdge[];
}

/**
 * Distributes items radially around a center point within an angular range.
 * Returns array of {x, y, angle} positions.
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
 * Counts total visible descendants for a discipline (for angular allocation)
 */
function countDisciplineWeight(
  discipline: DisciplineInHierarchy,
  expandedNodes: Set<string>
): number {
  if (!expandedNodes.has(discipline.id)) {
    return 1; // Just the discipline node itself
  }

  let weight = 1; // The discipline itself
  for (const page of discipline.pages) {
    weight += 1; // The page
    if (expandedNodes.has(page.id)) {
      weight += page.pointers.length; // Add pointers if page is expanded
    }
  }
  return weight;
}

/**
 * Converts hierarchy data to positioned ReactFlow nodes and edges.
 * Uses radial layout with project at center.
 */
export function layoutHierarchy(
  hierarchy: ProjectHierarchy,
  options: LayoutOptions
): LayoutResult {
  const { expandedNodes, activePageId, callbacks } = options;
  const config = DEFAULT_LAYOUT_CONFIG;

  const nodes: MindMapNode[] = [];
  const edges: MindMapEdge[] = [];

  const projectId = `project-${hierarchy.name}`;
  const isProjectExpanded = expandedNodes.has(projectId);

  // --- Project Node (center) ---
  nodes.push({
    id: projectId,
    type: 'project',
    position: { x: config.centerX, y: config.centerY },
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
    return { nodes, edges };
  }

  // --- Calculate angular allocation for disciplines ---
  // Weight each discipline by its visible descendants
  const disciplineWeights = hierarchy.disciplines.map(d =>
    countDisciplineWeight(d, expandedNodes)
  );
  const totalWeight = disciplineWeights.reduce((a, b) => a + b, 0);

  // Distribute disciplines around full circle (with small gaps)
  const fullCircle = Math.PI * 2;
  const gapAngle = 0.1; // Small gap between major sections
  const availableAngle = fullCircle - (gapAngle * hierarchy.disciplines.length);

  let currentAngle = -Math.PI / 2; // Start from top

  hierarchy.disciplines.forEach((discipline, discIndex) => {
    const weight = disciplineWeights[discIndex];
    const allocatedAngle = (weight / totalWeight) * availableAngle;
    const discEndAngle = currentAngle + allocatedAngle;
    const discMidAngle = currentAngle + allocatedAngle / 2;

    // Position discipline node
    const discX = config.centerX + config.levelRadius[1] * Math.cos(discMidAngle);
    const discY = config.centerY + config.levelRadius[1] * Math.sin(discMidAngle);

    const disciplineNodeId = discipline.id;
    const isDisciplineExpanded = expandedNodes.has(disciplineNodeId);

    // Count total pointers in discipline
    const totalPointers = discipline.pages.reduce((sum, p) => sum + p.pointers.length, 0);

    nodes.push({
      id: disciplineNodeId,
      type: 'discipline',
      position: { x: discX, y: discY },
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

    // Edge from project to discipline
    edges.push({
      id: `e-${projectId}-${disciplineNodeId}`,
      source: projectId,
      target: disciplineNodeId,
      type: 'smoothstep',
      style: {
        stroke: discipline.processed ? '#f59e0b' : '#64748b',
        strokeWidth: 2,
        opacity: 0.5,
      },
    });

    // --- Pages within discipline ---
    if (isDisciplineExpanded && discipline.pages.length > 0) {
      // Calculate angular space for each page based on its weight
      const pageWeights = discipline.pages.map(page =>
        expandedNodes.has(page.id) ? 1 + page.pointers.length : 1
      );
      const pageTotalWeight = pageWeights.reduce((a, b) => a + b, 0);

      let pageCurrentAngle = currentAngle;

      discipline.pages.forEach((page, pageIndex) => {
        const pageWeight = pageWeights[pageIndex];
        const pageAllocatedAngle = (pageWeight / pageTotalWeight) * allocatedAngle;
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

        // Edge from discipline to page
        edges.push({
          id: `e-${disciplineNodeId}-${pageNodeId}`,
          source: disciplineNodeId,
          target: pageNodeId,
          type: 'smoothstep',
          style: {
            stroke: '#64748b',
            strokeWidth: 1.5,
            opacity: 0.4,
          },
        });

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

            // Edge from page to pointer
            edges.push({
              id: `e-${pageNodeId}-${pointerNodeId}`,
              source: pageNodeId,
              target: pointerNodeId,
              type: 'smoothstep',
              style: {
                stroke: '#8b5cf6',
                strokeWidth: 1,
                opacity: 0.4,
              },
            });
          });
        }

        pageCurrentAngle += pageAllocatedAngle;
      });
    }

    currentAngle = discEndAngle + gapAngle;
  });

  return { nodes, edges };
}

/**
 * Generates initial expanded state (project + disciplines visible)
 */
export function getInitialExpandedState(hierarchy: ProjectHierarchy): string[] {
  const projectId = `project-${hierarchy.name}`;
  return [projectId]; // Just project expanded, disciplines visible but not their children
}
