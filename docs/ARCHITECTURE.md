# Hyperframes Studio architecture

## Runtime classification

Hyperframes Studio is a `local-api` Web application and a `docker-service` distribution. The browser alone is not the full product because research, model inference, persistent projects, narration, and video rendering require the FastAPI service.

## Current layers

- `web/`: Studio Design workspace with issue list, canvas, inspector, sequence strip, production panel, and complete light/dark theming.
- `api/`: FastAPI endpoints, trend ingestion, card composition, and render adapters.
- `remotion-template/`: React/Remotion renderer driven by project props.
- `studio.json`: canonical identity and release metadata.
- runtime data: projects, generated compositions, and output beneath the configured data directory (`/data` in Docker).

## Target data flow

```text
issue or keyword
  -> source-aware research bundle
  -> oMLX structured storyboard
  -> shared storyboard IR
  -> Hyperframes HTML + Remotion props
  -> narration/captions + rendered output
```

Provider URLs and credentials are runtime configuration. Docker connects to host services through `host.docker.internal`, never through a container-local `127.0.0.1` assumption.

## Discovery sources

- News RSS feeds provide time-sensitive issue discovery.
- `slavakurilyak/awesome-ai-agents` provides a runtime-fetched AI project catalog with explicit source attribution. It enriches research candidates but is not treated as a real-time GitHub ranking.
- Future MCP and oMLX research providers must retain evidence URLs and provider timestamps when they produce cards.
