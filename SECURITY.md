# Security Policy

## Supported versions

Security fixes are provided for the latest released minor version of Hyperframes Studio. The project is pre-release until `v0.1.0` is published.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting or a private security advisory for `suyaleo/Hyperframes_Studio`. Do not include credentials, private research data, unpublished media, or exploit details in a public issue.

Reports should include the affected version or commit, reproduction steps, impact, and any suggested mitigation. Receipt will be acknowledged as soon as practical and remediation status will be shared through the private advisory.

## Runtime secrets

Keep oMLX, MCP, law API, and other provider credentials in environment variables or an untracked `.env` file. Never embed them in projects, rendered media, Docker layers, or logs.
