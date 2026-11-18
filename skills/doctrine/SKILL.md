---
name: doctrine
description: Load the GTM Agency OS operating doctrine before doing any agency work in this plugin's repository: client audits, weekly reviews, campaign drafts, inbound triage, routines, or changes to agents and evals. Use at the start of every such session.
---

# GTM Agency OS doctrine

A `CLAUDE.md` at a plugin's root is not loaded as context, so this skill is
how the doctrine reaches you when the OS is installed as a plugin.

Read these before acting, in this order:

1. `${CLAUDE_PLUGIN_ROOT}/CLAUDE.md` - the master doctrine. It overrides
   everything else in the repository.
2. `${CLAUDE_PLUGIN_ROOT}/BRAND_GUIDELINES.md` - the voice card, for
   anything a client or prospect will read.
3. `${CLAUDE_PLUGIN_ROOT}/docs/PATTERNS.md` - the 18 patterns the doctrine
   refers to by number.
4. `${CLAUDE_PLUGIN_ROOT}/PLAN.md` - the current four-week plan.

Then follow the doctrine as written. Three points people get wrong:

- The files under `agents/` and `commands/` are prompts and Slack specs for
  the Python runtime. Run them with the `gtmos` CLI
  (`gtmos run-agent <name> --client <slug>`); they are not Claude Code
  subagents or slash commands.
- Every agent has a paired `evals/<agent>.yaml`. A change to an agent
  without a change to, or a run of, its eval is incomplete. `make verify`
  and `make eval` are the gates.
- Per-client overrides live in `clients/<slug>/client.md` and take
  precedence over the defaults for that client only.
