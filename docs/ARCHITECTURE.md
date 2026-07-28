# Leo Card Motion architecture

- Authoring: category prompts + trending issues → Card IR JSON
- Composition: Hyperframes-style HTML (`data-start`, `data-duration`, clip classes)
- Preview: iframe player
- Render: `npx hyperframes render` when available; otherwise HTML preview primary on N100
- Deploy: Docker on `edge`, Caddy `handle_path /cards/*`
