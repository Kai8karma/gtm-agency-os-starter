# GTM Agency OS — Master Doctrine

> **Read this first. Every session. Every agent. No exceptions.**
>
> This file is the master prompt that anchors every skill, command, routine, and agent in this repo. If something here conflicts with a SKILL.md or a routine spec, **this file wins** unless explicitly overridden in writing below.

**Author:** kai8karma (kaikarma.com)
**Template version:** 0.1 (May 2026)
**License:** MIT

---

## 1. What this OS is

A **GTM Agency Operating System** — a single repo that runs the day-to-day of a B2B GTM agency: outbound campaigns, per-client reviews, lead routing, internal briefings, eval discipline. Slack is the human surface. The repo is the brain.

Stripped to one sentence: **the team works inside Slack, the agents work inside this repo, the doctrine in this file binds them together.**

This is a **starter template**, not a finished product. It encodes 18 patterns from the [GTM OS Pattern Catalog](https://github.com/kai8karma) (5 layers: Doctrine, Surfaces, Agents, Pipelines, Eval) so that day-1 of any engagement starts with structure, not a blank repo.

---

## 2. Who this is for

- A **GTM Engineering agency** running outbound for B2B clients (Clay + Lemlist + LinkedIn + HubSpot or analogous stack).
- A **small senior team** (3–10 people) where every contributor can read code and ship without permission.
- An org that already has **Slack as their team hub** and wants Slack to also be their **OS interface**.

Not for: enterprise BD departments, solo operators, agencies running purely manual outbound.

---

## 3. The five layers (in priority order)

| Layer | What lives here | Why it's a layer |
|---|---|---|
| 1. **Doctrine** | This file. `PLAN.md`. `BRAND_GUIDELINES.md`. `AUDIT_REPORT_<DATE>.md`. | Single source of truth for "how we operate." Every contributor reads it. |
| 2. **Surfaces** | `commands/` (Slack slash commands). `routines/` (scheduled jobs). | The places humans interact with the OS. Slack-first. |
| 3. **Agents** | `agents/` (one file per role). | First-class layer. Each agent has its own lifecycle, prompt, and eval set. **Never** mix agent logic into surfaces. |
| 4. **Pipelines** | `routines/per-client-*.md`. `agents/*-pipeline.md`. | Multi-stage processes with named stages and quality gates. |
| 5. **Eval** | `evals/`. `.github/workflows/eval-gate.yml`. | Catches silent agent failures before they hit production. Non-negotiable. |

If a piece of work doesn't fit one of these five layers, **it doesn't belong in this repo.** Push back before adding a sixth layer.

---

## 4. Stack assumptions

This template assumes the following stack. Any deviation must be documented in `docs/STACK_OVERRIDES.md`.

- **Slack** — primary human interface. Slash commands (`/ops <action>`) and bot DMs.
- **Claude Code (CLI v2.1+)** — agent runtime. Skills under `.claude-plugin/`.
- **Claude Routines** — scheduled jobs. Replaces ad-hoc cron + n8n where possible.
- **n8n** — kept for legacy flows that don't migrate cleanly. Marked deprecated in `routines/`.
- **HubSpot or Notion** — CRM. Notion is the data plane for non-engineering surfaces.
- **Clay (Claygent + waterfalls + signals + triggers)** — outbound discovery layer.
- **Lemlist** — sequencing.
- **LinkedIn** — manual + tooling-augmented.
- **GitHub Actions or Husky** — CI / pre-push gate.
- **Sentry** — observability for any deployed service.
- **Railway or Vercel** — deploy.

Stack additions require a one-line entry in `PLAN.md` justifying the addition.

---

## 5. Operating principles

These five principles override personal preference. If you disagree with one, **write the disagreement in `PLAN.md` and resolve it before contributing**, don't just route around it.

1. **Ship > theorize.** Working code in the repo beats a perfect plan in Notion. Every PR ships at least one falsifiable artifact.
2. **One surface per concern.** Don't add a CRUD page if a Notion DB and a `/ops` command can do the same job. Surfaces are expensive.
3. **Doctrine > convention.** When in doubt, this file decides. When this file is silent, ask in `#ops-engineering` and update this file with the resolution.
4. **Evals from day one.** A new agent without an `evals/<agent>.yaml` file fails CI. No exceptions.
5. **Brand the work.** Every artifact (Slack message, doc, report) carries a one-line provenance: who/which-agent produced it and when.

---

## 6. Voice & tone

All agent outputs and all human-written prose follow the same voice rules. Customize `BRAND_GUIDELINES.md` per engagement.

- **Terse.** Short sentences. No hedging adverbs ("really", "very", "quite"). Cut filler.
- **Brain-native.** Reference memories, decisions, prior context. Cite by ID where the brain layer exists.
- **Decision-first.** Lead with the verdict. Justify after.
- **No emoji** in committed files. Slack messages may use emoji sparingly for status (✓ ✗ ⚠).
- **No marketing prose.** "World-class," "innovative," "cutting-edge" — strip on sight.

---

## 7. How agents behave when invoked

Every agent in this repo follows the same lifecycle:

1. **Read this file** at session start. Do not skip.
2. **Read the relevant `SKILL.md`** for the task.
3. **Pull context** — relevant memories, prior decisions, brand voice card if applicable.
4. **Plan first** for any non-trivial task (≥3 steps). State the plan, get explicit approval if user-invocable, then execute.
5. **Execute with verification** — every task ends with a falsifiable check (file exists, exit code 0, sqlite query returns expected row, eval passes).
6. **Log the outcome** to `runs/<date>/<agent>-<task>.md` so the eval harness can later judge whether the run was a win/loss.
7. **Never claim completion** without proof.

Agents that don't follow this lifecycle fail the eval gate.

---

## 8. The Slack interface contract

Slack is the surface. The repo is the brain. Contract:

- **One slash command per major action** — `/ops audit`, `/ops review <client>`, `/ops draft <campaign-type>`, `/ops digest`. Avoid `/crumbs-do-the-thing` style monoliths.
- **Bot DMs the human, not the channel,** when an action is owner-specific. Channel posts are reserved for shared status.
- **Every Slack output ends with provenance.** "Generated by `agents/weekly-review.md` at 2026-05-09T07:00. Eval: pass (8.4/10)."
- **No auto-publish without explicit approval.** All outbound copy, all client-facing messages — human reviews and approves before ship. PUBL-01 rule.

---

## 9. Per-client conventions

Each client gets a folder under `clients/<client-slug>/` containing:

- `client.md` — the doctrine override for that client (their brand, their tier definitions, their no-go topics).
- `campaigns/` — active campaign specs (one file per campaign).
- `runs/<date>.md` — outputs of routines run for this client.

Routines that operate across clients (e.g., per-client weekly review) take a `--client <slug>` argument and read the per-client doctrine override.

---

## 10. Eval discipline

Every agent file in `agents/` has a corresponding `evals/<agent>.yaml` file. Without it, the agent fails CI and cannot be invoked from `commands/` or `routines/`.

Eval files contain:

- **`fixtures:`** — 3+ representative input cases.
- **`rubric:`** — what "good" looks like (factual / voice-match / scope-discipline / verification-present).
- **`judge:`** — model + prompt for grading. Default: Haiku-4-5.
- **`pass_threshold:`** — minimum score (default 8.0/10).

CI runs `make eval` on every PR. Below-threshold agents block merge.

---

## 11. Anti-patterns (instant PR rejection)

- Inline LLM call inside a route handler or surface file. **Move to `agents/`.**
- New agent without `evals/<agent>.yaml`. **Add the eval, or don't add the agent.**
- Slack notification without provenance. **Add the one-liner footer.**
- Skill that overlaps an existing skill without a `Cousins` section explaining why both exist. **Merge or annotate.**
- Doctrine added without sunset criteria. **Doctrine that can't expire becomes dead weight.** Date the entry, set a review trigger.
- Mixing per-client logic into a generic agent. **Move client-specific config to `clients/<slug>/`.**

---

## 12. Customization points (what changes per engagement)

When this template is forked for a new agency client, **only these files change in week 1**:

1. `BRAND_GUIDELINES.md` — their brand colors, tone, banned phrases.
2. `clients/<client-slug>/client.md` — one file per active client, their doctrine override.
3. `agents/*` — keep the structure, swap prompts to match their voice + workflows.
4. `evals/*` — fixtures from their actual data (anonymized).
5. `commands/ops.md` — match their actual Slack channel naming + slash command preference.
6. `routines/per-client-weekly-review.md` — adjust schedule + recipient mapping.

Everything else (this doctrine, the 5-layer architecture, the eval gate, the Slack contract) stays. **The structure is the value.**

---

## 13. Verification (this file)

Run before merging any change to this `CLAUDE.md`:

```bash
# 1. File parses as valid markdown
mdl CLAUDE.md  # or: pandoc -f markdown CLAUDE.md -o /dev/null

# 2. All 5 layers are still present (Doctrine / Surfaces / Agents / Pipelines / Eval)
grep -E "^### .*(Doctrine|Surfaces|Agents|Pipelines|Eval)" CLAUDE.md | wc -l
# Expect: ≥5

# 3. No banned marketing phrases
grep -iE "world-class|cutting-edge|game-changing|revolutionary" CLAUDE.md && echo "FAIL" || echo "OK"

# 4. Provenance line is present
grep -E "^\\*\\*Author:\\*\\*" CLAUDE.md
```

If all four checks pass, the doctrine is shippable.

---

## 14. Bibliography (where the patterns came from)

This OS is informed by:

- The [GTM OS Pattern Catalog](./docs/PATTERNS.md) — 18 patterns from a production GTM platform, condensed in-repo.
- Hamel Husain on evals.
- Anthropic engineering on subagent fan-out and prompt caching discipline.
- Robin Faraj's `content-workflow` repo (closed-loop daily briefings).
- The Cowork plugin patterns observed in `claude-ads` and `toprank` (skills + MCP servers + install.sh).

Cite these explicitly when adopting new patterns. Memory > improvisation.

---

**Provenance:** kai8karma, 2026-05-09. This file is the master prompt for the `gtm-agency-os-starter` repo. All other files in this repo reference it.
