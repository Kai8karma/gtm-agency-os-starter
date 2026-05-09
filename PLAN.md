# PLAN — Real GTM OS

> Pattern 4: the plan moves with the code. v0.3 reality: doctrine + runtime + 2 narrow pipelines, ~25% of surface, 0% verified against production systems. This file rewrites the plan to hit a real GTM OS — closed-loop ops, outcome flywheel, multi-tenant.

**Owner:** kai8karma · **Last revised:** 2026-05-09 · **Cadence:** review weekly Monday morning, rewrite quarterly.

---

## v0.3 honest grade

| Layer | Status |
|---|---|
| Doctrine + agent specs + eval harness | real, validated |
| `gtmos/` runtime (config, security, runs, executor, judge) | real, tested 195 unit tests, 80% cov |
| HubSpot connector | written against v3 spec, **never run against a real portal** |
| Slack send/receive | written, never run against a real bot |
| `pipelines/inbound-triage` + `pipelines/weekly-review` | wired but unproven; one-shot CLI only |
| **Lemlist (the actual sequencer)** | stub |
| **Webhook receivers (real-time path)** | nothing |
| **Outcome tracking (the moat)** | nothing |
| **Deliverability monitoring** | nothing |
| **Per-client isolation** | partial — single config namespace |
| **Reporting (client-facing artifact)** | nothing |
| **Signal ingestion (the prospecting input)** | nothing |

A real GTM OS = closed loop per client (discover → enrich → sequence → triage → handoff → close → learn). Each stage moves real state in real systems. The moat is the data plane + outcome flywheel, not the prompts.

---

## Architecture (three planes)

**Data plane** — unified prospect state.
- HubSpot is system of record; everything writes back.
- `kai-crm.db` is the local mirror for fast reads + outcome attribution.
- Every prospect: identity, signal trail, touch history, sequence state, deal stage, outcome label.

**Control plane** — pipelines + agents.
- Webhook receivers (Lemlist, Slack, Calendly, HubSpot, Common Room) — not polling.
- Background worker queue (Railway/Cloudflare Worker) for long-running jobs.
- Pipelines orchestrate; agents run inside pipelines, not standalone.
- Every agent run logs `(decision, context, outcome-tbd)` to `kai-brain`.

**Surface plane** — humans.
- Slack: `/ops`, ✓/✗ reactions for approval, DMs for action items.
- Per-client weekly report (PDF or Notion page) auto-generated.
- Per-agency cross-client dashboard for capacity + deliverability + spend.

---

## Integration scope

| System | Why | Effort |
|---|---|---|
| HubSpot v3 | CRM system of record | drafted; needs real-portal verification |
| Slack send + Block Kit + reactions | approval UX, DMs, daily digest | send drafted; reactions/Block Kit pending |
| **Lemlist API + webhooks** | sequencer + reply receiver + bounce monitor | stub today; **highest single-PR leverage** |
| Clay Claygent + waterfalls | enrichment + verification | webhook-only (Clay does the work) |
| Common Room / RB2B | website signal + person identification | webhook receiver |
| Calendly / Cal.com | meeting bookings → CRM auto-update | webhook receiver |
| LinkedIn (via Clay or manual queue) | second-channel touches | manual queue + state tracking |
| Crunchbase / Exa / Apify | funding + RFP signals | scheduled polling |
| kai-brain | outcome flywheel + voice fingerprint + recall | API call from every agent + outcome write |

---

## Sprint sequence (8 sprints, ~3–4 months calendar solo)

### Sprint 1 — Verify what's drafted (week 1)
**Goal:** the "wired" connectors are actually wired.
- `make hubspot-smoke` against a real dev portal: create test contact → log email → create note → create task → delete. Verify association IDs (198/202/204) and property names match.
- `make slack-smoke` against a real bot in a sandbox workspace: post message + open DM + close.
- Patch any spec-vs-reality gaps surfaced by the smoke tests.
- **Acceptance:** both smoke tests exit 0 in CI gated on secrets.

### Sprint 2 — Lemlist + webhook receiver (week 2) ★ highest leverage
**Goal:** inbound replies trigger triage in real time.
- Replace `connectors/lemlist.py` stub with real client (push prospect to sequence, list recent replies, pause on reply, list bounces).
- Stand up an HTTPS webhook receiver (Railway or Cloudflare Worker, Python or TS) that accepts Lemlist + Slack + HubSpot events with HMAC verification.
- `pipelines/inbound_triage.py` runs on webhook events, not CLI.
- **Acceptance:** a real Lemlist reply lands in HubSpot as an activity within 60s, with the correct tier action taken.

### Sprint 3 — Outcome tracking + brain wiring (week 3)
**Goal:** the moat starts compounding.
- New table `decisions(id, agent, pipeline, client, prospect_id, taken_at, slack_ts, hubspot_engagement_ids, outcome=null)`.
- Outcome backfiller: when a HubSpot deal moves stages or closes, mark the originating decisions win/loss/ghosted.
- Every agent run writes a memory to `kai-brain` with `(decision, context, outcome-tbd)`; outcome backfiller updates it.
- Brain recall in agent prompts: "for this ICP × signal × buyer-role combo, your prior win rate is X%."
- **Acceptance:** after one week of real traffic, `brain roi` shows agent-level win/loss attribution.

