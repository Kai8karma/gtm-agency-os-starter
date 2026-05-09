"""GTM Agency OS — executable runtime.

This package implements the runnable layer behind the doctrine in CLAUDE.md.
Public modules:

    config        — env loading + repo-root resolution
    security      — Slack signature verification, slug + path validation
    clients       — client.md frontmatter loader and validator
    agents        — agent.md loader + executor (calls Claude, writes run artifact)
    brain         — kai-brain CLI bridge (recall, used, outcome, remember)
    runs          — run-artifact writer (path-validated)
    tasks         — sqlite-backed task store + closed-loop cron
    judge         — eval judge (real Anthropic API call)
    routines      — routine loader + dispatcher
    pipelines     — inbound triage + weekly review (real CRM/sequencer ops)
    connectors    — HubSpot, Slack, Lemlist real clients (HMAC + auth + retry)
    webhooks      — FastAPI receiver: Lemlist/Slack/HubSpot HMAC-verified ingress
    multi_tenant  — per-client task DBs, eval overrides, secret layering
    skill_bridge  — queue/run installed Claude Code skills as connectors
    slack_app     — Slack Bolt app with signature-verified slash commands
    cli           — `gtmos run-agent`, `gtmos eval`, `gtmos task-cron`, …

Doctrine reference: CLAUDE.md, BRAND_GUIDELINES.md, docs/PATTERNS.md.
"""

from __future__ import annotations

__version__ = "0.4.0"
__all__ = ["__version__"]
