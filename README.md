# gtm-agency-os-starter

Forkable starter template for a B2B GTM engineering agency. Encodes the 18-pattern GTM OS architecture as a single repo: doctrine, agents, evals, routines, per-client overrides.

**Read [`CLAUDE.md`](./CLAUDE.md) first.** Every session. Every contributor. No exceptions.

---

## Quick start

```bash
# 1. Clone and verify
git clone <this-repo> my-agency-os
cd my-agency-os
make verify          # runs CLAUDE.md self-check
make eval            # runs all agent evals against fixtures
# Both should exit 0 on a fresh clone.

# 2. Customize
$EDITOR BRAND_GUIDELINES.md           # your agency's voice
$EDITOR clients/_example/client.md    # rename to your first client
$EDITOR commands/ops.md               # your Slack channel + slash command names

# 3. Add a client
make new-client SLUG=acme

# 4. Wire up Slack
# See commands/ops.md for the slash command contract.

# 5. Schedule routines
# See routines/*.md — each file is a Claude Routines spec.
```

---

## What's in the repo

```
.
├── CLAUDE.md                  # master doctrine — overrides everything else
├── PLAN.md                    # 4-week rolling plan (Pattern 4)
├── BRAND_GUIDELINES.md        # voice card (Pattern 3)
├── AUDIT_REPORT_TEMPLATE.md   # quarterly audit fork target (Pattern 5)
├── Makefile                   # verify / eval / new-client targets
├── agents/                    # one file per agent role (Pattern 6)
├── evals/                     # one yaml per agent — required (Pattern 8)
├── commands/                  # Slack slash command specs (Pattern 2)
├── routines/                  # scheduled jobs (Pattern 11)
├── clients/                   # per-client doctrine overrides
├── docs/                      # PATTERNS.md, STACK_OVERRIDES.md
├── runs/                      # agent run artifacts (output of pipelines)
├── hooks/                     # pre-commit / pre-push (Pattern 15)
├── .github/workflows/         # CI eval gate (Pattern 16)
└── .claude-plugin/            # Claude Code plugin manifest
```

---

## The five layers (priority order)

| Layer | Where | Why |
|---|---|---|
| 1. Doctrine | `CLAUDE.md`, `PLAN.md`, `BRAND_GUIDELINES.md` | Single source of truth for "how we operate." |
| 2. Surfaces | `commands/`, `routines/` | Where humans interact. Slack-first. |
| 3. Agents | `agents/` | First-class. Own lifecycle, prompt, evals. |
| 4. Pipelines | `routines/per-client-*.md`, `agents/*-pipeline.md` | Multi-stage with named stages. |
| 5. Eval | `evals/`, `.github/workflows/eval-gate.yml` | Catches silent failures pre-merge. |

If a piece of work doesn't fit one of these, it doesn't belong here.

---

## Verification

`make verify` runs:

1. `CLAUDE.md` markdown parses.
2. All 5 layers still documented.
3. No banned marketing phrases in doctrine.
4. Provenance line present.

`make eval` runs every agent in `agents/` against its paired `evals/<agent>.yaml` fixtures, scores via Haiku-4-5 judge, fails on any below-threshold result.

CI runs both on every PR. Below-threshold blocks merge.

---

## License

MIT. See [`LICENSE`](./LICENSE) (add one before publishing the fork).

---

**Provenance:** kai8karma, 2026-05-09. Template version 0.1.
