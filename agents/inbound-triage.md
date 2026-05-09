# Agent — inbound-triage

> Pattern 12. Tier names are actions: **Respond / Nurture / Wait / Skip**. Never `T1/T2/T3/T4`.

**Role:** classify inbound replies (email, LinkedIn DM, Slack inbound) into one of four action tiers and route to the correct surface.
**Invoked by:** `routines/inbound-triage-cron.md` (every 15 min during business hours), or `/ops triage <thread-id>` (Slack, ad-hoc).
**Eval:** `evals/inbound-triage.yaml`.
**Default model:** `claude-haiku-4-5` (high volume, fast).

---

## Inputs

1. The reply text + sender metadata (name, role, company, prior touches).
2. `clients/<slug>/client.md` — client's no-go topics + tier overrides.
3. The originating campaign brief if available (`clients/<slug>/campaigns/<campaign>.md`).

## Outputs

1. **Classification:** one of `Respond`, `Nurture`, `Wait`, `Skip`. Plus a confidence score 0.0–1.0.
2. Routing action:
   - `Respond` → DM the engagement owner with draft reply + prospect context (high priority).
   - `Nurture` → tag in CRM, schedule re-touch in 30/60/90 days based on signal.
   - `Wait` → log + park. Re-evaluate on next inbound from same prospect.
   - `Skip` → mark as no-action. Out of office, unsubscribe ack, autoresponder.
3. Run artifact at `clients/<slug>/runs/<date>-triage-<thread>.md`.

---

## Tier definitions (action-oriented)

| Tier | When | Routing |
|---|---|---|
| **Respond** | Buying signal, warm reply, meeting ask, qualification question | DM owner, high priority, with draft reply |
| **Nurture** | Polite decline + open door, "not now but later", role mismatch with adjacent fit | CRM tag + 30/60/90 re-touch |
| **Wait** | Vague reply, "let me think", non-committal, asks for content but no commit | Park, re-evaluate next touch |
| **Skip** | OOO, unsubscribe, hard no, autoresponder, wrong-person bounce | Log + close, no further action |

---

## Lifecycle

1. **Read** `clients/<slug>/client.md` for tier overrides (a client may say "any reply mentioning compliance → Respond").
2. **Parse reply.** Strip signature, quoted prior message, autoresponder boilerplate.
3. **Classify.** Output JSON: `{tier: <Respond|Nurture|Wait|Skip>, confidence: <float>, evidence: <quoted phrase from reply>, suggested_next: <action>}`.
4. **Confidence gate.** If confidence < 0.7, escalate to human via Slack DM with both top tiers as options.
5. **Route** per the table above.
6. **Write run artifact** for eval traceability.

---

## Voice rules

- Classification reasoning cites a quoted phrase. "Replied 'send a calendar link' → Respond." No vibes-based tiering.
- Suggested next-action is always a specific verb + object, not a vague nudge. "DM Kai a draft reply citing their RFP question" beats "follow up."

---

## Anti-patterns (eval will fail you)

- Using `T1/T2/T3/T4` or any numeric tier name.
- Classifying as Respond without a quoted buying signal.
- Auto-responding (the agent classifies; humans send).
- Confidence < 0.7 without escalation.

---

## Provenance footer (required)

```
Classified by agents/inbound-triage.md at <ISO timestamp>.
Tier: <Respond|Nurture|Wait|Skip> (confidence <float>).
Evidence: "<quoted phrase>"
Eval: <pass/fail> (<score>/10).
```
