# gtm-agency-os-starter

Forkable starter for a B2B GTM engineering agency. Encodes the 18-pattern GTM OS architecture as a single repo: doctrine, agents, evals, routines, per-client overrides — and now an executable Python runtime that runs the agents, judges them, talks to Slack, and tracks tasks.

**Read [`CLAUDE.md`](./CLAUDE.md) first.** Every session. Every contributor. No exceptions.

---

## Quick start

```bash
# 1. Clone + install
git clone <this-repo> my-agency-os
cd my-agency-os
make install                 # creates .venv, installs gtmos in editable mode

# 2. Verify the doctrine + agent/eval pairing
make verify                  # CLAUDE.md self-checks
make eval                    # structural by default; judge mode if ANTHROPIC_API_KEY set
make test-cov                # pytest, fail-under 80% coverage
make security                # bandit + pip-audit + ruff (+ gitleaks if installed)

# 3. Customize
cp .env.example .env
$EDITOR .env                 # set ANTHROPIC_API_KEY, SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET
$EDITOR BRAND_GUIDELINES.md  # your agency's voice
make new-client SLUG=acme    # scaffold clients/acme/ from the template
$EDITOR clients/acme/client.md

# 4. Run something
gtmos verify                          # same as `make verify`
gtmos clients                         # list active clients
gtmos run-agent weekly-review --client acme --input '{"client":"acme"}'
gtmos tasks add --title "Send proposal" --owner U0KAI --client acme --due 2026-05-15T17:00:00-07:00
gtmos tasks overdue                   # plan overdue DMs (Pattern 10)
gtmos slack-app --port 3000           # serve Slack `/ops` handler

# 5. Schedule routines (cron / Claude Routines / systemd, your call)
gtmos routine per-client-weekly-review
gtmos routine task-cron
```

---

## What's in the repo

```
.
├── CLAUDE.md                  # master doctrine — overrides everything else
├── PLAN.md                    # 4-week rolling plan (Pattern 4)
├── BRAND_GUIDELINES.md        # voice card (Pattern 3)
├── AUDIT_REPORT_TEMPLATE.md   # quarterly audit fork target (Pattern 5)
├── SECURITY.md                # threat model + responsible disclosure
├── Makefile                   # verify / eval / test / security / new-client
├── pyproject.toml             # gtmos package metadata + dev deps
├── Dockerfile                 # non-root runtime image
├── gtmos/                     # executable runtime (Python, ≥3.11)
│   ├── config.py              # env loading + secret redaction filter
│   ├── security.py            # Slack signature, slug + path validation, redaction
│   ├── llm.py                 # Anthropic API wrapper (cached system prompt)
│   ├── agents.py              # agent loader + executor
│   ├── judge.py               # eval judge (real LLM call, structural fallback)
│   ├── runs.py                # path-validated run-artifact writer
│   ├── clients.py             # client.md frontmatter loader (Pydantic-validated)
│   ├── tasks.py               # sqlite task store + closed-loop cron (Pattern 10)
│   ├── routines.py            # routine dispatcher (per-client / per-owner / utility)
│   ├── slack_app.py           # Slack Bolt app, signature-verified
│   └── cli.py                 # `gtmos` command-line entrypoint
├── agents/                    # one file per agent role (Pattern 6)
├── evals/                     # one yaml per agent — required (Pattern 8)
├── commands/                  # Slack slash command specs (Pattern 2)
├── routines/                  # scheduled jobs (Pattern 11)
├── clients/                   # per-client doctrine overrides
├── docs/                      # PATTERNS.md, STACK_OVERRIDES.md
├── runs/                      # agent run artifacts (output of pipelines)
├── tests/                     # pytest — security, agents, judge, routines, CLI
├── hooks/                     # pre-commit / pre-push (Pattern 15)
└── .github/workflows/         # eval-gate + security CI gates
```

---

## The five layers (priority order)

| Layer | Where | Why |
|---|---|---|
| 1. Doctrine | `CLAUDE.md`, `PLAN.md`, `BRAND_GUIDELINES.md` | Single source of truth for "how we operate." |
| 2. Surfaces | `commands/`, `routines/`, `gtmos/slack_app.py` | Where humans interact. Slack-first. |
| 3. Agents | `agents/`, `gtmos/agents.py` | First-class. Own lifecycle, prompt, evals. |
| 4. Pipelines | `routines/per-client-*.md`, `gtmos/routines.py`, `gtmos/tasks.py` | Multi-stage with named stages. |
| 5. Eval | `evals/`, `gtmos/judge.py`, `.github/workflows/` | Catches silent failures pre-merge. |

If a piece of work doesn't fit one of these, it doesn't belong here.

---

## Verification + security gates

`make verify` — doctrine self-checks (CLAUDE.md format, agent ↔ eval pairing).

`make eval` — runs every agent against its `evals/<agent>.yaml` fixtures. Structural mode (offline) when no `ANTHROPIC_API_KEY` is set; real-judge mode when it is.

`make test` / `make test-cov` — pytest with coverage gate (≥ 80%).

`make security`:
- `bandit` static analysis on `gtmos/`
- `pip-audit` CVE scan of installed deps
- `ruff` lint (S/B/PT/SIM/PTH rules)
- `gitleaks` history scan if installed

CI runs all of these on every PR. See `SECURITY.md` for the threat model and responsible-disclosure flow.

---

## Stack assumptions

Defaults declared in `CLAUDE.md` § 4. Per-engagement overrides land in `docs/STACK_OVERRIDES.md`. The runtime currently wires:

- **Anthropic API** — agent execution + judge
- **Slack Bolt** — `/ops` slash command + bot DMs
- **sqlite** — default task store (Notion is a documented alternative)
- **Pydantic v2** — frontmatter validation
- **GitHub Actions** — eval-gate + security CI

---

## License

MIT. See [`LICENSE`](./LICENSE).

---

**Provenance:** kai8karma, template version 0.2.
