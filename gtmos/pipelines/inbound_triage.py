"""Inbound-triage pipeline — REAL classification + CRM write + Slack DM.

Flow:
  1. Accept an InboundReply (from CLI input, webhook, or a Lemlist-pull).
  2. Run the inbound-triage agent → tier ∈ {Respond, Nurture, Wait, Skip}.
  3. Resolve the prospect in HubSpot (search by sender email).
  4. Take tier action:
       Respond → DM owner with draft + log a HubSpot email-activity record
       Nurture → log HubSpot note + create a 30-day follow-up task
       Wait    → log HubSpot note (parking notice)
       Skip    → log only; no CRM/Slack noise
  5. Write the run artifact.

The agent's classification output is JSON-extracted so we route on the tier
field, not on hopeful regex over English. If the agent fails to return JSON
or the confidence < 0.7, we escalate to a human via Slack DM with the
ambiguity flagged.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from gtmos.agents import AgentExecutor
from gtmos.clients import load_client
from gtmos.config import Settings
from gtmos.connectors import ConnectorError, ConnectorUnavailable
from gtmos.connectors.hubspot import HubSpotClient
from gtmos.connectors.slack import SlackMessenger
from gtmos.security import is_likely_tool_output, redact

logger = logging.getLogger(__name__)


VALID_TIERS = ("Respond", "Nurture", "Wait", "Skip")
DEFAULT_CONFIDENCE_GATE = 0.7


@dataclass
class InboundReply:
    """One reply to triage."""

    client_slug: str
    sender_email: str
    sender_name: str = ""
    subject: str = ""
    body: str = ""
    received_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(tz=dt.UTC))
    thread_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.body, str) or not self.body.strip():
            raise ValueError("InboundReply.body required")
        if not _is_email(self.sender_email):
            raise ValueError(f"InboundReply.sender_email invalid: {self.sender_email!r}")
        if self.received_at.tzinfo is None:
            raise ValueError("InboundReply.received_at must be timezone-aware")


@dataclass
class TriageResult:
    client_slug: str
    tier: str = "Skip"
    confidence: float = 0.0
    evidence: str = ""
    suggested_next: str = ""
    contact_id: str | None = None
    artifact_path: str | None = None
    slack_ts: str | None = None
    hubspot_engagement_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    escalated: bool = False

    @property
    def succeeded(self) -> bool:
        return not self.errors and self.tier in VALID_TIERS


def run_inbound_triage(
    settings: Settings,
    reply: InboundReply,
    *,
    hubspot: HubSpotClient | None = None,
    slack: SlackMessenger | None = None,
    executor: AgentExecutor | None = None,
    confidence_gate: float = DEFAULT_CONFIDENCE_GATE,
) -> TriageResult:
    client = load_client(settings.repo_root, reply.client_slug)
    result = TriageResult(client_slug=client.slug)
    when = dt.datetime.now(tz=dt.UTC)

    # ---- 1. classify via the agent ------------------------------------------
    agent_inputs = {
        "client": client.slug,
        "client_name": client.name,
        "no_go_topics": client.no_go_topics,
        "tier_overrides": client.tier_overrides,
        "reply": {
            "sender_email": reply.sender_email,
            "sender_name": reply.sender_name,
            "subject": reply.subject,
            # Flag suspicious payloads so the agent prompt can isolate them.
            "body_flagged_as_tool_output": is_likely_tool_output(reply.body),
            "body": reply.body[:8000],  # bound prompt size
            "received_at": reply.received_at.isoformat(timespec="seconds"),
        },
    }
    ex = executor or AgentExecutor.from_settings(settings)
    run = ex.run(
        "inbound-triage",
        inputs=agent_inputs,
        client_slug=client.slug,
        task=f"triage-{_safe(reply.thread_id) or _safe(reply.sender_email) or 'one'}",
    )
    if run.error:
        result.errors.append(f"agent error: {run.error}")
        return result
    result.artifact_path = str(run.artifact_path.relative_to(settings.repo_root))

    parsed = _extract_classification(run.output_text)
    result.tier = parsed["tier"]
    result.confidence = parsed["confidence"]
    result.evidence = parsed["evidence"]
    result.suggested_next = parsed["suggested_next"]

    # ---- 2. resolve contact in HubSpot --------------------------------------
    try:
        hs = hubspot or HubSpotClient.from_settings(settings)
    except ConnectorUnavailable as e:
        result.errors.append(f"hubspot unavailable: {e}")
        hs = None

    if hs is not None:
        try:
            matches = hs.search_contacts(email=reply.sender_email, limit=1)
            if matches:
                result.contact_id = matches[0]["id"]
        except (ConnectorError, ValueError) as e:
            result.errors.append(f"hubspot.search_contacts failed: {e}")

    # ---- 3. confidence gate → escalate or act -------------------------------
    try:
        sm = slack or SlackMessenger.from_settings(settings)
    except ConnectorUnavailable as e:
        result.errors.append(f"slack unavailable: {e}")
        sm = None

    if result.confidence < confidence_gate:
        result.escalated = True
        if sm and client.owner_slack_id:
            try:
                ack = sm.dm_user(
                    user_id=client.owner_slack_id,
                    text=_format_escalation_dm(client.name, reply, result),
                    provenance=_provenance(client.slug, when, result.artifact_path),
                )
                result.slack_ts = str(ack.get("ts") or "")
            except ConnectorError as e:
                result.errors.append(f"slack escalation failed: {e}")
        return result  # do NOT auto-act below threshold

    # ---- 4. tier action -----------------------------------------------------
    if result.tier == "Respond":
        if sm and client.owner_slack_id:
            try:
                ack = sm.dm_user(
                    user_id=client.owner_slack_id,
                    text=_format_respond_dm(client.name, reply, result),
                    provenance=_provenance(client.slug, when, result.artifact_path),
                )
                result.slack_ts = str(ack.get("ts") or "")
            except ConnectorError as e:
                result.errors.append(f"slack respond DM failed: {e}")
        if hs and result.contact_id:
            try:
                eng = hs.log_email_activity(
                    contact_id=result.contact_id,
                    subject=reply.subject or "(no subject)",
                    body=reply.body[:65000],
                    direction="INCOMING_EMAIL",
                    timestamp=reply.received_at,
                )
                eng_id = str(eng.get("id") or "")
                if eng_id:
                    result.hubspot_engagement_ids.append(eng_id)
            except (ConnectorError, ValueError) as e:
                result.errors.append(f"hubspot.log_email_activity failed: {e}")

    elif result.tier == "Nurture":
        if hs and result.contact_id:
            try:
                note = hs.create_note(
                    contact_id=result.contact_id,
                    body=_format_nurture_note(reply, result),
                )
                if note.get("id"):
                    result.hubspot_engagement_ids.append(str(note["id"]))
            except (ConnectorError, ValueError) as e:
                result.errors.append(f"hubspot.create_note failed: {e}")
            try:
                task = hs.create_task(
                    contact_id=result.contact_id,
                    title=f"Nurture re-touch: {reply.sender_name or reply.sender_email}",
                    due_at=when + dt.timedelta(days=30),
                    body=result.suggested_next or "30-day re-touch",
                )
                if task.get("id"):
                    result.hubspot_engagement_ids.append(str(task["id"]))
            except (ConnectorError, ValueError) as e:
                result.errors.append(f"hubspot.create_task failed: {e}")

    elif result.tier == "Wait":
        if hs and result.contact_id:
            try:
                note = hs.create_note(
                    contact_id=result.contact_id,
                    body=_format_wait_note(reply, result),
                )
                if note.get("id"):
                    result.hubspot_engagement_ids.append(str(note["id"]))
            except (ConnectorError, ValueError) as e:
                result.errors.append(f"hubspot.create_note failed: {e}")

    # tier == Skip → log + close, no CRM / Slack noise

    return result


# ---- formatters ------------------------------------------------------------


def _format_respond_dm(client_name: str, reply: InboundReply, r: TriageResult) -> str:
    return (
        f"*🚨 Respond-tier inbound — {client_name}*\n"
        f"From: {reply.sender_name or reply.sender_email} <{reply.sender_email}>\n"
        f"Subject: {reply.subject or '(none)'}\n"
        f"Confidence: {r.confidence:.2f} · Evidence: \"{redact(r.evidence)[:200]}\"\n\n"
        f"Suggested next: {redact(r.suggested_next)[:500]}"
    )


def _format_escalation_dm(client_name: str, reply: InboundReply, r: TriageResult) -> str:
    return (
        f"*⚠ Triage escalation — {client_name}*\n"
        f"From: {reply.sender_name or reply.sender_email}\n"
        f"Confidence {r.confidence:.2f} below gate — please pick a tier.\n"
        f"Body excerpt: \"{redact(reply.body)[:300]}\""
    )


def _format_nurture_note(reply: InboundReply, r: TriageResult) -> str:
    return (
        f"GTM OS triage: Nurture (conf {r.confidence:.2f}). "
        f"Subject: {reply.subject!r}. "
        f"Evidence: {redact(r.evidence)[:300]}. "
        f"Suggested re-touch: {redact(r.suggested_next)[:300]}."
    )


def _format_wait_note(reply: InboundReply, r: TriageResult) -> str:
    return (
        f"GTM OS triage: Wait (conf {r.confidence:.2f}). "
        f"Subject: {reply.subject!r}. "
        f"Evidence: {redact(r.evidence)[:300]}."
    )


def _provenance(client_slug: str, when: dt.datetime, artifact: str | None) -> str:
    return (
        f"Generated by `agents/inbound-triage.md` for `{client_slug}` at "
        f"{when.isoformat(timespec='seconds')}. Run: `{artifact}`."
    )


# ---- agent-output classification extraction --------------------------------


_TIER_RE = re.compile(r"\b(Respond|Nurture|Wait|Skip)\b")


def _extract_classification(text: str) -> dict[str, Any]:
    """Tolerant parse of the agent output. JSON preferred; falls back to regex."""
    out = {"tier": "Skip", "confidence": 0.0, "evidence": "", "suggested_next": ""}
    if not isinstance(text, str) or not text:
        return out

    obj = _first_json_object(text)
    if obj is not None:
        tier = str(obj.get("tier", "")).strip().capitalize()
        if tier in VALID_TIERS:
            out["tier"] = tier
        try:
            out["confidence"] = max(0.0, min(1.0, float(obj.get("confidence", 0.0))))
        except (TypeError, ValueError):
            out["confidence"] = 0.0
        out["evidence"] = str(obj.get("evidence", ""))[:500]
        out["suggested_next"] = str(obj.get("suggested_next", ""))[:500]
        return out

    # Regex fallback — accept the first tier word the agent emits, no confidence.
    m = _TIER_RE.search(text)
    if m:
        out["tier"] = m.group(1)
        out["confidence"] = 0.5  # below gate → forces escalation
        out["evidence"] = text.strip()[:300]
    return out


def _first_json_object(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start : i + 1])
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    return None
    return None


# ---- helpers ----------------------------------------------------------------


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_FILENAME_RE = re.compile(r"[^a-z0-9-]+")


def _is_email(value: str) -> bool:
    return isinstance(value, str) and bool(_EMAIL_RE.match(value))


def _safe(value: str) -> str:
    if not isinstance(value, str):
        return ""
    return _FILENAME_RE.sub("-", value.lower()).strip("-")[:60]
