# Pattern catalog — 18 patterns from GTM OS

> Source-of-truth condensation of the GTM OS Pattern Catalog (`~/kai-brain/refs/gtm-os-architecture.md`). This file is the authoritative pattern list inside the repo. Updates here ship via PR.

---

## Layer 1 — Doctrine (1, 4, 5, 9)

### Pattern 1 — Doctrine document as the OS root
A single canonical file (e.g., `CLAUDE.md`) at the repo root. Every contributor (human or agent) reads it before acting.
- **Anti-pattern:** rules distributed across Notion / Slack / wikis where no one reads them.
- **In this repo:** `CLAUDE.md`.

### Pattern 4 — Plan document as source of truth
`PLAN.md` at root. Plan moves with code. Linear/Asana lose.
- **Anti-pattern:** roadmap in a tool only PMs read.
- **In this repo:** `PLAN.md`.

### Pattern 5 — Audit reports as committed documents
Point-in-time audits (e.g., `AUDIT_REPORT_<DATE>.md`) committed as artifacts. State assessments age in place; future-you can diff them.
- **Anti-pattern:** audit findings in a Slack thread.
- **In this repo:** `AUDIT_REPORT_TEMPLATE.md` + `agents/audit-mapper.md`.

### Pattern 9 — Doctrine removal as a first-class action
Commits explicitly **remove** stale doctrine. Same review weight as adding it.
- **Anti-pattern:** every PR adds rules; nothing ever leaves.
- **In this repo:** quarterly doctrine pruning (`PLAN.md` Wave 4).

---

## Layer 2 — Surfaces (2, 3, 14)

### Pattern 2 — Multi-surface ops decomposition
Separate surfaces for designops, mktops, salesops, business-case, tools. Each surface is its own opinionated workflow.
- **Anti-pattern:** "unified workspace" = generic kanban with custom fields.
- **In this repo:** `commands/ops.md` defines distinct subcommands per concern.

### Pattern 3 — Brand layer embedded in repo
`BRAND_GUIDELINES.md` lives next to the code. Brand = code.
- **Anti-pattern:** brand drift because guidelines live in a deck.
- **In this repo:** `BRAND_GUIDELINES.md` + per-client overrides in `clients/<slug>/client.md`.

### Pattern 14 — Notion DB provisioning for non-engineering surfaces
When a surface needs structured data managed by non-engineers, provision a Notion DB programmatically.
- **Anti-pattern:** bespoke admin UIs for every team's structured data.
- **In this repo:** `routines/task-cron.md` (default Notion-backed task store).

---

## Layer 3 — Agents (6, 7, 8)

### Pattern 6 — Agent layer separated from app layer
Dedicated `agents/` folder. Agents are first-class — own lifecycle, deployment cadence, tests.
- **Anti-pattern:** LLM calls inline in route handlers.
- **In this repo:** `agents/*.md`, one file per role.

### Pattern 7 — Multi-stage AI pipeline as a service
AI layer as a separate service with explicit named stages. Scales independently.
- **Anti-pattern:** AI calls baked into the same Node process as the UI.
- **In this repo:** `agents/campaign-drafter.md` is a pipeline stage; downstream stages are called via routine fan-out.

### Pattern 8 — Eval harness for agent reliability
Explicit harness designed to "catch silent agent failures." Tests run agents against fixtures + a judge model.
- **Anti-pattern:** prompts without tests.
- **In this repo:** `evals/<agent>.yaml` per agent. CI gates merges (`.github/workflows/eval-gate.yml`).

---

## Layer 4 — Pipelines (10, 11, 12, 13)

### Pattern 10 — Closed-loop task → cron → reminder
Tasks have due dates. Cron checks for overdue. Overdue tasks DM the owner on Slack.
- **Anti-pattern:** task list no one opens.
- **In this repo:** `routines/task-cron.md`.

### Pattern 11 — Pipeline health check cron, scoped per org
Cron jobs scoped per customer/account. Skip when no signal exists.
- **Anti-pattern:** monolithic cron drowning real signals.
- **In this repo:** `routines/per-client-weekly-review.md` with skip conditions.

### Pattern 12 — Tier nomenclature that's action-oriented
Tiers named for the action they imply (Respond / Nurture / Wait / Skip), not generic numeric.
- **Anti-pattern:** T1/T2/T3/T4 — every team member learns the lookup.
- **In this repo:** `agents/inbound-triage.md`.

### Pattern 13 — Slack user ID resolution + backfill
DMs target specific humans, not channels. Script proactively resolves Slack user IDs and backfills the database.
- **Anti-pattern:** every notification → `@channel` → blindness within a week.
- **In this repo:** `commands/ops.md` § "Slack user ID resolution"; `client.md` `owner_slack_id` field.

---

## Layer 5 — Eval + DX (15, 16, 17, 18)

### Pattern 15 — Hooks-first DX (pre-tool, pre-commit, pre-push)
Hooks enforcing scope blocks, formatting, security checks, and quality gates. Discipline codified, not optional.
- **Anti-pattern:** code review as the only quality gate.
- **In this repo:** `hooks/pre-commit`, `hooks/pre-push`.

### Pattern 16 — Three-piece infra discipline (Sentry + Railway + Husky)
Observability + deploy + pre-push. Each one's table stakes; missing any one is a tell.
- **Anti-pattern:** any one of the three missing.
- **In this repo:** `.github/workflows/eval-gate.yml` (CI gate), `docs/STACK_OVERRIDES.md` for Sentry/deploy override per engagement.

### Pattern 17 — Wave-based shipping cadence
Releases are named eras ("Wave 2.5"). Each wave has a charter and a date.
- **Anti-pattern:** continuous trickle deploys with no narrative.
- **In this repo:** `PLAN.md` is wave-structured.

### Pattern 18 — Bitscale grids for outbound discovery
Bitscale grids configured per ICP / signal type. 6+ priority grids minimum.
- **Anti-pattern:** "let's just pull a Sales Nav list" without grid governance.
- **In this repo:** referenced in campaign briefs (`clients/<slug>/campaigns/*.md`) when discovery is grid-driven.

---

## Quick-reference table

| Pattern | Layer | File(s) in this repo |
|---|---|---|
| 1 | Doctrine | `CLAUDE.md` |
| 2 | Surfaces | `commands/ops.md` |
| 3 | Surfaces | `BRAND_GUIDELINES.md` |
| 4 | Doctrine | `PLAN.md` |
| 5 | Doctrine | `AUDIT_REPORT_TEMPLATE.md`, `agents/audit-mapper.md` |
| 6 | Agents | `agents/*.md` |
| 7 | Agents | `agents/campaign-drafter.md` (pipeline stage) |
| 8 | Eval | `evals/*.yaml`, `.github/workflows/eval-gate.yml` |
| 9 | Doctrine | `PLAN.md` Wave 4 |
| 10 | Pipelines | `routines/task-cron.md` |
| 11 | Pipelines | `routines/per-client-weekly-review.md` |
| 12 | Pipelines | `agents/inbound-triage.md` |
| 13 | Pipelines | `commands/ops.md` § Slack ID resolution |
| 14 | Surfaces | `routines/task-cron.md` (Notion default) |
| 15 | Eval | `hooks/pre-commit`, `hooks/pre-push` |
| 16 | Eval | `.github/workflows/eval-gate.yml` |
| 17 | Eval | `PLAN.md` |
| 18 | Pipelines | `clients/<slug>/campaigns/*.md` |

---

**Provenance:** condensed from `~/kai-brain/refs/gtm-os-architecture.md`. kai8karma 2026-05-09.
