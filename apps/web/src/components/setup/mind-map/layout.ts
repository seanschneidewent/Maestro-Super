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
 * Calculates the intersection point where a line from center at angle θ
 * crosses the boundary of a rectangle.
 */
function getRectEdgePoint(
  centerX: number,
  centerY: number,
  halfWidth: number,
  halfHeight: number,
  angle: number
): { x: number; y: number } {
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);

  // Avoid division by zero
  const absCos = Math.abs(cos) < 0.0001 ? 0.0001 : Math.abs(cos);
  const absSin = Math.abs(sin) < 0.0001 ? 0.0001 : Math.abs(sin);

  // Distance to edge in each direction
  const rX = halfWidth / absCos;
  const rY = halfHeight / absSin;

  // Take the minimum (whichever edge is hit first)
  const r = Math.min(rX, rY);

  return {
    x: centerX + r * cos,
    y: centerY + r * sin,
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

  // Project node position (top-left corner at origin)
  const projectPosX = config.centerX;
  const projectPosY = config.centerY;

  // Project VISUAL CENTER (for SVG lines) - offset by half dimensions
  const projectVisualCenterX = projectPosX + NODE_DIMENSIONS.project.width / 2;
  const projectVisualCenterY = projectPosY + NODE_DIMENSIONS.project.height / 2;

  // --- Project Node (center) ---
  nodes.push({
    id: projectId,
    type: 'project',
    position: { x: projectPosX, y: projectPosY },
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
  // CRITICAL: Equal angular spacing around the circle
  // With N disciplines, each gets 360/N degrees of arc
  const n = hierarchy.disciplines.length;
  const radius = config.levelRadius[1];

  // The center point for the radial layout is the PROJECT'S VISUAL CENTER
  const cx = projectVisualCenterX;
  const cy = projectVisualCenterY;

  // Discipline node half-dimensions for centering
  const discHalfW = NODE_DIMENSIONS.discipline.width / 2;
  const discHalfH = NODE_DIMENSIONS.discipline.height / 2;

  // Pre-calculate all positions with EXACT equal angles
  const disciplinePositions: Array<{
    discipline: typeof hierarchy.disciplines[0];
    angle: number;
    visualCenterX: number;  // Where the line should END (discipline visual center)
    visualCenterY: number;
    nodeX: number;  // Where to place the node (top-left)
    nodeY: number;
  }> = [];

  for (let i = 0; i < n; i++) {
    // Angle in radians: start at top (-90°) and go clockwise
    // -Math.PI/2 = -90° = top of circle
    // Each step is (2π / n) radians = (360 / n) degrees
    const angleRad = -Math.PI / 2 + (i * 2 * Math.PI / n);

    // Visual center on circle: this is where the MIDDLE of the discipline node should be
    const visualCenterX = cx + radius * Math.cos(angleRad);
    const visualCenterY = cy + radius * Math.sin(angleRad);

    // Node position is offset so that visual center aligns with circle
    const nodeX = visualCenterX - discHalfW;
    const nodeY = visualCenterY - discHalfH;

    disciplinePositions.push({
      discipline: hierarchy.disciplines[i],
      angle: angleRad,
      visualCenterX,
      visualCenterY,
      nodeX,
      nodeY,
    });
  }

  // Now create nodes and lines using the calculated positions
  disciplinePositions.forEach(({ discipline, angle, visualCenterX, visualCenterY, nodeX, nodeY }, discIndex) => {
    const discMidAngle = angle;
    const angleStep = (2 * Math.PI) / n;

    // Allocate angular slice for children (pages/pointers within this discipline)
    const sliceStartAngle = discMidAngle - angleStep / 2;
    const sliceEndAngle = discMidAngle + angleStep / 2;

    // Position for the node (top-left corner)
    const discX = nodeX;
    const discY = nodeY;

    const disciplineNodeId = discipline.id;
    const isDisciplineExpanded = expandedNodes.has(disciplineNodeId);
    const totalPointers = discipline.pages.reduce((sum, p) => sum + p.pointers.length, 0);

    // Position node at calculated position (ReactFlow positions by top-left)
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

    // Edge: project → discipline (for ReactFlow)
    edges.push(createEdge(
      projectId,
      disciplineNodeId,
      discipline.processed ? '#f59e0b' : '#475569',
      2
    ));

    // SVG line: project EDGE → discipline EDGE (edge-to-edge connection)
    // This ensures equal visible gap between node boundaries
    const projectHalfW = NODE_DIMENSIONS.project.width / 2;
    const projectHalfH = NODE_DIMENSIONS.project.height / 2;

    // Project edge point (where line exits project node boundary)
    const projectEdge = getRectEdgePoint(
      projectVisualCenterX,
      projectVisualCenterY,
      projectHalfW,
      projectHalfH,
      angle // angle from project center to discipline
    );

    // Discipline edge point (where line enters discipline node boundary)
    // Angle is reversed (π + angle) since we're coming FROM the project
    const disciplineEdge = getRectEdgePoint(
      visualCenterX,
      visualCenterY,
      discHalfW,
      discHalfH,
      angle + Math.PI // opposite direction
    );

    lines.push({
      x1: projectEdge.x,
      y1: projectEdge.y,
      x2: disciplineEdge.x,
      y2: disciplineEdge.y,
      color: 'rgba(100, 116, 139, 0.5)', // Subtle slate color
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
