"""GTM Agency OS — executable runtime.

This package implements the runnable layer behind the doctrine in CLAUDE.md.
Public modules:

    config    — env loading + repo-root resolution
    security  — Slack signature verification, slug + path validation
    clients   — client.md frontmatter loader and validator
    agents    — agent.md loader + executor (calls Claude, writes run artifact)
    runs      — run-artifact writer (path-validated)
    tasks     — sqlite-backed task store + closed-loop cron
    judge     — eval judge (real Anthropic API call)
    routines  — routine loader + dispatcher
    slack_app — Slack Bolt app with signature-verified slash commands
    cli       — `gtmos run-agent`, `gtmos eval`, `gtmos task-cron`, …

Doctrine reference: CLAUDE.md, BRAND_GUIDELINES.md, docs/PATTERNS.md.
"""

from __future__ import annotations

__version__ = "0.3.0"
__all__ = ["__version__"]
