# 02 — Frontend

**Path:** `frontend/` · **Stack:** React 19 + TypeScript, Vite 8, Tailwind 4, framer-motion,
react-markdown + remark-gfm · **Port:** 5173

The frontend is a single-screen, three-pane chat application. There is **no router** and **no
global store** — state lives in two hooks and is prop-drilled into three sibling panes. Styling
is predominantly **inline styles** with a small amount of global CSS; Tailwind is used sparingly.

## Layout

`src/App.tsx` is the whole shell — a flexbox row (`height: 100vh`) of three panes:

```
┌──────────┬───────────────────────────┬──────────┐
│ Sidebar  │        ChatArea           │ DataPanel│
│ (268px)  │        (flex: 1)          │  (276px) │
│ history  │  welcome / message list   │  files   │
│ + nav    │  + MessageInput footer    │  + usage │
└──────────┴───────────────────────────┴──────────┘
```

`App.tsx` wires two hooks and drills their return values into the panes:

- `useFiles()` → `{ files, uploadFile, removeFile, isUploading, totalUsed, totalCapacity }`
- `useChat(files)` → chat state + actions (receives `files` so message routing can resolve a
  target dataset)

`src/main.tsx` is a standard React 19 entry (`createRoot(...).render(<StrictMode><App/></StrictMode>)`).

## Components (`src/components/`)

| Component | Role |
|---|---|
| **Sidebar.tsx** | Left rail: brand header, "New Chat", chat History list with inline rename (Enter/blur commit, Esc cancel) and delete, static Notebooks/Datasets nav, user profile. framer-motion `AnimatePresence` for row transitions. |
| **ChatArea.tsx** | Center column: top bar (title + Share/Your Data/Upload), an animated welcome screen with `QuickActions` when the chat is empty, otherwise the mapped message list. Auto-scrolls on new messages; shows a typing indicator while loading. Footer renders `MessageInput` keyed on `chat.id`. |
| **MessageInput.tsx** | The composer (largest component). Auto-resizing textarea, Enter-to-send / Shift+Enter newline. A `+` "Attach" dropdown with File / EDA Agent / Market Research (others show a "Soon" badge). Selecting EDA/Market Research toggles a **mode chip**; active modes are passed to `onSend(text, [...modes])`. Keeps a `localStorage` recent-attachments list. |
| **QuickActions.tsx** | The 4-card grid on the welcome screen: **EDA**, **Market Research**, **Insight Builder**, **Causal Analysis**. Each calls `onFeature(featureId)`. |
| **DataPanel.tsx** | Right rail file manager: drag-and-drop + click dropzone (`.csv,.xlsx,.xls,.json,.parquet,.sql`), file list with type-colored icons/size/relative time/remove, and a storage-usage bar (`totalUsed` / `totalCapacity`). |

## Result renderers (`src/components/results/`)

Assistant messages carry a `kind` and `data` payload. `ChatMessage.tsx` dispatches on
`message.kind` to a dedicated renderer instead of plain markdown. Each renderer also defines
its own payload TypeScript interface (those richer types live in the component files, not in
`types/index.ts`).

| Renderer | `kind` | Renders |
|---|---|---|
| **EdaResult.tsx** | `eda` | Splits the markdown `response` on `[[PLOT:n]]` markers and interleaves plot images (data-URI PNGs). Suggested follow-up chips call `onFollowup(q)`. Shows a mock-mode banner when DIAL is unconfigured. |
| **MarketResearchResult.tsx** | `market_research` | Domain/row-count header, executive summary, key findings with source links, opportunities/risks grid, priority-coded recommendations, and the causal DAG via `DagView`. |
| **DagView.tsx** | — | Pure-SVG causal-DAG renderer. Computes a longest-path layered layout (with cycle guard), draws bezier edges with arrowheads colored by relationship (increases=green, decreases=red), collision-aware edge labels, node colors by type (external_factor vs dataset_variable). |
| **InsightsResult.tsx** | `insights` | Pipeline stat tiles (rows, candidates generated/after-triage, executed, validated), executive summary, and `InsightCard`s. Cards parse a leading `[Tag]` badge and a trailing outlier-trim note from the narrative; badges color-coded by trust tier. |
| **CausalResult.tsx** | `causal` | Composite full-report renderer: executive summary, DAG, causal-story markdown, confidence-coded key-driver cards, EDA plot highlights, embedded `InsightsResult`, priority-coded recommendations. |

