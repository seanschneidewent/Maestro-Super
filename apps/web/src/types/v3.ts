export type V3ThinkingPanel = 'workspace_assembly' | 'learning' | 'knowledge_update'

export interface V3TokenEvent {
  type: 'token'
  content: string
}

export interface V3ThinkingEvent {
  type: 'thinking'
  panel: V3ThinkingPanel
  content: string
  turn_number?: number
}

export interface V3ToolCallEvent {
  type: 'tool_call'
  tool: string
  arguments: Record<string, unknown>
}

export interface V3ToolResultEvent {
  type: 'tool_result'
  tool: string
  result: Record<string, unknown> | Array<Record<string, unknown>>
}

export interface V3WorkspaceUpdateEvent {
  type: 'workspace_update'
  action: 'add_pages' | 'remove_pages' | 'highlight_pointers' | 'pin_page'
  workspace_state?: {
    displayed_pages: string[]
    highlighted_pointers: string[]
    pinned_pages: string[]
  }
  page_ids?: string[]
  pointer_ids?: string[]
  pages?: Array<{
    page_id: string
    page_name: string
    file_path: string
    discipline_id: string
  }>
  pointers?: Array<{
    pointer_id: string
    title: string
    page_id: string
    bbox_x: number
    bbox_y: number
    bbox_width: number
    bbox_height: number
  }>
  pinned_pages?: string[]
}

export interface V3DoneEvent {
  type: 'done'
}

export interface V3LearningDoneEvent {
  type: 'learning_done'
  turn_number?: number
}

export type V3Event =
  | V3TokenEvent
  | V3ThinkingEvent
  | V3ToolCallEvent
  | V3ToolResultEvent
  | V3WorkspaceUpdateEvent
  | V3DoneEvent
  | V3LearningDoneEvent

export interface V3WorkspaceState {
  displayed_pages: string[]
  highlighted_pointers: string[]
  pinned_pages: string[]
}
