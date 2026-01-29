# Maestro Mode Components

White-themed query interface for superintendents in the field. This is the primary interface where users ask questions and get answers from their construction documents.

## Structure

### Main Container
- **MaestroMode.tsx** — Main container orchestrating query input, feed display, history panel, and conversation management

### Input Components
- **HoldToTalk.tsx** — Voice input button (hold to record) + exports `QueryInput` for text input
- **SessionControls.tsx** — Session management controls (clear, settings)
- **SuggestedPrompts.tsx** — Pre-built query suggestions for new users

### Display Components
- **FeedViewer.tsx** — Main feed showing query results, pages, and answers as a scrollable timeline
- **MaestroText.tsx** — Styled text rendering with construction-aware formatting
- **ThinkingSection.tsx** — Expandable section showing agent reasoning
- **ReasoningTrace.tsx** — Detailed step-by-step trace of agent actions
- **ToolCallCard.tsx** — Card displaying individual tool calls in the trace
- **PlanViewer.tsx** — Displays execution plan with page thumbnails
- **PlansPanel.tsx** — Side panel showing multiple plans

### Page Display
- **PageViewer.tsx** — Full PDF page viewer with zoom/pan
- **PageList.tsx** — Grid of page thumbnails
- **PointerOverlay.tsx** — Draws context pointer bboxes on pages
- **PointerPopover.tsx** — Tooltip showing pointer details on hover
- **TextHighlightOverlay.tsx** — Highlights relevant text on pages
- **PagesVisitedBadges.tsx** — Badge showing which pages were consulted

### History & Navigation
- **QueryHistoryPanel.tsx** — Slide-out panel showing past queries in current session
- **ConversationIndicator.tsx** — Shows current conversation context
- **QueryStack.tsx** — Stack of active/recent queries
- **QueryBubbleStack.tsx** — Visual stack of query bubbles
- **ActiveQueryBubble.tsx** — Currently streaming query indicator
- **NewConversationButton.tsx** — Start fresh conversation
- **BackButton.tsx** — Navigation back

### Visual Feedback
- **AgentToastStack.tsx** — Stack of agent status toasts
- **AgentWorkingToast.tsx** — Toast showing agent is processing
- **ConstellationAnimation.tsx** — Background animation during loading
- **FileTreeCollapsed.tsx** — Compact file tree for reference

### Utilities
- **transformResponse.ts** — Transforms API responses for display (exports `transformAgentResponse`, `extractLatestThinking`)

## Data Flow

```
User types/speaks query
       │
       ▼
useQueryManager.submitQuery()
       │
       ▼
POST /query (with conversation_id if continuing)
       │
       ▼
Backend streams SSE events
       │
       ▼
useQueryManager processes stream:
  - 'thinking' → updates thinkingText
  - 'tool_call' → updates currentTool
  - 'tool_result' → updates selectedPages
  - 'response' → updates finalAnswer
       │
       ▼
FeedViewer renders feed items:
  - user-query → query bubble
  - pages → page thumbnails with pointers
  - text → markdown answer with trace
```

## Key Patterns

- **Multi-query support**: `useQueryManager` tracks up to 3 concurrent queries
- **SSE streaming**: Real-time updates via EventSource with automatic reconnection
- **Conversation context**: Queries within a conversation share history for follow-ups
- **Toast notifications**: Background queries show progress via `AgentToastStack`
- **Keyboard handling**: `useKeyboardHeight` adjusts layout for mobile keyboards
