---
slug: _example
name: Example Client Inc.
tier: pilot
team: [kai]
owner_slack_id: U0EXAMPLE0
pause: false
no_go_topics:
  - competitor names (do not mention by name in outbound)
  - pricing on cold outbound (defer to call)
voice_overrides:
  reading_level: 9th
  emoji_policy: none
  hedge_density_max: 0.5
tier_overrides:
  any_reply_mentioning_compliance: Respond
---

# Client — Example Client Inc. (`_example`)

> This is the template client. **Rename the directory** to your real client slug before running anything against it. The eval harness ignores `_example` because the slug starts with `_`.

## Engagement

- **Started:** 2026-05-09
- **Wave plan:** see `PLAN.md` § Wave 1.
- **Owner:** Kai (`U0EXAMPLE0`) — replace with the real Slack user ID.
- **Cadence:** weekly review (Mondays), quarterly audit (March / June / Sept / Dec).

## Stack (their side)

- CRM: HubSpot
- Outbound: Lemlist + Clay
- Surface: Slack workspace `example.slack.com`
- Repo: GitHub `example-org/example-revops`

Deviations from the template stack go in `docs/STACK_OVERRIDES.md`.

## Brand override

Fork `BRAND_GUIDELINES.md` only where the client's voice differs from the agency default. Leave everything else inheriting.

- **Banned phrases (additional):** "synergy partner", "force multiplier" — both flagged by the client's marketing lead in kickoff.
- **Sender persona:** First-name only in signatures. Full name only on first send.

## Active campaigns

See `clients/_example/campaigns/`. One file per campaign.

## Runs

`clients/_example/runs/<YYYY-MM-DD>-<routine>.md` — append-only.

---

**Provenance:** template default, kai8karma 2026-05-09. Replace this file content per real client.
