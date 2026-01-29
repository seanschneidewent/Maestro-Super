# Custom Hooks

React hooks for managing state, data fetching, and streaming across the application.

## Query Hooks

Hooks for handling user queries and AI responses.

### useQueryManager
Multi-query manager supporting concurrent background queries (up to 3 simultaneous).
- Tracks query state: `streaming` | `complete` | `error`
- Manages SSE stream connections with 90-second timeout
- Handles tool calls, thinking text, and final answers
- Links queries to toast notifications

### useFieldStream
Single-query stream handler (legacy, being replaced by useQueryManager).
- Simpler interface for one query at a time
- Auto-aborts previous query when new one starts
- Transforms agent responses for display

### useConversation
Conversation state management with explicit binding.
- `activeConversationId`: Current bound conversation (null = ready for new)
- Creates new conversations on first query
- Supports restoring from history
- Uses React Query for caching

### useAgentStream
Low-level SSE stream connection for agent queries.
- Sends queries to `/query` endpoint
- Provides `sendQuery`, `isStreaming`, `error`, `abort`
- Used internally by higher-level hooks

## Data Hooks

Hooks for fetching and caching project data.

### usePointers
Pointer data management for pages.
- `usePagePointers(pageId)`: Fetch pointers for a page
- `toContextPointer()`: Convert API response to component format
- Single source of truth for pointer data in Setup Mode

### useHierarchy
Project hierarchy data (disciplines → pages → pointers).
- `useHierarchy(projectId)`: Fetch full hierarchy tree
- `useInvalidateHierarchy()`: Invalidate cache after mutations
- `useOptimisticDeletePointer()`: Immediate UI feedback on delete

### useProcessingStream
Real-time processing progress via SSE.
- Tracks: `idle` | `pending` | `processing` | `completed` | `failed` | `paused`
- Reports current page, progress (current/total), completed pages
- Connects to `/projects/{id}/processing/stream`

## UI Hooks

Hooks for interface behavior.

### useKeyboardHeight
Mobile keyboard detection and layout adjustment.
- Returns current keyboard height
- Uses `visualViewport` API for accurate detection
- Essential for mobile input positioning

### useTutorial
Tutorial/onboarding state management.
- Tracks tutorial step progression
- Controls visibility of tutorial UI elements

### useGoogleDrivePicker
Google Drive file picker integration.
- Opens Google Picker for file selection
- Returns selected files for import to Brain Mode
