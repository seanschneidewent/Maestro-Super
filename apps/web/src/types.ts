export enum AppMode {
  SETUP = 'SETUP',
  USE = 'USE',
  LOGIN = 'LOGIN',
  DEMO = 'DEMO'
}

export enum FileType {
  PDF = 'pdf',
  CSV = 'csv',
  IMAGE = 'image',
  MODEL = 'model',
  FOLDER = 'folder'
}

export type ProjectStatus = 'setup' | 'processing' | 'ready';

export interface Project {
  id: string;
  name: string;
  status: ProjectStatus;
  createdAt: string;
  updatedAt?: string;
}

export interface ProjectFile {
  id: string;
  name: string;
  type: FileType;
  children?: ProjectFile[];
  parentId?: string;
  storagePath?: string; // Supabase Storage path
  pageCount?: number;
  pointerCount?: number; // Number of context pointers on this page
  category?: string; // For Use Mode grouping (e.g., "A-101")
  file?: File; // The actual file object for rendering (local only)
}

export interface OcrSpan {
  text: string;
  x: number;
  y: number;
  w: number;
  h: number;
  confidence: number;
}

export interface PointerReference {
  id: string;
  targetPageId: string;
  targetPageName: string;
  justification: string;
}

export interface ContextPointer {
  id: string;
  pageId: string;
  title: string;
  description: string;
  textSpans?: string[];
  ocrData?: OcrSpan[];  // Word-level OCR with positions for highlighting
  bboxX: number;
  bboxY: number;
  bboxWidth: number;
  bboxHeight: number;
  pngPath?: string;
  hasEmbedding?: boolean;
  references?: PointerReference[];
  isGenerating?: boolean;  // True while waiting for AI analysis
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'agent';
  text: string;
  timestamp: Date;
  referencedSheets?: {
    fileId: string;
    name: string;
    pointerCount: number;
  }[];
}

// Session types for query grouping
export interface Session {
  id: string;
  projectId: string;
  createdAt: string;
  updatedAt: string;
}

export interface QueryPage {
  id: string;
  pageId: string;
  pageOrder: number;
  pointersShown: { pointerId: string }[] | null;
  // Page details from join
  pageName?: string;
  filePath?: string;
  disciplineId?: string;
}

export interface QueryWithPages {
  id: string;
  sessionId: string | null;
  displayTitle: string | null;
  sequenceOrder: number | null;
  queryText: string;
  responseText: string | null;
  pages: QueryPage[];
  createdAt: string;
}

export interface SessionWithQueries extends Session {
  queries: QueryWithPages[];
}

// Hierarchy types for mind map visualization
export interface PointerSummary {
  id: string;
  title: string;
}

export interface PageInHierarchy {
  id: string;
  pageName: string;
  processedPass1: boolean;
  processedPass2: boolean;
  pointerCount: number;
  pointers: PointerSummary[];
}

export interface DisciplineInHierarchy {
  id: string;
  name: string;
  displayName: string;
  processed: boolean;
  pages: PageInHierarchy[];
}

export interface ProjectHierarchy {
  id: string;
  name: string;
  disciplines: DisciplineInHierarchy[];
}

// Agent streaming event types (from backend SSE)
export interface AgentTextEvent {
  type: 'text';
  content: string;
}

export interface AgentToolCallEvent {
  type: 'tool_call';
  tool: string;
  input: Record<string, unknown>;
}

export interface AgentToolResultEvent {
  type: 'tool_result';
  tool: string;
  result: Record<string, unknown>;
}

export interface AgentTraceStep {
  type: 'reasoning' | 'tool_call' | 'tool_result';
  content?: string;
  tool?: string;
  input?: Record<string, unknown>;
  result?: Record<string, unknown>;
}

export interface AgentDoneEvent {
  type: 'done';
  trace: AgentTraceStep[];
  usage: { inputTokens: number; outputTokens: number };
  displayTitle: string | null;
}

export interface AgentErrorEvent {
  type: 'error';
  message: string;
}

export type AgentEvent =
  | AgentTextEvent
  | AgentToolCallEvent
  | AgentToolResultEvent
  | AgentDoneEvent
  | AgentErrorEvent;

// Agent message state (built from events)
export interface ToolCallState {
  tool: string;
  input: Record<string, unknown>;
  result?: Record<string, unknown>;
  status: 'pending' | 'complete';
}

export interface PageVisit {
  pageId: string;
  pageName: string;
}

export interface AgentMessage {
  id: string;
  role: 'user' | 'agent';
  timestamp: Date;
  // User message
  text?: string;
  // Agent message (built incrementally from events)
  reasoning?: string[];
  toolCalls?: ToolCallState[];
  finalAnswer?: string;
  displayTitle?: string | null;
  trace?: AgentTraceStep[];
  pagesVisited?: PageVisit[];
  isComplete: boolean;
}

// Field Mode Types
export type FieldViewMode = 'standard' | 'response'

export interface FieldPointer {
  id: string
  label: string
  region: {
    bboxX: number      // 0-1 normalized
    bboxY: number      // 0-1 normalized
    bboxWidth: number  // 0-1 normalized
    bboxHeight: number // 0-1 normalized
  }
  answer: string
  evidence: {
    type: 'quote' | 'explanation'
    text: string
  }
}

export interface FieldPage {
  id: string
  pageNumber: number
  title: string
  pngDataUrl: string
  intro: string
  pointers: FieldPointer[]
}

export interface FieldResponse {
  id: string
  query: string
  summary: string
  displayTitle: string | null
  pages: FieldPage[]
}

// Tutorial types
export type TutorialStep = 'welcome' | 'sidebar' | 'viewer' | 'query' | 'new-session' | 'session-intro' | 'history' | 'complete' | null;
