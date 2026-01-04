import { Node, Edge } from 'reactflow';

export type MindMapNodeType = 'project' | 'discipline' | 'page' | 'pointer';

export interface ProjectNodeData {
  type: 'project';
  id: string;
  name: string;
  disciplineCount: number;
  onExpand: () => void;
  isExpanded: boolean;
}

export interface DisciplineNodeData {
  type: 'discipline';
  id: string;
  name: string;
  displayName: string;
  processed: boolean;
  pageCount: number;
  pointerCount: number;
  onExpand: () => void;
  onClick: () => void;
  isExpanded: boolean;
}

export interface PageNodeData {
  type: 'page';
  id: string;
  pageName: string;
  disciplineId: string;
  pointerCount: number;
  processedPass1: boolean;
  processedPass2: boolean;
  onExpand: () => void;
  onClick: () => void;
  isExpanded: boolean;
  isActive: boolean;
}

export interface PointerNodeData {
  type: 'pointer';
  id: string;
  title: string;
  pageId: string;
  disciplineId: string;
  onClick: () => void;
}

export type MindMapNodeData =
  | ProjectNodeData
  | DisciplineNodeData
  | PageNodeData
  | PointerNodeData;

export type MindMapNode = Node<MindMapNodeData>;
export type MindMapEdge = Edge;

export interface LayoutConfig {
  centerX: number;
  centerY: number;
  levelRadius: number[];  // Distance from center for each level
  nodeSpacing: number;
}

export const DEFAULT_LAYOUT_CONFIG: LayoutConfig = {
  centerX: 0,
  centerY: 0,
  levelRadius: [0, 180, 360, 520, 680],  // Project, Discipline, Page, Pointer
  nodeSpacing: 60,
};

// Node dimensions for layout calculations
export const NODE_DIMENSIONS = {
  project: { width: 180, height: 60 },
  discipline: { width: 160, height: 52 },
  page: { width: 140, height: 44 },
  pointer: { width: 120, height: 36 },
};
