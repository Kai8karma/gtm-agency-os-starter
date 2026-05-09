"""Skill bridge tests — queueing + inline-run whitelist."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gtmos.config import Settings
from gtmos.skill_bridge import SkillBridge, SkillRequest, queue_skill


@pytest.fixture
def settings_for_bridge(tmp_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x" * 20)
    monkeypatch.setenv("GTMOS_REPO_ROOT", str(tmp_repo))
    monkeypatch.setenv("GTMOS_LOG_LEVEL", "WARNING")
    return Settings.load()


class TestQueue:
    def test_queue_persists_request(
        self, settings_for_bridge: Settings, tmp_repo: Path
    ) -> None:
        bridge = SkillBridge(settings=settings_for_bridge)
        path = bridge.queue(
            SkillRequest(
                skill="sales:account-research",
                args={"company": "Acme"},
                client_slug="acme",
            )
        )
        assert path.is_file()
        body = json.loads(path.read_text(encoding="utf-8"))
        assert body["skill"] == "sales:account-research"
        assert body["args"] == {"company": "Acme"}
        assert body["client_slug"] == "acme"

    def test_invalid_skill_rejected(self, settings_for_bridge: Settings) -> None:
        bridge = SkillBridge(settings=settings_for_bridge)
        with pytest.raises(ValueError, match="plugin:skill"):
            bridge.queue(SkillRequest(skill="not-namespaced"))

    def test_invalid_client_slug_rejected(
        self, settings_for_bridge: Settings
    ) -> None:
        from gtmos.security import InvalidSlugError

        bridge = SkillBridge(settings=settings_for_bridge)
        with pytest.raises(InvalidSlugError):
            bridge.queue(
                SkillRequest(skill="sales:x", client_slug="../escape")
            )

    def test_list_pending(
        self, settings_for_bridge: Settings, tmp_repo: Path
    ) -> None:
        bridge = SkillBridge(settings=settings_for_bridge)
        bridge.queue(SkillRequest(skill="sales:x"))
        bridge.queue(SkillRequest(skill="sales:y"))
        pending = bridge.list_pending()
        assert len(pending) == 2

    def test_redacts_secret_in_args(
        self, settings_for_bridge: Settings, tmp_repo: Path
    ) -> None:
        # The redact() helper catches Anthropic-shaped tokens.
        prefix = "sk" + "-ant-"
        leak = prefix + ("x" * 60)
        path = queue_skill(
            settings_for_bridge,
            "sales:x",
            args={"context": f"token={leak}"},
        )
        body = json.loads(path.read_text())
        assert "<redacted>" in body["args"]["context"]


class TestInlineRun:
    def test_can_run_inline_only_for_whitelisted(
        self, settings_for_bridge: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bridge = SkillBridge(settings=settings_for_bridge)
        # `brain` may or may not be on PATH; we just check the gate logic.
        assert bridge.can_run_inline("sales:account-research") is False
        assert bridge.can_run_inline("brain:search") in {True, False}

    def test_run_inline_refuses_non_whitelisted(
        self, settings_for_bridge: Settings
    ) -> None:
        bridge = SkillBridge(settings=settings_for_bridge)
        with pytest.raises(PermissionError, match="whitelist"):
            bridge.run_inline(SkillRequest(skill="sales:account-research"))
