# Atlas Web — Next.js Frontend

A React/TypeScript replacement for the legacy Plotly Dash UI. Built with
Next.js 15 (App Router), Tailwind CSS v4, and MapLibre GL JS. Speaks to
the FastAPI backend in [`src/atlas/api/`](../src/atlas/api).

## Quick start

```bash
# 1. Boot the FastAPI backend (Python side, port 8000)
uv sync --extra web
uv run atlas-api

# 2. In a separate terminal, boot Next.js (port 3000)
cd web
pnpm install
pnpm dev
```

Open <http://localhost:3000>.

`pnpm dev` proxies all `/api/*` calls to `http://localhost:8000` via the
rewrite in [`next.config.ts`](./next.config.ts). Override with
`ATLAS_API_ORIGIN` if the API runs elsewhere.

## Scripts

| Command | Purpose |
|---------|---------|
| `pnpm dev` | Start the Next.js dev server (port 3000) |
| `pnpm build` | Production build |
| `pnpm start` | Serve the production build |
| `pnpm typecheck` | Run `tsc --noEmit` |
| `pnpm lint` | Run `next lint` |
| `pnpm generate:types` | Regenerate `lib/api-types.ts` from the live `/openapi.json` (requires the API to be running) |

## Layout

The page mirrors the original Dash three-panel design:

```
┌─────────────────────────────────────────────────────────┐
│ Navbar                                                  │
├──────────┬─────────────────────────────┬───────────────┤
│ Chat     │ Itinerary                   │ Sidebar       │
│ (340px)  │ (flex)                      │ (320px)       │
│          │  · Flights / Accommodation  │  · Map        │
│ Messages │  · Day-by-day timeline      │  · Budget     │
│ + input  │                             │  · Stats      │
└──────────┴─────────────────────────────┴───────────────┘
```

## Design system

Tailwind v4 `@theme` tokens in [`app/globals.css`](./app/globals.css)
mirror [`.github/DESIGN.md`](../.github/DESIGN.md). Geist + Geist Mono
load via `next/font/google`. Activity-category colours live in
[`lib/categoryStyles.ts`](./lib/categoryStyles.ts) and match the legacy
Dash colour map exactly.

## State

[`lib/store.ts`](./lib/store.ts) holds a small Zustand store with the
session id (persisted to `localStorage`), chat history, itinerary, and
status bar text. The chat panel hydrates from the server on mount so a
page reload doesn't lose context.

## Map

[`react-map-gl/maplibre`](https://visgl.github.io/react-map-gl/) renders
the destination + activity pins. The default style is the public
`demotiles.maplibre.org` style — no API key required. Swap to
MapTiler/Stadia for production tiles.
