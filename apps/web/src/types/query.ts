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

// Conversation types for query grouping
export interface Conversation {
  id: string;
  projectId: string;
  title?: string | null;
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
  conversationId: string | null;
  displayTitle: string | null;
  sequenceOrder: number | null;
  queryText: string;
  responseText: string | null;
  pages: QueryPage[];
  createdAt: string;
}

export interface ConversationWithQueries extends Conversation {
  queries: QueryWithPages[];
}

// Agent streaming event types (from backend SSE)
export interface AgentTextEvent {
  type: 'text';
  content: string;
}

export interface AgentTokenEvent {
  type: 'token';
  content: string;
}

export interface AgentThinkingEvent {
  type: 'thinking';
  content: string;
  panel?: 'workspace_assembly' | 'learning' | 'knowledge_update';
  turn_number?: number;
}

export interface AgentToolCallEvent {
  type: 'tool_call';
  tool: string;
  input: Record<string, unknown>;
  arguments?: Record<string, unknown>;
}

export interface AgentToolResultEvent {
  type: 'tool_result';
  tool: string;
  result: Record<string, unknown>;
}

export interface AgentTraceStep {
  type: 'reasoning' | 'tool_call' | 'tool_result' | 'thinking' | 'code_execution' | 'code_result';
  content?: string;
  tool?: string;
  input?: Record<string, unknown>;
  result?: Record<string, unknown>;
  panel?: 'workspace_assembly' | 'learning' | 'knowledge_update';
}

export interface AnnotatedImage {
  imageBase64: string;
  mimeType: string;
}

export interface AgentDoneEvent {
  type: 'done';
  trace: AgentTraceStep[];
  usage: { inputTokens: number; outputTokens: number };
  displayTitle: string | null;
  conversationTitle?: string | null;
  conceptName?: string | null;
  summary?: string | null;
  findings?: AgentFinding[];
  crossReferences?: AgentCrossReference[];
  gaps?: string[];
}

export interface AgentErrorEvent {
  type: 'error';
  message: string;
}

export interface AgentWorkspaceUpdateEvent {
  type: 'workspace_update';
  action: 'add_pages' | 'remove_pages' | 'highlight_pointers' | 'pin_page' | string;
  page_ids?: string[];
  pointer_ids?: string[];
  pages?: Array<{
    page_id: string;
    page_name?: string;
    file_path?: string;
    discipline_id?: string;
  }>;
  pointers?: Array<{
    pointer_id: string;
    title?: string;
    page_id: string;
    bbox_x?: number;
    bbox_y?: number;
    bbox_width?: number;
    bbox_height?: number;
  }>;
  workspace_state?: {
    displayed_pages?: string[];
    highlighted_pointers?: string[];
    pinned_pages?: string[];
  } | null;
}

export interface AgentPageStateEvent {
  type: 'page_state';
  page_id: string;
  page_name?: string;
  state: 'queued' | 'processing' | 'done';
}

export interface AgentResponseUpdateEvent {
  type: 'response_update';
  text: string;
  version: number;
}

export interface AgentLearningEvent {
  type: 'learning';
  text: string;
  classification?: string;
  file_updated?: string;
}

export type AgentEvent =
  | AgentTokenEvent
  | AgentTextEvent
  | AgentThinkingEvent
  | AgentToolCallEvent
  | AgentToolResultEvent
  | AgentWorkspaceUpdateEvent
  | AgentDoneEvent
  | AgentErrorEvent
  | AgentPageStateEvent
  | AgentResponseUpdateEvent
  | AgentLearningEvent;

export interface AgentFinding {
  category: string;
  content: string;
  pageId: string;
  semanticRefs?: number[];
  bbox?: [number, number, number, number];
  confidence?: string;
  sourceText?: string;
  pageName?: string;
}

export interface AgentCrossReference {
  fromPage: string;
  toPage: string;
  relationship: string;
}

export interface AgentConceptResponse {
  conceptName?: string | null;
  summary?: string | null;
  findings?: AgentFinding[];
  crossReferences?: AgentCrossReference[];
  gaps?: string[];
}

export interface V3WorkspaceState {
  displayedPages: string[];
  highlightedPointers: string[];
  pinnedPages: string[];
}

export interface V3SessionSummary {
  sessionId: string;
  sessionType: 'workspace' | 'telegram';
  workspaceName: string | null;
  status?: string;
  lastActiveAt?: string | null;
  lastMessagePreview?: string | null;
}

export interface V3SessionDetails extends V3SessionSummary {
  workspaceState: V3WorkspaceState | null;
}

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
