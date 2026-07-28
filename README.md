# Leo Card Motion

Hyperframes-first card video studio for Leo Timeline Home Lab.

- Live: `https://leotimeline.synology.me/cards/`
- Ubuntu: `/opt/apps/leo-card-motion`
- Stack: FastAPI + Hyperframes HTML compositions + Playwright fallback + FFmpeg
- Design: Grok Creative Tool style dark studio

## Features
- Rising-issue RSS feed (category chips)
- Card slide board (headline / bullets / chart / quote / CTA)
- WYSIWYG card editor + reorder
- In-app HTML preview + MP4 render
- Default engine: **Hyperframes** (Playwright/Remotion adapter fallback)
- Timeline push → storyboard resource + deep link `/cards/?project=<id>`

## Local
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd api && uvicorn main:app --host 0.0.0.0 --port 8770
```

## Docker (Home Lab)
```bash
cp .env.example .env   # set LT_TIMELINE_TOKEN
docker compose up -d --build
# Caddy: handle_path /cards/* -> leo-card-motion-web:8770
```

## Render engines
| Engine | Role |
|---|---|
| hyperframes | default real render |
| playwright | HTML record fallback |
| remotion | special-template adapter export + kinetic capture |
| ffmpeg-slate | last-resort placeholder |
