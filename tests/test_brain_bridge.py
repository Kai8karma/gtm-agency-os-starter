"""BrainBridge subprocess wrapper tests.

The brain CLI is a real binary on Kai's box but absent in CI. Tests use a
``GTMOS_BRAIN_BIN`` override pointing at a tiny shell script that emits
deterministic output, so we exercise the parsing + arg validation paths
without running the real brain.
"""

from __future__ import annotations

import stat
import textwrap
from pathlib import Path

import pytest

from gtmos.brain import BrainBridge, BrainError, BrainUnavailable


def _write_fake_brain(tmp_path: Path, body: str) -> Path:
    """Drop a shell script that prints `body` and exits 0."""
    script = tmp_path / "fake-brain"
    script.write_text(
        "#!/usr/bin/env bash\nset -e\n" + body + "\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


@pytest.fixture
def brain_bin_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    body = textwrap.dedent(
        """
        if [[ "$1" == "search" ]]; then
            cat <<'EOF'
[
  {"id": 694, "title": "GTM OS architecture catalog", "preview": "5 layers",
   "confidence": 0.7, "source_trust": "core"},
  {"id": 225, "title": "Strat-Agent Model", "preview": "humans close",
   "confidence": 0.69, "source_trust": "core"}
]
EOF
        elif [[ "$1" == "used" ]]; then
            echo "usage 42 logged"
        elif [[ "$1" == "outcome" ]]; then
            echo "outcome recorded"
        elif [[ "$1" == "remember" ]]; then
            echo "memory #1234 created"
        elif [[ "$1" == "voice" ]]; then
            echo "Kai's voice: terse, decision-first."
        else
            echo "unknown" >&2
            exit 1
        fi
        """
    )
    script = _write_fake_brain(tmp_path, body)
    monkeypatch.setenv("GTMOS_BRAIN_BIN", str(script))
    return script


class TestDiscover:
    def test_discover_returns_none_when_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GTMOS_BRAIN_BIN", "/nope/does-not-exist")
        assert BrainBridge.discover() is None

    def test_discover_finds_via_override(self, brain_bin_json: Path) -> None:
        b = BrainBridge.discover()
        assert b is not None


class TestSearch:
    def test_parses_json_output(self, brain_bin_json: Path) -> None:
        b = BrainBridge()
        hits = b.search("gtm os")
        assert len(hits) == 2
        assert hits[0].id == 694
        assert "GTM OS" in hits[0].title

    def test_rejects_empty_query(self, brain_bin_json: Path) -> None:
        b = BrainBridge()
        with pytest.raises(BrainError, match="query"):
            b.search("   ")

    def test_rejects_bad_limit(self, brain_bin_json: Path) -> None:
        b = BrainBridge()
        with pytest.raises(BrainError):
            b.search("x", limit=0)
        with pytest.raises(BrainError):
            b.search("x", limit=999)


class TestUsed:
    def test_returns_usage_id(self, brain_bin_json: Path) -> None:
        b = BrainBridge()
        uid = b.used(694, context="agent=test")
        assert uid == 42

    def test_rejects_bad_memory_id(self, brain_bin_json: Path) -> None:
        b = BrainBridge()
        with pytest.raises(BrainError):
            b.used(0)
        with pytest.raises(BrainError):
            b.used(-1)


class TestOutcome:
    def test_accepts_valid_verdict(self, brain_bin_json: Path) -> None:
        b = BrainBridge()
        b.outcome(42, "win")
        b.outcome(42, "loss")
        b.outcome(42, "neutral", note="closed mid-funnel")

    def test_rejects_unknown_verdict(self, brain_bin_json: Path) -> None:
        b = BrainBridge()
        with pytest.raises(BrainError, match="verdict"):
            b.outcome(42, "kinda")

    def test_rejects_bad_usage_id(self, brain_bin_json: Path) -> None:
        b = BrainBridge()
        with pytest.raises(BrainError):
            b.outcome(0, "win")


class TestRemember:
    def test_extracts_new_id(self, brain_bin_json: Path) -> None:
        b = BrainBridge()
        new_id = b.remember("decision", "test", "test content")
        assert new_id == 1234

    def test_rejects_bad_type(self, brain_bin_json: Path) -> None:
        b = BrainBridge()
        with pytest.raises(BrainError):
            b.remember("invalid-type", "title", "content")


class TestVoiceCard:
    def test_returns_voice_text(self, brain_bin_json: Path) -> None:
        b = BrainBridge()
        v = b.voice_card()
        assert "Kai" in v


class TestMissingBrain:
    def test_raises_unavailable_when_path_invalid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GTMOS_BRAIN_BIN", "/dev/null/no-such-file")
        with pytest.raises(BrainUnavailable):
            BrainBridge().search("anything")
