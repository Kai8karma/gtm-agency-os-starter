"""Webhook receiver — FastAPI app accepting Lemlist + Slack + HubSpot events.

Run with:
    gtmos webhook-server --port 8080
or:
    uvicorn gtmos.webhooks:app --port 8080

Security posture:
  * Lemlist signs payloads with HMAC-SHA256 of the request body using the
    workspace ``team api key`` (per Lemlist webhook docs). We verify with
    ``LEMLIST_WEBHOOK_SECRET`` env var; missing secret → 503 (NOT 401, so a
    misconfigured server doesn't get probed for valid events).
  * Slack events route through ``SlackVerifier`` (existing module).
  * HubSpot uses v3 ``X-HubSpot-Signature-V3`` HMAC. Verified inline.
  * Every accepted event is dispatched to a handler that runs the matching
    pipeline. Long work goes to a background task — handlers must return
    fast (per memory #283 — async tasks for long ops).
  * Body is always read once, raw, then parsed. Re-reading would invalidate
    the signature comparison.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import logging
import os
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from gtmos.config import ConfigError, Settings
from gtmos.security import (
    ReplayError,
    SignatureError,
    SlackVerifier,
    redact,
)

logger = logging.getLogger(__name__)


# ---- app factory -----------------------------------------------------------


def build_app() -> FastAPI:
    app = FastAPI(
        title="GTM Agency OS — webhook receiver",
        version="0.4.0",
        docs_url=None,  # don't expose /docs by default
        redoc_url=None,
    )

    # Resolve settings lazily so the app can be imported without all env set.
    state: dict[str, Any] = {}

    def _settings() -> Settings:
        if "settings" not in state:
            state["settings"] = Settings.load()
        return state["settings"]

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # ---- Lemlist ---------------------------------------------------------

    @app.post("/webhooks/lemlist")
    async def lemlist_webhook(request: Request, bg: BackgroundTasks) -> JSONResponse:
        secret = os.environ.get("LEMLIST_WEBHOOK_SECRET", "").strip()
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="webhook receiver not configured for lemlist",
            )

        body = await request.body()
        provided = request.headers.get("X-Lemlist-Signature", "")
        if not _verify_lemlist_signature(secret=secret, body=body, provided=provided):
            logger.warning("lemlist webhook signature failed")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad signature")

        try:
            event = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid JSON body: {redact(str(e))}",
            ) from e

        if not isinstance(event, dict):
            raise HTTPException(status_code=400, detail="event body must be JSON object")

        bg.add_task(_dispatch_lemlist_event, _settings(), event)
        return JSONResponse({"accepted": True})

    # ---- Slack -----------------------------------------------------------

    @app.post("/webhooks/slack")
    async def slack_webhook(request: Request, bg: BackgroundTasks) -> JSONResponse:
        try:
            settings = _settings()
        except ConfigError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        if not settings.slack_signing_secret:
            raise HTTPException(status_code=503, detail="SLACK_SIGNING_SECRET unset")

        body = await request.body()
        ts = request.headers.get("X-Slack-Request-Timestamp", "")
        sig = request.headers.get("X-Slack-Signature", "")
        verifier = SlackVerifier(
            signing_secret=settings.slack_signing_secret,
            replay_window_s=settings.slack_sig_replay_window_s,
            expected_team_id=settings.slack_team_id,
        )
        try:
            verifier.verify(timestamp=ts, signature=sig, body=body)
        except (SignatureError, ReplayError) as e:
            logger.warning("slack webhook rejected: %s", redact(str(e)))
            raise HTTPException(status_code=401, detail="bad signature") from e

        # Slack URL verification handshake.
        try:
            event = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise HTTPException(status_code=400, detail=f"bad body: {e}") from e
        if isinstance(event, dict) and event.get("type") == "url_verification":
            return JSONResponse({"challenge": event.get("challenge", "")})

        bg.add_task(_dispatch_slack_event, settings, event)
        return JSONResponse({"accepted": True})

    # ---- HubSpot ---------------------------------------------------------

    @app.post("/webhooks/hubspot")
    async def hubspot_webhook(request: Request, bg: BackgroundTasks) -> JSONResponse:
        secret = os.environ.get("HUBSPOT_WEBHOOK_SECRET", "").strip()
        if not secret:
            raise HTTPException(status_code=503, detail="HUBSPOT_WEBHOOK_SECRET unset")

        body = await request.body()
        method = request.method
        url = str(request.url)
        provided = request.headers.get("X-HubSpot-Signature-V3", "")
        ts = request.headers.get("X-HubSpot-Request-Timestamp", "")

        if not _verify_hubspot_signature(
            secret=secret,
            method=method,
            url=url,
            body=body,
            timestamp=ts,
            provided=provided,
        ):
            raise HTTPException(status_code=401, detail="bad signature")

        try:
            event = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise HTTPException(status_code=400, detail=f"bad body: {e}") from e

        bg.add_task(_dispatch_hubspot_event, _settings(), event)
        return JSONResponse({"accepted": True})

    return app


# ---- signature verification helpers ---------------------------------------


def _verify_lemlist_signature(*, secret: str, body: bytes, provided: str) -> bool:
    if not provided or not secret:
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, provided.strip())


def _verify_hubspot_signature(
    *,
    secret: str,
    method: str,
    url: str,
    body: bytes,
    timestamp: str,
    provided: str,
) -> bool:
    """HubSpot v3 signature: sha256(method + url + body + timestamp), base64."""
    if not (provided and timestamp):
        return False
    try:
        ts_int = int(timestamp)
    except ValueError:
        return False
    # Replay window of 5 minutes per HubSpot docs.
    now = dt.datetime.now(tz=dt.UTC).timestamp() * 1000
    if abs(now - ts_int) > 300_000:
        return False
    raw = (method.upper() + url + body.decode("utf-8", errors="replace") + str(ts_int)).encode(
        "utf-8"
    )
    digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    import base64

    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, provided.strip())


# ---- dispatchers (run in background tasks) --------------------------------


def _dispatch_lemlist_event(settings: Settings, event: dict[str, Any]) -> None:
    """Lemlist event types we care about: ``emailsReplied``, ``emailsBounced``."""
    event_type = (event.get("type") or "").strip()
    sender_email = (event.get("leadEmail") or event.get("email") or "").strip()
    campaign_id = (event.get("campaignId") or event.get("campaign") or "").strip()
    client_slug = (event.get("clientSlug") or _client_from_campaign(campaign_id)).strip()

    if event_type == "emailsReplied" and sender_email and client_slug:
        body = (event.get("text") or event.get("body") or "").strip() or "(no body)"
        subject = (event.get("subject") or "").strip()
        try:
            from gtmos.pipelines import InboundReply, run_inbound_triage

            reply = InboundReply(
                client_slug=client_slug,
                sender_email=sender_email,
                sender_name=(event.get("leadFirstName") or "") + " " + (event.get("leadLastName") or ""),
                subject=subject,
                body=body,
                thread_id=str(event.get("activityId") or ""),
            )
            run_inbound_triage(settings, reply)
        except Exception as e:
            logger.exception("lemlist inbound dispatch failed: %s", redact(str(e)))
        return

    if event_type == "emailsBounced":
        # Sprint-5 hook: deliverability monitor will consume these.
        logger.info("lemlist bounce: campaign=%s lead=%s", campaign_id, sender_email)
        return

    logger.info("lemlist event ignored: type=%s", event_type)


def _dispatch_slack_event(settings: Settings, event: dict[str, Any]) -> None:  # noqa: ARG001
    event_type = (event.get("event") or {}).get("type") if isinstance(event.get("event"), dict) else ""
    logger.info("slack event accepted (handler stub): type=%s", event_type or event.get("type"))


def _dispatch_hubspot_event(settings: Settings, event: dict[str, Any]) -> None:  # noqa: ARG001
    events = event if isinstance(event, list) else (event.get("events") or [event])
    for ev in events:
        if not isinstance(ev, dict):
            continue
        sub = ev.get("subscriptionType", "")
        logger.info("hubspot event accepted: %s", sub)


def _client_from_campaign(campaign_id: str) -> str:  # noqa: ARG001
    """Best-effort mapping campaign_id -> client_slug.

    Engagements override this by adding a ``campaigns/<campaign_id>.yaml``
    or by maintaining a side table; for the OOTB path we simply require the
    Lemlist payload to set ``clientSlug``. Returning empty triggers the
    handler to log + skip.
    """
    return ""


# `app` is the entrypoint for `uvicorn gtmos.webhooks:app`.
app = build_app()
