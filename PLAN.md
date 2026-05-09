# PLAN — GTM Agency OS Starter

> Pattern 4: the plan moves with the code. Linear/Asana/Notion lose to a co-located plan every time.

**Owner:** kai8karma
**Horizon:** 4 weeks (rolling)
**Last updated:** 2026-05-09
**Review trigger:** every Monday `/ops digest` posts a diff of this file vs. last week.

---

## Wave 1 — Bootstrap (week 1, current)

Goal: a forkable repo where `make verify && make eval` exits 0 on a fresh clone.

- [x] `CLAUDE.md` doctrine (208 lines, 14 sections, all 5 layers documented)
- [x] Five reference agents with paired evals
- [x] `Makefile` with `verify` + `eval` + `new-client` targets
- [x] `.github/workflows/eval-gate.yml` blocking merge on eval failure
- [x] `clients/_example/` showing per-client doctrine override structure
- [x] Pre-push hook running scope-block + eval gate
- [ ] First fork validates the template on a real engagement (PENDING)

## Wave 2 — Per-client routines (week 2)

Goal: weekly review fires per client, DMs the right human, skips dormant accounts (Pattern 11).

- [ ] `routines/per-client-weekly-review.md` wired to Claude Routines
- [ ] Slack user ID resolver + backfill (Pattern 13)
- [ ] Per-client `runs/<date>.md` artifact written every run
- [ ] Eval fixture: dormant client → run skipped, no Slack noise

## Wave 3 — Closed-loop ops (weeks 3–4)

Goal: tasks → cron → reminder loop running for at least one client.

- [ ] Task store (Notion DB or sqlite) — Pattern 14
- [ ] Overdue task cron + DM to owner (Pattern 10)
- [ ] Tier-action inbound triage live (Pattern 12: Respond / Nurture / Wait / Skip)
- [ ] Sentry + Railway hooks installed (Pattern 16)

## Wave 4 — Eval depth (weeks 5–8)

Goal: every agent has 5+ fixtures, judge model rotation, regression baseline.

- [ ] Bump fixture count from 3 → 5+ per agent
- [ ] Add Opus judge alongside Haiku for high-stakes agents
- [ ] Baseline scores committed; PRs fail if score drops > 0.5
- [ ] Quarterly doctrine pruning ritual (Pattern 9)

---

## Open questions (resolve before promoting to a wave)

- Slack workspace per-engagement or shared agency workspace? Default: per-engagement, isolated tokens.
- Agent runtime: Claude Code CLI vs. Claude Agent SDK for production? Default: CLI for the team, SDK only when latency forces it.
- Notion vs. HubSpot as primary CRM data plane? Default: HubSpot if client already has it; Notion otherwise.

---

**Provenance:** kai8karma, 2026-05-09. Plan items reference patterns from `docs/PATTERNS.md`.
