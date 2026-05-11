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

# 4. Run something — pure agent (no integrations)
gtmos verify
gtmos clients
gtmos run-agent weekly-review --client acme --input '{"client":"acme"}'

# 5. Run something — REAL pipelines (HubSpot + Slack)
# weekly-review pulls actual engagement counts and deal movement from HubSpot,
# runs the agent against those numbers, and DMs the client owner.
gtmos pipeline weekly-review --client acme

# inbound-triage classifies a reply, writes a HubSpot activity,
# and routes per tier (Respond → DM, Nurture → note + task, Skip → log).
echo "Send a calendar link for Tuesday." | gtmos pipeline inbound-triage \
  --client acme \
  --from-email priya@northpoint.com \
  --from-name "Priya N." \
  --subject "Re: vendor consolidation"

# 6. Local closed-loop ops
gtmos tasks add --title "Send proposal" --owner U0KAI --client acme --due 2026-05-15T17:00:00-07:00
gtmos tasks overdue                   # plan overdue DMs (Pattern 10)
gtmos slack-app --port 3000           # serve Slack `/ops` handler

# 7. Schedule routines (cron / Claude Routines / systemd, your call)
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
│   ├── config.py              # env loading + capability gating + secret redactor
│   ├── security.py            # Slack signature, slug + path validation, redaction
│   ├── llm.py                 # Anthropic API wrapper (cached system prompt)
│   ├── agents.py              # agent loader + executor
│   ├── judge.py               # eval judge (real LLM call, structural fallback)
│   ├── runs.py                # path-validated run-artifact writer
│   ├── clients.py             # client.md frontmatter loader (Pydantic-validated)
│   ├── tasks.py               # sqlite task store + closed-loop cron (Pattern 10)
│   ├── routines.py            # routine dispatcher (per-client / per-owner / utility)
│   ├── slack_app.py           # Slack Bolt app, signature-verified
│   ├── cli.py                 # `gtmos` command-line entrypoint
│   ├── connectors/            # external-system clients
│   │   ├── base.py            #   HTTP base with retry + redacted error reporting
│   │   ├── hubspot.py         #   real HubSpot v3: search/log/note/task/engagement counts
│   │   ├── slack.py           #   Slack chat_postMessage + conversations_open
│   │   ├── lemlist.py         #   stub — wire per engagement
│   │   └── discovery.py       #   Apollo / Clay stubs — wire per engagement
│   └── pipelines/             # end-to-end ops loops (real CRM + Slack writes)
│       ├── weekly_review.py   #   HubSpot pull → agent → Slack DM (Pattern 11)
│       └── inbound_triage.py  #   reply → classify → CRM activity + Slack route (Pattern 12)
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

## What's wired vs. what's stubbed

The honest scope of v0.4:

| Connector | Status | Where |
|---|---|---|
| Anthropic | wired | `gtmos/llm.py` |
| HubSpot | **wired** (search contacts/deals, log email, create note + task, engagement counts) | `gtmos/connectors/hubspot.py` |
| Slack — receive | wired (signed `/ops` handler + signed webhook receiver) | `gtmos/slack_app.py`, `gtmos/webhooks.py` |
| Slack — send | **wired** (chat_postMessage, conversations_open) | `gtmos/connectors/slack.py` |
| Lemlist | **wired** (push, pause, resume, stop, replies, bounces, sender health) | `gtmos/connectors/lemlist.py` |
| Webhook receiver | **wired** (FastAPI, HMAC-verified Lemlist + Slack + HubSpot v3) | `gtmos/webhooks.py` |
| kai-brain bridge | **wired** (search, used, outcome, remember, voice_card) | `gtmos/brain.py` |
| Apollo | stub — `ConnectorUnavailable` | `gtmos/connectors/discovery.py` |
| Clay | stub — `ConnectorUnavailable` | `gtmos/connectors/discovery.py` |
| sqlite task store | wired (default) | `gtmos/tasks.py` |
| Multi-tenant runs / tasks / evals / secrets | **wired** | `gtmos/multi_tenant.py` |
| Skill bridge (queue + inline whitelist) | **wired** | `gtmos/skill_bridge.py` |

Pipelines that hit real systems end-to-end:

- `pipelines/weekly_review.py` — pulls HubSpot engagement counts + deals, runs the agent, DMs the owner.
- `pipelines/inbound_triage.py` — classifies a reply, writes a HubSpot activity, routes per tier (Pattern 12). Triggered by the Lemlist `emailsReplied` webhook dispatch.

Brain flywheel:

- `AgentExecutor` queries kai-brain before each LLM call, injects top-k recalled memories + (for voice-sensitive agents) the brain voice card.
- Outputs containing `[[brain.applied: #ID]]` markers get logged via `brain used`. Downstream `report_outcome(executor, run, "win|loss|neutral")` backfills the verdict so confidence + decay re-weight the next recall.
- Brain unavailable → pipelines proceed without the recall block; no hard dependency.

Smoke harness (gated on real creds):

```bash
GTMOS_HUBSPOT_SMOKE=1 HUBSPOT_PRIVATE_APP_TOKEN=... python scripts/hubspot_smoke.py
GTMOS_SLACK_SMOKE=1   SLACK_BOT_TOKEN=...  SLACK_SMOKE_CHANNEL=C... \
  python scripts/slack_smoke.py
```

Both write a smoke-test artifact and clean up after themselves.

Stubs fail closed at startup if the engagement requires them (`require=("apollo",)`). Implementing a stub means subclassing it and wiring the API calls — interface contracts are documented in each stub file.

## Stack assumptions

Defaults declared in `CLAUDE.md` § 4. Per-engagement overrides land in `docs/STACK_OVERRIDES.md`.

---

## License

MIT. See [`LICENSE`](./LICENSE).

---

**Provenance:** kai8karma, template version 0.4.
