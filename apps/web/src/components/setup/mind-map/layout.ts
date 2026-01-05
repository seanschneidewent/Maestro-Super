import dagre from '@dagrejs/dagre';
import { MindMapNode, MindMapEdge, NODE_DIMENSIONS } from './types';
import type { ProjectHierarchy } from '../../../types';

interface LayoutCallbacks {
  onProjectExpand: () => void;
  onDisciplineClick: (id: string) => void;
  onDisciplineExpand: (id: string) => void;
  onPageClick: (id: string, disciplineId: string) => void;
  onPageExpand: (id: string) => void;
  onPointerClick: (id: string, pageId: string, disciplineId: string) => void;
  onPointerDelete: (id: string) => void;
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
    type: 'smoothstep',
    style: {
      stroke: color,
      strokeWidth: width,
      opacity: 0.5,
    },
  };
}

export function layoutHierarchy(
  hierarchy: ProjectHierarchy,
  options: LayoutOptions
): LayoutResult {
  const { expandedNodes, activePageId, callbacks } = options;

  const nodes: MindMapNode[] = [];
  const edges: MindMapEdge[] = [];

  const g = new dagre.graphlib.Graph();
  g.setGraph({
    rankdir: 'LR',
    nodesep: 20,      // Reduced vertical separation
    ranksep: 80,      // Reduced horizontal separation
    marginx: 10,
    marginy: 10,
  });
  g.setDefaultEdgeLabel(() => ({}));

  const projectId = `project-${hierarchy.name}`;
  const isProjectExpanded = expandedNodes.has(projectId);

  g.setNode(projectId, {
    width: NODE_DIMENSIONS.project.width,
    height: NODE_DIMENSIONS.project.height,
  });

  nodes.push({
    id: projectId,
    type: 'project',
    position: { x: 0, y: 0 },
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
    dagre.layout(g);
    const projectPos = g.node(projectId);
    nodes[0].position = {
      x: projectPos.x - NODE_DIMENSIONS.project.width / 2,
      y: projectPos.y - NODE_DIMENSIONS.project.height / 2,
    };
    return { nodes, edges };
  }

  hierarchy.disciplines.forEach((discipline) => {
    const disciplineNodeId = discipline.id;
    const isDisciplineExpanded = expandedNodes.has(disciplineNodeId);
    const totalPointers = discipline.pages.reduce((sum, p) => sum + p.pointers.length, 0);

    g.setNode(disciplineNodeId, {
      width: NODE_DIMENSIONS.discipline.width,
      height: NODE_DIMENSIONS.discipline.height,
    });

    g.setEdge(projectId, disciplineNodeId);

    nodes.push({
      id: disciplineNodeId,
      key: `${disciplineNodeId}-${isProjectExpanded}`,
      type: 'discipline',
      position: { x: 0, y: 0 },
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
        animationKey: `${disciplineNodeId}-${isProjectExpanded}`,
      },
    });

    edges.push(createEdge(
      projectId,
      disciplineNodeId,
      discipline.processed ? '#f59e0b' : '#475569',
      2
    ));

    if (isDisciplineExpanded && discipline.pages.length > 0) {
      discipline.pages.forEach((page) => {
        const pageNodeId = page.id;
        const isPageExpanded = expandedNodes.has(pageNodeId);

        g.setNode(pageNodeId, {
          width: NODE_DIMENSIONS.page.width,
          height: NODE_DIMENSIONS.page.height,
        });

        g.setEdge(disciplineNodeId, pageNodeId);

        nodes.push({
          id: pageNodeId,
          key: `${pageNodeId}-${isDisciplineExpanded}`,
          type: 'page',
          position: { x: 0, y: 0 },
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
            animationKey: `${pageNodeId}-${isDisciplineExpanded}`,
          },
        });

        edges.push(createEdge(
          disciplineNodeId,
          pageNodeId,
          '#475569',
          1.5
        ));

        if (isPageExpanded && page.pointers.length > 0) {
          // Add extra height padding for pointer nodes to improve vertical spacing
          const POINTER_DAGRE_HEIGHT_PADDING = 16;

          page.pointers.forEach((pointer) => {
            const pointerNodeId = pointer.id;

            g.setNode(pointerNodeId, {
              width: NODE_DIMENSIONS.pointer.width,
              height: NODE_DIMENSIONS.pointer.height + POINTER_DAGRE_HEIGHT_PADDING,
            });

            g.setEdge(pageNodeId, pointerNodeId);

            nodes.push({
              id: pointerNodeId,
              key: `${pointerNodeId}-${isPageExpanded}`,
              type: 'pointer',
              position: { x: 0, y: 0 },
              data: {
                type: 'pointer',
                id: pointer.id,
                title: pointer.title,
                pageId: page.id,
                disciplineId: discipline.id,
                onClick: () => callbacks.onPointerClick(pointer.id, page.id, discipline.id),
                onDelete: () => callbacks.onPointerDelete(pointer.id),
                animationKey: `${pointerNodeId}-${isPageExpanded}`,
              },
            });

            edges.push(createEdge(
              pageNodeId,
              pointerNodeId,
              '#8b5cf6',
              1
            ));
          });
        }
      });
    }
  });

  dagre.layout(g);

  nodes.forEach((node) => {
    const nodeWithPosition = g.node(node.id);
    if (nodeWithPosition) {
      const dims = NODE_DIMENSIONS[node.data.type as keyof typeof NODE_DIMENSIONS];
      node.position = {
        x: nodeWithPosition.x - dims.width / 2,
        y: nodeWithPosition.y - dims.height / 2,
      };
    }
  });

  return { nodes, edges };
}

export function getInitialExpandedState(hierarchy: ProjectHierarchy): string[] {
  const projectId = `project-${hierarchy.name}`;
  return [projectId];
}
