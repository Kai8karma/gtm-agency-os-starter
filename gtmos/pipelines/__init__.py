"""End-to-end GTM pipelines.

A *pipeline* is a multi-stage process that touches at least one external
system to do real ops work — pull CRM state, classify a reply, send a DM,
log an activity. Pipelines are the difference between "agent that emits
text" and "GTM OS that moves state in your CRM."

Each pipeline:
  1. Loads its config (client doctrine, brand guidelines, settings).
  2. Pulls real data from connectors (HubSpot, Slack, Lemlist as wired).
  3. Calls one or more agents to produce the verdict text.
  4. Writes back to the connectors (Slack DM, HubSpot activity, etc.).
  5. Records a run artifact under ``runs/`` with the full trace.

Pipelines never auto-publish client-facing copy without an explicit ✓ from
a human — see PUBL-01 in commands/ops.md.
"""

from __future__ import annotations

from gtmos.pipelines.inbound_triage import InboundReply, run_inbound_triage
from gtmos.pipelines.weekly_review import run_weekly_review

__all__ = [
    "InboundReply",
    "run_inbound_triage",
    "run_weekly_review",
]
