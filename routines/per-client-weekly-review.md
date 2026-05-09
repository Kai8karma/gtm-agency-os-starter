---
name: per-client-weekly-review
schedule: "0 7 * * 1"
timezone: America/Los_Angeles
agent: agents/weekly-review.md
runtime: claude-routines
fanout: per-client
---

# Routine — per-client-weekly-review

> Pattern 11. Fires Mondays 07:00 local. One sub-run per client. Skips dormant clients.

## Inputs

- All directories under `clients/*/` matching `client.md` (each is one fan-out target).
- For each client: campaigns, runs, CRM signal (HubSpot MCP if wired).

## Fan-out

One sub-run per `clients/<slug>/`, parallel. Each sub-run reads its own `client.md` for the owner DM target + tier overrides.

## Skip conditions (Pattern 11)

A client is **skipped** (sub-run exits 0, no DM, logs to `runs/<date>/skipped.log`) when:

- `client.md` frontmatter has `pause: true`.
- No `clients/<slug>/campaigns/*.md` modified in the last 14 days.
- No `clients/<slug>/runs/*.md` written in the last 7 days.

Skips are logged but not announced. Pattern 13: don't ping owners about silence.

## Owner DM target

`owner_slack_id` from `client.md` frontmatter. If missing, the routine triggers the user-ID backfill flow (`commands/ops.md` § "Slack user ID resolution") and exits with a non-zero status code so CI catches the gap.

## Eval gate

`make eval-weekly-review` must pass before any change to `agents/weekly-review.md` ships.

## Provenance

Each sub-run writes `clients/<slug>/runs/<date>-weekly-review.md`.
