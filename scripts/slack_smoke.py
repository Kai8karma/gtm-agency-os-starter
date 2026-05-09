#!/usr/bin/env python3
"""Slack smoke test — posts + DMs + opens conversation against a real workspace.

Refuses to run without ``GTMOS_SLACK_SMOKE=1`` AND a SLACK_SMOKE_CHANNEL env
var (channel ID where the test message goes; expected to be a private "bot
sandbox" channel). Refuses to DM unless ``SLACK_SMOKE_USER`` is also set.
"""

from __future__ import annotations

import os
import sys

from gtmos.connectors import ConnectorAuthError, ConnectorError, ConnectorUnavailable
from gtmos.connectors.slack import SlackMessenger


def main() -> int:
    if os.environ.get("GTMOS_SLACK_SMOKE", "") != "1":
        print("refusing to run without GTMOS_SLACK_SMOKE=1; this hits a real Slack workspace")
        return 2

    token = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    channel = os.environ.get("SLACK_SMOKE_CHANNEL", "").strip()
    user = os.environ.get("SLACK_SMOKE_USER", "").strip()

    if not token:
        print("SLACK_BOT_TOKEN unset")
        return 2
    if not channel:
        print("SLACK_SMOKE_CHANNEL unset (expected a sandbox channel id like C…)")
        return 2

    try:
        sm = SlackMessenger(bot_token=token, default_provenance="gtmos slack-smoke")
    except ConnectorUnavailable as e:
        print(f"slack messenger unavailable: {e}")
        return 1

    failures: list[str] = []

    def step(name: str, fn) -> None:  # type: ignore[no-untyped-def]
        try:
            fn()
            print(f"  ✓ {name}")
        except (ConnectorAuthError, ConnectorError, ConnectorUnavailable, ValueError) as e:
            failures.append(f"{name}: {e}")
            print(f"  ✗ {name}: {e}")

    print(f"slack-smoke: channel={channel} user={user or '-'}")

    step(
        "post_message to channel",
        lambda: sm.post_message(
            channel=channel,
            text=":wave: gtmos slack-smoke (channel post)",
        ),
    )

    if user:
        step(
            "dm_user",
            lambda: sm.dm_user(
                user_id=user,
                text=":wave: gtmos slack-smoke (DM)",
            ),
        )

    print()
    if failures:
        print(f"slack-smoke: FAIL ({len(failures)})")
        return 1
    print("slack-smoke: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
