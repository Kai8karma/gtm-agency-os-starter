# Stack overrides

> `CLAUDE.md` § 4 lists the assumed stack. Any deviation lands here. One row per override. Each override has a date and an owner.

This is the audit trail for "why is this engagement different from the template."

---

## Override log

| Date | Engagement / scope | Default | Override | Reason | Owner |
|---|---|---|---|---|---|
| _2026-05-09_ | _(template)_ | _(see CLAUDE.md § 4)_ | _none yet_ | _starter template, no engagements live_ | _kai8karma_ |

---

## How to add an override

1. Identify the deviation (e.g., client uses Salesforce instead of HubSpot).
2. Add a row to the table above.
3. Update the relevant agent or routine file with a conditional path or `--stack <override>` flag.
4. Add a fixture to the corresponding eval that exercises the override path.

If three or more engagements override the same default, the **default itself is wrong** — propose a doctrine update via PR to `CLAUDE.md` § 4.

---

## Common overrides (template defaults & alternatives)

| Concern | Default | Common alt | Notes |
|---|---|---|---|
| CRM | HubSpot | Salesforce | HubSpot MCP exists; Salesforce MCP requires custom auth. |
| CRM (small) | HubSpot | Notion | Notion as CRM works for ≤ 200 contacts; breaks beyond. |
| Sequencer | Lemlist | Outreach / Salesloft | Lemlist API simpler; Outreach has better deliverability tools. |
| Surface | Slack | MS Teams | Teams MCP coverage is thinner; expect more manual work. |
| Task store | Notion DB | Linear / sqlite | Linear if engineering-heavy team; sqlite for small ops teams. |
| Deploy | Railway | Vercel / Fly.io | Railway for Python services; Vercel for JS-only. |
| Observability | Sentry | Datadog | Pattern 16 requires *something* — pick one and enforce. |

---

**Provenance:** template default, kai8karma 2026-05-09.
