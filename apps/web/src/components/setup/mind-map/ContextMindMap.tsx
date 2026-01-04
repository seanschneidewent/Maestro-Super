import { useCallback, useMemo, useEffect, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
  NodeTypes,
  ReactFlowProvider,
  useReactFlow,
  ConnectionMode,
  useViewport,
} from 'reactflow';
import 'reactflow/dist/style.css';

import { ProjectNode, DisciplineNode, PageNode, PointerNode } from './nodes';
import { layoutHierarchy, getInitialExpandedState, ConnectionLine } from './layout';
import { useHierarchy, useInvalidateHierarchy } from '../../../hooks/useHierarchy';
import { MindMapSkeleton } from '../../ui/Skeleton';

// Custom SVG layer for connection lines
function ConnectionLinesLayer({ lines }: { lines: ConnectionLine[] }) {
  const { x, y, zoom } = useViewport();

  if (lines.length === 0) return null;

  return (
    <svg
      className="absolute inset-0 pointer-events-none"
      style={{ overflow: 'visible' }}
    >
      <g transform={`translate(${x}, ${y}) scale(${zoom})`}>
        {lines.map((line, i) => (
          <line
            key={i}
            x1={line.x1}
            y1={line.y1}
            x2={line.x2}
            y2={line.y2}
            stroke={line.color}
            strokeWidth={line.width / zoom}
            strokeLinecap="round"
          />
        ))}
      </g>
    </svg>
  );
}

// Register custom node types
const nodeTypes: NodeTypes = {
  project: ProjectNode,
  discipline: DisciplineNode,
  page: PageNode,
  pointer: PointerNode,
};

// Default edge options for floating bezier curves
const defaultEdgeOptions = {
  type: 'default',
  style: {
    strokeWidth: 2,
  },
};

interface ContextMindMapProps {
  projectId: string;
  activePageId?: string;
  onPageClick?: (pageId: string, disciplineId: string) => void;
  onPointerClick?: (pointerId: string, pageId: string, disciplineId: string) => void;
  onDisciplineClick?: (disciplineId: string) => void;
  refreshTrigger?: number;
  expandedNodes: string[];
  setExpandedNodes: (nodes: string[]) => void;
}

function ContextMindMapInner({
  projectId,
  activePageId,
  onPageClick,
  onPointerClick,
  onDisciplineClick,
  refreshTrigger,
  expandedNodes,
  setExpandedNodes,
}: ContextMindMapProps) {
  const { fitView } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [lines, setLines] = useState<ConnectionLine[]>([]);

  // Fetch hierarchy data
  const { data: hierarchy, isLoading, error, refetch } = useHierarchy(projectId);
  const invalidateHierarchy = useInvalidateHierarchy();

  // Refresh when trigger changes
  useEffect(() => {
    if (refreshTrigger !== undefined && refreshTrigger > 0) {
      invalidateHierarchy(projectId);
    }
  }, [refreshTrigger, projectId, invalidateHierarchy]);

  // Initialize expanded state when hierarchy first loads
  useEffect(() => {
    if (hierarchy && expandedNodes.length === 0) {
      const initial = getInitialExpandedState(hierarchy);
      setExpandedNodes(initial);
    }
  }, [hierarchy, expandedNodes.length, setExpandedNodes]);

  // Toggle node expansion
  const toggleExpanded = useCallback((nodeId: string) => {
    setExpandedNodes(
      expandedNodes.includes(nodeId)
        ? expandedNodes.filter(id => id !== nodeId)
        : [...expandedNodes, nodeId]
    );
  }, [expandedNodes, setExpandedNodes]);

  // Layout callbacks
  const callbacks = useMemo(() => ({
    onProjectExpand: () => {
      const projectId = hierarchy ? `project-${hierarchy.name}` : '';
      if (projectId) toggleExpanded(projectId);
    },
    onDisciplineClick: (id: string) => {
      onDisciplineClick?.(id);
    },
    onDisciplineExpand: (id: string) => {
      toggleExpanded(id);
    },
    onPageClick: (id: string, disciplineId: string) => {
      onPageClick?.(id, disciplineId);
    },
    onPageExpand: (id: string) => {
      toggleExpanded(id);
    },
    onPointerClick: (id: string, pageId: string, disciplineId: string) => {
      onPointerClick?.(id, pageId, disciplineId);
    },
  }), [hierarchy, toggleExpanded, onDisciplineClick, onPageClick, onPointerClick]);

  // Compute layout when hierarchy or expanded state changes
  useEffect(() => {
    if (!hierarchy) return;

    const expandedSet = new Set(expandedNodes);
    const { nodes: layoutNodes, edges: layoutEdges, lines: layoutLines } = layoutHierarchy(hierarchy, {
      expandedNodes: expandedSet,
      activePageId,
      callbacks,
    });

    setNodes(layoutNodes);
    setEdges(layoutEdges);
    setLines(layoutLines);

    // Fit view after layout updates
    setTimeout(() => {
      fitView({ padding: 0.3, duration: 300 });
    }, 50);
  }, [hierarchy, expandedNodes, activePageId, callbacks, setNodes, setEdges, fitView]);

  if (isLoading) {
    return <MindMapSkeleton />;
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-red-400 gap-3">
        <p>Failed to load project hierarchy</p>
        <button
          onClick={() => refetch()}
          className="px-4 py-2 text-sm bg-slate-700 hover:bg-slate-600 rounded-lg text-white transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!hierarchy || hierarchy.disciplines.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-2">
        <p className="text-sm">No disciplines uploaded yet.</p>
        <p className="text-xs">Upload files to see the project hierarchy.</p>
      </div>
    );
  }

  return (
    <div className="w-full h-full relative">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        defaultEdgeOptions={defaultEdgeOptions}
        connectionMode={ConnectionMode.Loose}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnScroll
        zoomOnScroll
        className="bg-transparent"
      >
        {/* Custom SVG lines layer - renders behind nodes */}
        <ConnectionLinesLayer lines={lines} />
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="#334155"
          className="opacity-30"
        />
        <Controls
          showZoom={true}
          showFitView={true}
          showInteractive={false}
          className="!bg-slate-800 !border-slate-700 !shadow-lg [&>button]:!bg-slate-800 [&>button]:!border-slate-700 [&>button]:!text-slate-400 [&>button:hover]:!bg-slate-700 [&>button:hover]:!text-white"
        />
      </ReactFlow>
    </div>
  );
}

// Wrap with provider
export function ContextMindMap(props: ContextMindMapProps) {
  return (
    <ReactFlowProvider>
      <ContextMindMapInner {...props} />
    </ReactFlowProvider>
  );
}
