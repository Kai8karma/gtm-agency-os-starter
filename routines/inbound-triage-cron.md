---
name: inbound-triage-cron
schedule: "*/15 9-18 * * 1-5"
timezone: America/Los_Angeles
agent: agents/inbound-triage.md
runtime: claude-routines
fanout: per-thread
---

# Routine — inbound-triage-cron

> Pattern 12. Every 15 min during business hours. Classifies new inbound replies and routes per tier (Respond / Nurture / Wait / Skip).

## Inputs

- Lemlist inbox via Lemlist API (or per `docs/STACK_OVERRIDES.md`).
- LinkedIn inbox via configured connector (manual fallback if not wired).
- Slack inbound channel `#inbound-replies` (configurable per agency).

## Fan-out

One sub-run per new thread since last run. The routine maintains a `last_seen_thread_id` per source in `runs/.state/inbound-triage.json` so it doesn't re-classify.

## Routing (matches `agents/inbound-triage.md`)

- `Respond` → DM the campaign owner with draft reply context (high priority).
- `Nurture` → CRM tag + 30/60/90 re-touch. No DM.
- `Wait` → log + park. No DM.
- `Skip` → log + close. No DM.

## Confidence gate

If the agent returns confidence < 0.7, escalate via DM to the campaign owner with both top-tier candidates. The human decides; their decision is logged as a labeled fixture for future eval improvement.

## Eval gate

`make eval-inbound-triage` must pass before any change to `agents/inbound-triage.md` ships.

## Provenance

Each sub-run writes `clients/<slug>/runs/<date>-triage-<thread>.md` containing the reply text, classification, evidence, and routing action taken.