## Hooks (`src/hooks/`)

### `useChat.ts` — core orchestration

Holds `chats`, `activeChatId`, `isLoading`, plus refs mapping local↔backend chat ids and
tracking active EDA sessions and the streaming `AbortController`. Base path is `/api`.

Key behaviors:

- **Optimistic local ids.** New chats get a `local-…` id immediately; a backend chat is
  created asynchronously via `POST /api/chats` and the returned id is remembered.
- **`sendMessage(content, modes)`** routes the message: if an EDA/Market-Research mode chip is
  active or a text-regex feature detector matches, it calls `executeFeature()`; otherwise it
  hits the streaming chat endpoint.
- **SSE chat streaming.** `POST /api/chats/{id}/messages` with `{content, fileContext, mode}`;
  reads the response body reader, buffers by newline, parses `data: ` lines, accumulates
  `delta` text, finalizes on the `done` event. On any error it falls back to **simulated
  streaming of hardcoded mock responses**, so the UI works with no backend.
- **`executeFeature(feature)`** dispatches per feature:
  - **EDA** → `POST /api/eda/analyze` (first run) then `POST /api/eda/ask` (follow-ups).
  - **Market Research** → `POST /api/market-research/analyze`.
  - **Causal** → `POST /api/causal/runs`, then **detached polling** of
    `GET /api/causal/runs/{id}` every 10s, patching a live progress message until
    completed/failed (deliberately does not lock the chat).
  - **Insight Builder** → downloads the file, re-uploads it to `POST /api/insight/datasets`,
    then `POST /api/insight/datasets/{session_id}/analyze`.
  - Results are written back with `patchMessage(..., {kind, data})` so the matching result
    component renders.
- Chat management: `renameChat` → `PATCH /api/chats/{id}`, `deleteChat` → `DELETE`, plus
  `newChat` and `sendEdaFollowup`.

### `useFiles.ts` — file management

Holds `files` and `isUploading`; base path `/api/files`. On mount it `GET /api/files` and
normalizes backend field names into the `UploadedFile` shape. `uploadFile` does a multipart
`POST /api/files/upload` (falling back to a local-only entry on failure); `removeFile` does an
optimistic removal + `DELETE`. `totalCapacity` is a hardcoded 10 GiB.

## Types (`src/types/index.ts`)

```ts
type AgentMode = 'eda' | 'market_research' | null
type FeatureId = 'eda' | 'market_research' | 'insight_builder' | 'causal_analysis'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  streaming?: boolean
  kind?: 'text' | 'eda' | 'market_research' | 'insights' | 'causal'  // structured render
  data?: unknown                                                      // payload for renderer
}

interface Chat { id: string; title: string; messages: Message[]; createdAt: Date }
interface UploadedFile {
  id: string; name: string; size: number
  type: 'csv' | 'excel' | 'json' | 'parquet' | 'sql' | 'other'
  uploadedAt: Date; context?: string
}
```

The `kind` / `data` pair is the mechanism that lets one chat stream render both plain markdown
and rich structured feature results.

## Build tooling & backend wiring

- **`vite.config.ts`** — `@vitejs/plugin-react` + `@tailwindcss/vite`, and a dev proxy:
  `server.proxy['/api'] → http://localhost:8001`. All hook calls use relative `/api/...`
  paths, so this proxy is the entire backend connection in development.
- **`package.json` scripts** — `dev` (vite), `build` (`tsc -b && vite build`), `lint`
  (`oxlint`), `preview`. Networking uses native `fetch` (axios is a dependency but unused).
- **Tailwind 4** via the Vite plugin (`@import "tailwindcss"` in `index.css`); no
  `tailwind.config.js`. Visual design is mostly inline-style driven.
- **TypeScript** uses project references (`tsconfig.app.json` for `src`, `tsconfig.node.json`
  for the Vite config). Linting is **oxlint** (not ESLint), configured in `.oxlintrc.json`.

## Notable design points

- **Graceful degradation is first-class** — every backend call has a local/mock fallback, so
  the UI renders fully without a running backend.
- **Two response modes** — plain markdown streaming (chat LLM) vs. structured JSON results
  rendered by dedicated `results/*` components, selected by `Message.kind`.
- **Long-running jobs differ** — Causal Analysis uses non-blocking detached polling with live
  progress; Insight Builder blocks with a wait message.
