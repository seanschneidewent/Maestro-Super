# Frontend CLAUDE.md

React + TypeScript + Tailwind + Vite. Deployed to Vercel.

## Architecture

```
src/
├── App.tsx              # Root - auth state, mode switching, project loading
├── components/
│   ├── setup/           # Setup Mode (draw boxes, process, manage files)
│   │   ├── SetupMode.tsx
│   │   ├── PdfViewer.tsx
│   │   ├── context-panel/   # Pointer details, page context, discipline view
│   │   └── mind-map/        # Visual representation of project structure
│   ├── use/             # Use Mode (query interface, field mode)
│   │   ├── UseMode.tsx
│   │   ├── FeedViewer.tsx
│   │   ├── PlanViewer.tsx
│   │   └── ReasoningTrace.tsx
│   ├── ui/              # Shared UI components (Toast, Skeleton, etc.)
│   └── tutorial/        # Onboarding overlay
├── contexts/            # React contexts (AgentToast, etc.)
├── hooks/               # Custom hooks
├── lib/
│   ├── api.ts           # Backend API client
│   ├── supabase.ts      # Supabase client + auth helpers
│   └── queryClient.ts   # React Query config
├── services/            # Service layer
└── types.ts             # Shared TypeScript types
```

## Modes

- **LOGIN** — Auth screen (email/password, Google OAuth)
- **DEMO** — Anonymous user viewing demo project (read-only)
- **SETUP** — Authenticated user managing project (upload, draw boxes, process)
- **USE** — Authenticated user querying (voice input, chat, view responses)

Mode state lives in `App.tsx`. Both SetupMode and UseMode render simultaneously (hidden/shown) to preserve state when switching.

## Key Components

| Component | Purpose |
|-----------|---------|
| `SetupMode` | File tree, PDF viewer, pointer drawing, processing controls |
| `UseMode` | Voice input, chat interface, agent responses |
| `PdfViewer` | PDF.js wrapper with pan/zoom, canvas overlay for drawing |
| `ContextPanel` | Shows pointer details, page context, discipline rollups |
| `FeedViewer` | Displays agent response stream with tool calls |

## State Management

- **React Query** for server state (projects, files, pointers)
- **Local state** for UI (selected file, drawing mode, expanded nodes)
- **Refs** for preserving state across mode switches (`localFileMapRef`, `setupState`)

## Patterns

- Glass morphism UI (`glass-panel` class)
- Dark theme with cyan accents
- Tailwind for all styling (no CSS files)
- `lucide-react` for icons
- Optimistic updates where possible

## API Client

All backend calls go through `lib/api.ts`. Uses fetch with Supabase auth token.

```typescript
// Example
const projects = await api.projects.list();
const response = await api.queries.stream(projectId, query);
```

## Development

```bash
pnpm install
pnpm dev          # http://localhost:5173
pnpm build        # Production build
pnpm preview      # Preview production build
```

## Environment Variables

```bash
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
VITE_API_URL=http://localhost:8000
VITE_DEMO_PROJECT_ID=          # For anonymous demo mode
```

## Current State

**Working:**
- Auth flow (anonymous → login → authenticated)
- PDF viewer with pan/zoom
- Pointer drawing and display
- Mode toggle (Setup ↔ Use)
- Voice input in Use Mode
- Session-based conversation history

**Current Focus:**
- Agent response display optimization
- Reducing perceived latency
- Mobile responsiveness for field use
