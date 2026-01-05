import { useCallback, useMemo, useEffect, useRef } from 'react';
import ReactFlow, {
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
  NodeTypes,
  ReactFlowProvider,
  useReactFlow,
} from 'reactflow';
import 'reactflow/dist/style.css';

import { ProjectNode, DisciplineNode, PageNode, PointerNode } from './nodes';
import { layoutHierarchy, getInitialExpandedState } from './layout';
import { NODE_DIMENSIONS } from './types';
import { useHierarchy, useInvalidateHierarchy } from '../../../hooks/useHierarchy';
import { MindMapSkeleton } from '../../ui/Skeleton';

const nodeTypes: NodeTypes = {
  project: ProjectNode,
  discipline: DisciplineNode,
  page: PageNode,
  pointer: PointerNode,
};

interface ContextMindMapProps {
  projectId: string;
  activePageId?: string;
  onPageClick?: (pageId: string, disciplineId: string) => void;
  onPointerClick?: (pointerId: string, pageId: string, disciplineId: string) => void;
  onPointerDelete?: (pointerId: string) => void;
  onDisciplineClick?: (disciplineId: string) => void;
  refreshTrigger?: number;
  expandedNodes: string[];
  setExpandedNodes: (updater: string[] | ((prev: string[]) => string[])) => void;
  focusNodeId?: string | null;
  onFocusComplete?: () => void;
}

function ContextMindMapInner({
  projectId,
  activePageId,
  onPageClick,
  onPointerClick,
  onPointerDelete,
  onDisciplineClick,
  refreshTrigger,
  expandedNodes,
  setExpandedNodes,
  focusNodeId,
  onFocusComplete,
}: ContextMindMapProps) {
  const { fitView, getNode, setCenter } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const prevNodeCountRef = useRef(0);
  const prevFocusNodeIdRef = useRef<string | null>(null);

  const { data: hierarchy, isLoading, error, refetch } = useHierarchy(projectId);
  const invalidateHierarchy = useInvalidateHierarchy();

  useEffect(() => {
    if (refreshTrigger !== undefined && refreshTrigger > 0) {
      invalidateHierarchy(projectId);
    }
  }, [refreshTrigger, projectId, invalidateHierarchy]);

  useEffect(() => {
    if (hierarchy && expandedNodes.length === 0) {
      const initial = getInitialExpandedState(hierarchy);
      setExpandedNodes(initial);
    }
  }, [hierarchy, expandedNodes.length, setExpandedNodes]);

  const toggleExpanded = useCallback((nodeId: string) => {
    setExpandedNodes(prev =>
      prev.includes(nodeId)
        ? prev.filter(id => id !== nodeId)
        : [...prev, nodeId]
    );
  }, [setExpandedNodes]);

  // Store callbacks in a ref for stable identity - prevents unnecessary layout recalculations
  // This is critical for performance when the mind map has many nodes
  const callbacksRef = useRef({
    onProjectExpand: () => {},
    onDisciplineClick: (_id: string) => {},
    onDisciplineExpand: (_id: string) => {},
    onPageClick: (_id: string, _disciplineId: string) => {},
    onPageExpand: (_id: string) => {},
    onPointerClick: (_id: string, _pageId: string, _disciplineId: string) => {},
    onPointerDelete: (_id: string) => {},
  });

  // Update the ref with current callback implementations (runs every render but doesn't trigger effects)
  callbacksRef.current = {
    onProjectExpand: () => {
      const projectNodeId = hierarchy ? `project-${hierarchy.name}` : '';
      if (projectNodeId) toggleExpanded(projectNodeId);
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
    onPointerDelete: (id: string) => {
      onPointerDelete?.(id);
    },
  };

  // Create stable callbacks that delegate to the ref
  const callbacks = useMemo(() => ({
    onProjectExpand: () => callbacksRef.current.onProjectExpand(),
    onDisciplineClick: (id: string) => callbacksRef.current.onDisciplineClick(id),
    onDisciplineExpand: (id: string) => callbacksRef.current.onDisciplineExpand(id),
    onPageClick: (id: string, disciplineId: string) => callbacksRef.current.onPageClick(id, disciplineId),
    onPageExpand: (id: string) => callbacksRef.current.onPageExpand(id),
    onPointerClick: (id: string, pageId: string, disciplineId: string) => callbacksRef.current.onPointerClick(id, pageId, disciplineId),
    onPointerDelete: (id: string) => callbacksRef.current.onPointerDelete(id),
  }), []); // Empty deps - callbacks are stable, they delegate to ref

  useEffect(() => {
    if (!hierarchy) return;

    const expandedSet = new Set(expandedNodes);
    const { nodes: layoutNodes, edges: layoutEdges } = layoutHierarchy(hierarchy, {
      expandedNodes: expandedSet,
      activePageId,
      callbacks,
    });

    setNodes(layoutNodes);
    setEdges(layoutEdges);
  }, [hierarchy, expandedNodes, activePageId, callbacks, setNodes, setEdges]);

  // Separate useEffect for fitView - triggers after nodes are rendered
  useEffect(() => {
    if (nodes.length === 0) return;

    // Only fit view when node count changes (expansion/collapse)
    if (nodes.length !== prevNodeCountRef.current) {
      prevNodeCountRef.current = nodes.length;

      // Use double requestAnimationFrame + setTimeout for reliable fitView
      // First RAF: React commits, Second RAF: browser paints, then 200ms for ReactFlow layout
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          setTimeout(() => {
            fitView({ padding: 0.15, duration: 300, minZoom: 0.1, maxZoom: 1.5 });
          }, 200);
        });
      });
    }
  }, [nodes.length, fitView]);

  // Scroll to focused node (e.g., after creating a new pointer)
  useEffect(() => {
    if (!focusNodeId || focusNodeId === prevFocusNodeIdRef.current || nodes.length === 0) return;

    // Wait for Dagre layout to complete before scrolling
    const timeoutId = setTimeout(() => {
      const node = getNode(focusNodeId);
      if (node) {
        const dims = NODE_DIMENSIONS.pointer;
        setCenter(
          node.position.x + dims.width / 2,
          node.position.y + dims.height / 2,
          { zoom: 1.2, duration: 400 }
        );
        prevFocusNodeIdRef.current = focusNodeId;
        onFocusComplete?.();
      }
    }, 350);

    return () => clearTimeout(timeoutId);
  }, [focusNodeId, nodes, getNode, setCenter, onFocusComplete]);

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
    <div className="w-full h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnScroll={false}
        panOnDrag={true}
        zoomOnScroll={true}
        className="bg-transparent"
      >
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

export function ContextMindMap(props: ContextMindMapProps) {
  return (
    <ReactFlowProvider>
      <ContextMindMapInner {...props} />
    </ReactFlowProvider>
  );
}
