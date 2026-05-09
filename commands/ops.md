# `/ops` — the single Slack slash command

> Pattern 2 + Pattern 13. One slash command, action-named subcommands, DM-routed where owner-specific. Adding a second top-level command (`/biz`, `/sales`, `/crumbs-do-the-thing`) is a doctrine violation.

Customize the channel + slash command name per engagement (CLAUDE.md § 12). Default: `#ops-engineering`, `/ops`.

---

## Subcommand contract

| Subcommand | Invokes | Output target | Frequency |
|---|---|---|---|
| `/ops audit <client>` | `agents/audit-mapper.md` | DM to engagement owner + `AUDIT_REPORT_<CLIENT>_<DATE>.md` PR | Quarterly per client |
| `/ops review <client>` | `agents/weekly-review.md` | DM to engagement owner | Weekly per client (also fires from `routines/per-client-weekly-review.md`) |
| `/ops draft <campaign-type> --client <slug>` | `agents/campaign-drafter.md` | Thread reply with draft + approval prompt | Ad-hoc |
| `/ops triage [<thread-id>]` | `agents/inbound-triage.md` | Routed per tier (Respond → DM, Skip → log only) | Cron + ad-hoc |
| `/ops digest` | `agents/daily-digest.md` | DM to owner | Cron 07:00, ad-hoc OK |
| `/ops continue` | (resumes a paused agent run) | Same channel/thread as the pause | Manual |
| `/ops status` | (shows last 7 days of runs across all clients) | Channel post in `#ops-engineering` | Ad-hoc |

No other top-level subcommands. If a new action is needed, propose the addition in `PLAN.md` first.

---

## Routing rules

- **DM the human, not the channel** (Pattern 13) when the action is owner-specific:
  - `/ops review`, `/ops digest`, `/ops audit` → DM the engagement owner.
  - `/ops triage` Respond-tier → DM the campaign owner.
  - `/ops triage` Skip/Wait → log only, no DM.
- **Channel post** is reserved for shared status:
  - `/ops status` (status board)
  - `/ops draft` (draft is shown inline so the channel can review-and-approve in thread)
- **Provenance line on every output.** No exceptions.

---

## Slack user ID resolution (Pattern 13)

`owner_slack_id` lives in `clients/<slug>/client.md` frontmatter. If missing, the bot:

1. Posts a DM to the agency admin (`agency_admin_slack_id` in `BRAND_GUIDELINES.md` frontmatter).
2. Asks for the missing ID once.
3. Backfills it via PR titled `chore(client): backfill <slug> owner_slack_id`.

The backfill PR is auto-merged if it touches only `clients/<slug>/client.md` and only the `owner_slack_id` field.

---

## Approval flow (PUBL-01)

Any agent output that produces client-facing copy (campaign drafts, customer emails, public posts) requires explicit human approval before send:

1. Agent posts the draft in a thread.
2. Owner reacts ✓ to approve, ✗ to reject, ⚠ to revise.
3. ✓ → bot calls the publish path (Lemlist API, email send, etc.).
4. ✗ or ⚠ → bot exits and logs the decision to the run artifact.

No approval = no publish. Auto-publish is an instant PR rejection (CLAUDE.md § 11).

---

## Authorization

- Subcommands that modify state (`/ops draft`, `/ops review`, `/ops audit`) require the invoker to be in the agency Slack workspace.
- Per-client subcommands (`<client>` argument) check `clients/<slug>/client.md` `team` field — only members of that team can invoke.
- `/ops status` is open to the channel.

---

## Example invocations

```
/ops audit acme
  → agents/audit-mapper.md fires
  → DMs the owner with verdict + opens PR with AUDIT_REPORT_ACME_2026-05-10.md

/ops review acme
  → agents/weekly-review.md fires
  → DMs owner; if dormant (Pattern 11), logs skip and exits 0

/ops draft jrs-q2 --client acme
  → agents/campaign-drafter.md fires
  → posts draft in thread, awaits ✓ reaction

/ops triage T01234567890
  → classifies that one thread, routes per tier

/ops digest
  → fires daily-digest for the invoker
```

---

**Provenance:** `commands/ops.md`, kai8karma 2026-05-09. Aligns with `CLAUDE.md` § 8 (Slack interface contract).
