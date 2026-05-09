---
name: daily-digest
schedule: "0 7 * * 1-5"
timezone: America/Los_Angeles
agent: agents/daily-digest.md
runtime: claude-routines
fanout: per-owner
---

# Routine — daily-digest

Fires every weekday at 07:00 local. One run per agency owner. DMs the digest.

## Inputs (resolved at run time)

- Owner roster from `BRAND_GUIDELINES.md` frontmatter (`agency_owners` list) + per-client `owner_slack_id` fields in `clients/*/client.md`.
- Today's date (resolves `<YYYY-MM-DD>`).
- Yesterday's run artifacts: `clients/*/runs/<yesterday>*.md` and top-level `runs/<yesterday>/*.md`.
- Open + slipped + due-today tasks from the task store (Notion DB or sqlite — see `routines/task-cron.md`).

## Fan-out

One sub-run per owner, parallel. Each sub-run is independent; failure of one doesn't block the others.

## Stop conditions

- Owner has zero shipped + zero slipped + zero due-today + zero meetings + zero Respond-tier inbound → **don't send the DM** (no "nothing to report" filler).
- Owner is on PTO (frontmatter `pto_until: <date>`) → log skip, no DM.
- Slack rate limit hit → backoff, retry once, then log to `runs/<date>/daily-digest-errors.md` and DM the agency admin.

## Eval gate

Before deploying changes to `agents/daily-digest.md`, `make eval-daily-digest` must pass with score ≥ 8.0 against `evals/daily-digest.yaml`.

## Provenance

Each sub-run writes `runs/<date>/daily-digest-<owner>.md` containing the rendered DM text + send status + eval score.
