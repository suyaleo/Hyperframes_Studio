# Hyperframes Studio

Hyperframes Studio turns a live issue or a user-supplied topic into evidence-backed HTML cards and rendered video. The current `0.1.0` work is being built in verified phases: release foundation first, then the Studio workspace, research orchestration, local oMLX generation, narration, and final rendering.

> Status: pre-release. The current card editor and render adapters are retained while the new AI workflow is built. Repository and container publication remain blocked until every release gate passes.

## Current capabilities

- RSS issue discovery with category filters
- AI trend discovery combines current news with the MIT-licensed [Awesome AI Agents](https://github.com/slavakurilyak/awesome-ai-agents) catalog; catalog dates and star counts are snapshot metadata, not real-time GitHub measurements
- Persistent research bundles with evidence URLs, retrieval timestamps, provider status, image-license warnings, and per-card citations
- oMLX 0.5.x structured-output storyboard generation with an explicitly labeled deterministic fallback when authentication or model configuration is unavailable
- Editable headline, bullet, chart, quote, and CTA cards
- Hyperframes-compatible HTML composition output
- Remotion, Hyperframes, Playwright, and FFmpeg render adapters
- FastAPI local Web service and Docker Compose packaging
- `/api/health` and `/api/version` runtime metadata
- Compact Studio workspace with issue list, media canvas, composition inspector, draggable card sequence, and inspectable render panel
- Persistent Light, Dark, and System themes with resolved-theme logo switching

## Interface scope

The creator workspace keeps a documented minimum width of 1024px. At 1180px it compresses the issue list and inspector while preserving the canvas and primary actions. Touch-first and narrow mobile editing are not part of the current desktop production scope.

## Planned workflow

1. Select a current issue or enter a topic.
2. Collect research with source provenance, including optional biomedical and Korean-law MCP providers.
3. Ask a local oMLX model for a structured storyboard.
4. Review cards, narration, images, citations, and timing in the Studio workspace.
5. export Hyperframes HTML or render a Remotion MP4 from the same storyboard data.

## Local development

Requirements: Python 3.12, `uv`, Node.js 22+, FFmpeg, and a Chromium-compatible render environment.

```bash
uv sync --locked
npm ci --prefix remotion-template
uv run uvicorn api.main:app --host 127.0.0.1 --port 8770
```

Open `http://127.0.0.1:8770` and check `http://127.0.0.1:8770/api/health`.

For native oMLX generation, set `OMLX_BASE_URL=http://127.0.0.1:8000/v1`, `OMLX_API_KEY`, and `OMLX_MODEL` in an untracked `.env`. Without them, research still works and storyboard generation produces a visibly labeled rule-based review draft.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

The service is available at `http://127.0.0.1:8770`. Persistent project and render data is stored in the `hyperframes-studio-data` volume. `OMLX_DOCKER_BASE_URL` defaults to `http://host.docker.internal:8000/v1`, while native execution continues to use `OMLX_BASE_URL`; credentials stay in the untracked `.env` file.

## Distribution channels

- Web: `local-api` — the browser UI requires the local FastAPI service.
- Docker: `docker-service` — the same source tree runs in Compose with persistent storage.
- GitHub Pages is not presented as the full product because AI, research, storage, and rendering require an API.

## Licensing

Original Hyperframes Studio code is licensed under Apache-2.0. Dependencies and external services keep their own terms; see `THIRD_PARTY_NOTICES.md`.

Remotion uses its own conditional license and is not covered by this repository's Apache-2.0 license. Review the Remotion license before commercial use or redistribution. Product names and logos are governed separately by `TRADEMARKS.md`.
