---
name: task-cron
schedule: "*/30 * * * 1-5"
timezone: America/Los_Angeles
runtime: claude-routines
fanout: none
---

# Routine — task-cron

> Pattern 10. The closed-loop heartbeat: tasks → cron → reminder. Overdue tasks DM the owner until they get handled. No "tracker no one opens."

## Task store

Default: a Notion database `Tasks` (see `docs/STACK_OVERRIDES.md` if you swap it for sqlite, Linear, or HubSpot tasks).

Required fields:

| Field | Type | Notes |
|---|---|---|
| `title` | text | Short verb phrase. |
| `owner_slack_id` | text | Pattern 13 — DM target. Never a channel. |
| `client_slug` | relation | Links to `clients/<slug>/`. |
| `due_at` | date | When it's due. |
| `status` | select | `open` / `in_progress` / `done` / `cancelled`. |
| `last_dm_at` | date | Set by this routine; throttle DMs to one per 24h. |

## Schedule

Every 30 minutes during business hours, weekdays. Cheap — Notion DB query + classify + maybe DM.

## Logic

```
for task in tasks where status in ('open','in_progress'):
  if task.due_at < now:
    days_late = (now - task.due_at).days
    if task.last_dm_at is None or (now - task.last_dm_at).hours >= 24:
      slack.dm(task.owner_slack_id,
               f"⚠ Overdue: {task.title} — {days_late} day(s) late.")
      task.last_dm_at = now
```

Pattern 10 exact: pressure escalates linearly with days-late. The bot doesn't shame, but it doesn't stop either.

## Stop conditions

- Task moves to `done` or `cancelled` → DMs stop.
- Owner sets `last_dm_at` manually to a future date (snooze) → DMs pause until then.
- Owner is on PTO (`agency_owners[*].pto_until` in `BRAND_GUIDELINES.md`) → reroute to deputy or pause.

## Eval gate

This routine is logic-heavy, not LLM-heavy — so it has a `tests/test_task_cron.py` unit-test gate instead of an `evals/` YAML. Both must pass before merge.

## Provenance

Writes a daily summary to `runs/<date>/task-cron-summary.md`: tasks DM'd, tasks closed, tasks snoozed.
