"""Slack handler — `/ops` slash command + interactive approve/reject.

Security posture:
  * Every inbound request signature-verified via slack_bolt's built-in
    SignatureVerifier (replay window enforced via SLACK_SIG_REPLAY_WINDOW_S).
  * Per-client subcommands check `team` membership (gtmos.clients).
  * No agent runs in the request thread — long work goes to a background
    thread; the slash command immediately ack()'s within Slack's 3s budget.
  * Every public response carries provenance.

Wire to Slack:
  * Create a Slack app with a slash command pointed at
    https://<host>/slack/events ; bot scopes ``commands chat:write im:write``.
  * Set SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, optionally SLACK_TEAM_ID.

Test locally with `gtmos slack-app --port 3000` and tunnel via your reverse
proxy of choice.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from slack_bolt import Ack, App, Respond
from slack_sdk.web import WebClient

from gtmos.agents import AgentExecutor
from gtmos.clients import ClientLoadError, is_authorized_invoker, list_clients, load_client
from gtmos.config import Settings
from gtmos.security import InvalidSlugError, redact, validate_slug

logger = logging.getLogger(__name__)


_SUBCOMMANDS = {"audit", "review", "draft", "triage", "digest", "status", "help"}


def build_app(settings: Settings) -> App:
    """Construct the Slack Bolt app. ``settings`` must include slack creds."""
    if not settings.slack_signing_secret or not settings.slack_bot_token:
        raise RuntimeError(
            "build_app requires SLACK_SIGNING_SECRET and SLACK_BOT_TOKEN; "
            "load Settings with require=('slack',)"
        )

    app = App(
        token=settings.slack_bot_token,
        signing_secret=settings.slack_signing_secret,
        # slack_bolt enforces this internally; we mirror our own knob for parity.
        request_verification_enabled=True,
        ssl_check_enabled=True,
    )

    executor = AgentExecutor.from_settings(settings)

    @app.command("/ops")
    def handle_ops(ack: Ack, command: dict[str, Any], respond: Respond, client: WebClient) -> None:
        ack()  # within 3s, always.
        try:
            _route(settings, executor, command, respond, client)
        except Exception as e:
            logger.exception("/ops handler error")
            respond(f"⚠ /ops error: `{redact(str(e))}`")

    return app


# ---- routing ---------------------------------------------------------------


def _route(
    settings: Settings,
    executor: AgentExecutor,
    command: dict[str, Any],
    respond: Respond,
    client: WebClient,
) -> None:
    raw_text = (command.get("text") or "").strip()
    user_id = command.get("user_id", "")
    team_id = command.get("team_id", "")

    if settings.slack_team_id and team_id != settings.slack_team_id:
        respond("✗ this workspace is not authorized for /ops")
        return

    parts = raw_text.split()
    if not parts:
        respond(_help_message())
        return
    sub = parts[0].lower()
    if sub not in _SUBCOMMANDS:
        respond(f"✗ unknown subcommand `{sub}`. Valid: {', '.join(sorted(_SUBCOMMANDS))}")
        return

    rest = parts[1:]

    if sub == "help":
        respond(_help_message())
        return
    if sub == "status":
        _status(settings, respond)
        return
    if sub == "digest":
        _kick_background(
            target=lambda: _run_agent(executor, "daily-digest", inputs={"owner": user_id},
                                      task=f"digest-{user_id}"),
            on_done=lambda art: respond(f"✓ daily-digest run: `{art}`"),
            on_err=lambda e: respond(f"✗ daily-digest failed: `{redact(str(e))}`"),
        )
        respond("⏳ running daily-digest…")
        return

    if sub in {"audit", "review", "draft", "triage"}:
        if not rest:
            respond(f"✗ `/ops {sub}` requires a client slug")
            return
        try:
            slug = validate_slug(rest[0])
        except InvalidSlugError as e:
            respond(f"✗ invalid client slug: `{redact(str(e))}`")
            return

        try:
            cli = load_client(settings.repo_root, slug)
        except ClientLoadError as e:
            respond(f"✗ {redact(str(e))}")
            return

        if not is_authorized_invoker(cli, user_id):
            respond(f"✗ {user_id} is not in clients/{slug}/ team")
            return

        agent_for_sub = {
            "audit": "audit-mapper",
            "review": "weekly-review",
            "draft": "campaign-drafter",
            "triage": "inbound-triage",
        }[sub]

        # Extract any extra args (e.g. campaign type for draft).
        extras = " ".join(rest[1:]).strip()
        inputs: dict[str, Any] = {
            "client": slug,
            "invoker": user_id,
            "extra_args": extras,
        }

        respond(f"⏳ running {agent_for_sub} for `{slug}`…")
        _kick_background(
            target=lambda: _run_agent(
                executor, agent_for_sub, inputs=inputs, client_slug=slug,
                task=f"{sub}-{user_id}"),
            on_done=lambda art: client.chat_postMessage(
                channel=cli.owner_slack_id or user_id,
                text=f"✓ {agent_for_sub} for `{slug}` complete. Run: `{art}`. "
                     f"Generated by `agents/{agent_for_sub}.md`. PUBL-01: review before send.",
            ),
            on_err=lambda e: respond(f"✗ {agent_for_sub} failed: `{redact(str(e))}`"),
        )
        return


# ---- helpers ---------------------------------------------------------------


def _run_agent(executor: AgentExecutor, name: str, *, inputs: dict[str, Any],
               client_slug: str | None = None, task: str | None = None) -> str:
    run = executor.run(name, inputs, client_slug=client_slug, task=task)
    if run.error:
        raise RuntimeError(run.error)
    return str(run.artifact_path.relative_to(executor.settings.repo_root))


def _kick_background(*, target, on_done, on_err) -> None:  # type: ignore[no-untyped-def]
    """Run `target()` in a daemon thread; fan results to callbacks.

    Slack's slash-command response budget is 3s. Any agent run exceeds that,
    so the request thread acks immediately and the work happens in the
    background. ``on_done`` and ``on_err`` are called from the worker thread
    and should be Slack API calls (already retry-safe via slack_sdk).
    """
    def _worker() -> None:
        try:
            result = target()
        except Exception as e:
            on_err(e)
        else:
            on_done(result)

    thread = threading.Thread(target=_worker, daemon=True, name="gtmos-agent")
    thread.start()


def _status(settings: Settings, respond: Respond) -> None:
    clients = list_clients(settings.repo_root)
    text = "*GTM Agency OS — status*\n"
    text += f"• repo: `{settings.repo_root}`\n"
    text += f"• clients: {len(clients)} active ({', '.join(clients) or 'none'})\n"
    text += f"• agent model: `{settings.agent_model}`\n"
    text += f"• judge model: `{settings.judge_model}`\n"
    text += "Generated by `gtmos.slack_app._status`."
    respond(text)


def _help_message() -> str:
    return (
        "*`/ops` — GTM Agency OS*\n"
        "• `/ops audit <client>` — run audit-mapper\n"
        "• `/ops review <client>` — run weekly-review\n"
        "• `/ops draft <client> <campaign>` — run campaign-drafter\n"
        "• `/ops triage <client>` — run inbound-triage\n"
        "• `/ops digest` — run daily-digest for you\n"
        "• `/ops status` — show repo + model state\n"
        "• `/ops help` — this message\n"
        "Doctrine: `commands/ops.md`."
    )
