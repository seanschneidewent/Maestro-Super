import { Node, Edge } from 'reactflow';

export type MindMapNodeType = 'project' | 'discipline' | 'page' | 'pointer' | 'detail';

// Processing status for pages
export type PageProcessingStatus = 'pending' | 'processing' | 'completed' | 'failed';

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
  animationKey?: string;
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
  animationKey?: string;
  // Brain Mode processing state
  processingStatus?: PageProcessingStatus;
  detailCount?: number;
}

export interface PointerNodeData {
  type: 'pointer';
  id: string;
  title: string;
  pageId: string;
  disciplineId: string;
  onClick: () => void;
  onDelete: () => void;
  animationKey?: string;
}

export interface DetailNodeData {
  type: 'detail';
  id: string;
  title: string;
  number: string | null;
  shows: string | null;
  materials: string[];
  dimensions: string[];
  notes: string | null;
  pageId: string;
  disciplineId: string;
  onClick: () => void;
  animationKey?: string;
  staggerIndex?: number; // For staggered animation (50ms delay per detail)
}

export type MindMapNodeData =
  | ProjectNodeData
  | DisciplineNodeData
  | PageNodeData
  | PointerNodeData
  | DetailNodeData;

export type MindMapNode = Node<MindMapNodeData> & { key?: string };
export type MindMapEdge = Edge;

export interface LayoutConfig {
  centerX: number;
  centerY: number;
  nodeSpacing: number;
}

export const DEFAULT_LAYOUT_CONFIG: LayoutConfig = {
  centerX: 0,
  centerY: 0,
  nodeSpacing: 60,
};

// Node dimensions for layout calculations
export const NODE_DIMENSIONS = {
  project: { width: 180, height: 60 },
  discipline: { width: 160, height: 52 },
  page: { width: 140, height: 44 },
  pointer: { width: 120, height: 36 },
  detail: { width: 160, height: 36 },
};