### Sprint 4 — Outbound for real (week 4)
**Goal:** drafts go from agent → human → Lemlist with state tracking.
- Sender persona library: `personas/<slug>.md` with voice card + signature + calendar URL per persona; agents pick personas per campaign.
- `pipelines/campaign_send.py`: brief → draft (existing campaign-drafter agent) → Slack approval thread → reaction listener → ✓ → Lemlist push.
- PUBL-01 enforced by reaction listener, not just prompt.
- **Acceptance:** a Slack ✓ reaction adds the prospect to the right Lemlist sequence; a ✗ logs the rejection reason for the next eval cycle.

### Sprint 5 — Deliverability discipline (week 5)
**Goal:** sender reputation doesn't quietly degrade.
- Per-sender state: bounce rate, complaint rate, warm-up state, sends/day.
- Auto-pause sequences when any sender crosses thresholds.
- Daily deliverability digest to agency owner.
- **Acceptance:** a deliberately bad sender triggers an auto-pause within 24h.

### Sprint 6 — Reporting layer (week 6)
**Goal:** clients see the value automatically.
- Weekly client report generator: real metrics + commentary + screenshots, output as PDF (via the `pdf` skill — Pandoc/Typst) or Notion page.
- Drops in the client's shared channel every Monday 09:00 local.
- **Acceptance:** one client's first report ships without manual editing.

### Sprint 7 — Signal ingestion (weeks 7–8)
**Goal:** the system reaches out for the right reasons.
- Start with one signal: LinkedIn job-change via Clay's job-change waterfall (webhook → enrich → score against ICP → if fit, queue for campaign-drafter).
- Add funding (Crunchbase) and hiring (LinkedIn jobs) — each signal type = one webhook + one scoring rule.
- **Acceptance:** an inbound signal becomes a sequenced prospect end-to-end with no manual touches.

### Sprint 8 — Multi-tenant + onboarding (weeks 9–10)
**Goal:** the OS is forkable for engagement #2, #3, #N.
- `gtmos onboard --client <slug>` scaffolds: HubSpot pipeline IDs, Slack channel, Lemlist team, voice card, eval baseline, dashboard.
- Per-client cost dashboard (Anthropic spend, run counts, outcomes).
- **Acceptance:** onboarding a second client takes ≤ 2 hours.

---

## What changes from v0.3

**Keep as-is:** `security.py`, `config.py`, `clients.py`, `runs.py`, `judge.py`, `agents.py`, `connectors/base.py`, all doctrine markdown, eval YAML format.

**Rework:**
- `pipelines/inbound_triage.py` — CLI → webhook-driven.
- `pipelines/weekly_review.py` — text-only → real PDF + Notion artifact.
- `tasks.py` — keep local; layer HubSpot tasks on top for client-facing work.
- `slack_app.py` — text-only routing → Block Kit + reaction listeners for approval flow.

**Replace:** `connectors/lemlist.py` stub → real client (Sprint 2).

**Rip:** `connectors/discovery.py` (Apollo + Clay direct stubs). Clay integration is webhook-driven; Apollo is unlikely. Remove until needed.

---

## The moat — what makes this defensible

1. **Outcome flywheel.** Every agent decision links to a real deal outcome. After 6 months: "LinkedIn-post citation within 3 days → 8% reply / 23% qualified" vs. "generic funding mention → 4% / 11%." Other agencies guess.
2. **Voice + signal-mix curated per ICP.** Brain-backed memory of which combinations land for which buyer types.
3. **Deliverability discipline.** Built-in monitoring + auto-pause. Most agencies don't do this; differentiating.
4. **Eval baselines per client.** Model upgrades don't silently regress agent quality.
5. **Brain integration.** Pattern recognition compounds across every engagement; client #4 starts smarter than client #1.

---

## Out of scope (deliberately)

- Native dashboards / custom CRM UI
- OAuth installer / marketplace listing
- Agency-side multi-user RBAC
- White-label rebrand
- Native mobile

All viable as v1.0 scope after the first real engagement validates the loop.

---

## Cost per active client engagement

- Anthropic API: ~$50–200/mo (agents + judge runs)
- Infra: ~$20/mo (Railway webhook receiver)
- Client pays HubSpot, Lemlist, Clay, Calendly directly.

---

## Open questions (resolve before promoting to a sprint)

- HubSpot dev portal: Kai uses production, or spin up a dedicated dev account for smoke tests? **Default: dev account; production access is high blast radius.**
- Webhook receiver host: Railway (Python, more familiar) or Cloudflare Worker (cheaper, lower latency, TS-only)? **Default: Railway for Sprint 2; reassess at Sprint 5.**
- `kai-brain` outcome write: direct DB write or via brain CLI subprocess? **Default: brain CLI; keeps the brain layer's accuracy guarantees.**
- Per-client Slack workspace or shared agency workspace with per-client channels? **Default: shared workspace, per-client channel + per-client bot installation.**

---

**Provenance:** kai8karma, 2026-05-09. Plan items reference patterns from `docs/PATTERNS.md`. Eval baselines per agent live in `evals/<agent>.yaml`.
