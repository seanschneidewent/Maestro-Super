// Re-export all types organized by domain

// App
export { AppMode } from './app';

// Project & Hierarchy
export {
  FileType,
  type ProjectStatus,
  type Project,
  type ProjectFile,
  type PointerSummary,
  type DetailSummary,
  type PageProcessingStatus,
  type PageInHierarchy,
  type DisciplineInHierarchy,
  type ProjectHierarchy,
} from './project';

// Pointers
export {
  type OcrSpan,
  type PointerReference,
  type ContextPointer,
} from './pointer';

// Queries & Agent
export {
  type ChatMessage,
  type Conversation,
  type QueryPage,
  type QueryWithPages,
  type ConversationWithQueries,
  type AgentTextEvent,
  type AgentToolCallEvent,
  type AgentToolResultEvent,
  type AgentTraceStep,
  type AgentDoneEvent,
  type AgentErrorEvent,
  type AgentEvent,
  type ToolCallState,
  type PageVisit,
  type AgentMessage,
} from './query';

// Field Mode
export {
  type FieldViewMode,
  type OcrWord,
  type FieldPointer,
  type FieldPage,
  type FieldResponse,
} from './field';

// Tutorial
export { type TutorialStep } from './tutorial';

// Mind Map
export {
  type MindMapNodeType,
  type ProjectNodeData,
  type DisciplineNodeData,
  type PageNodeData,
  type PointerNodeData,
  type DetailNodeData,
  type MindMapNodeData,
  type MindMapNode,
  type MindMapEdge,
  type LayoutConfig,
  DEFAULT_LAYOUT_CONFIG,
  NODE_DIMENSIONS,
} from './mind-map';
