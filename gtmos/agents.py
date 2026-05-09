"""Agent loader + executor.

An "agent" is an `agents/<name>.md` doctrine file with a paired
`evals/<name>.yaml`. The executor:
  1. resolves and validates the agent file,
  2. loads its prompt + the global doctrine (CLAUDE.md, BRAND_GUIDELINES.md),
  3. constructs a system prompt built from doctrine ⊕ agent.md,
  4. calls Claude with a single user message describing the inputs,
  5. writes a run artifact under `runs/` (or per-client `runs/`),
  6. optionally runs the eval judge against the output.

The executor never auto-publishes. Outputs are drafts until something else
takes the approve path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gtmos.config import Settings
from gtmos.llm import LLMClient, LLMResponse
from gtmos.runs import RunArtifact
from gtmos.security import redact, safe_join, validate_slug

logger = logging.getLogger(__name__)

# Doctrine files folded into the system prompt so every agent inherits them.
_DOCTRINE_FILES = (
    "CLAUDE.md",
    "BRAND_GUIDELINES.md",
)
_AGENT_NAME_RE = __import__("re").compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


class AgentError(Exception):
    """Raised when an agent fails to load or execute."""


@dataclass(frozen=True)
class Agent:
    name: str
    path: Path
    prompt: str

    @classmethod
    def load(cls, name: str, repo_root: Path) -> Agent:
        if not isinstance(name, str) or not _AGENT_NAME_RE.fullmatch(name):
            raise AgentError(f"agent name {name!r} invalid")
        path = safe_join(repo_root, "agents", f"{name}.md")
        if not path.is_file():
            raise AgentError(f"agent file not found: agents/{name}.md")
        text = path.read_text(encoding="utf-8")
        if len(text.strip()) < 50:
            raise AgentError(f"agent file too short: agents/{name}.md")
        return cls(name=name, path=path, prompt=text)


@dataclass(frozen=True)
class AgentRun:
    name: str
    output_text: str
    response: LLMResponse | None
    artifact_path: Path
    error: str | None = None


@dataclass
class AgentExecutor:
    """Executes a named agent against a structured input dict."""

    settings: Settings
    llm: LLMClient

    @classmethod
    def from_settings(cls, settings: Settings) -> AgentExecutor:
        return cls(settings=settings, llm=LLMClient.from_settings(settings))

    def system_prompt(self, agent: Agent) -> str:
        parts = [
            "You are an agent inside a B2B GTM agency operating system.",
            "Read every doctrine block before producing any output.",
            "When in doubt, follow the doctrine.",
            "If a rule conflicts, the rule earlier in this prompt wins.",
            "Lead every output with the verdict. No marketing prose.",
            "End every output with the provenance footer specified by your agent file.",
            "",
        ]
        for rel in _DOCTRINE_FILES:
            try:
                p = safe_join(self.settings.repo_root, rel)
            except Exception as e:
                logger.warning("doctrine file %s not loadable: %s", rel, e)
                continue
            if not p.is_file():
                continue
            parts.append(f"# === DOCTRINE — {rel} ===")
            parts.append(p.read_text(encoding="utf-8"))
            parts.append("")
        parts.append(f"# === AGENT — agents/{agent.name}.md ===")
        parts.append(agent.prompt)
        return "\n".join(parts)

    def user_message(self, inputs: dict[str, Any]) -> str:
        # Inputs are rendered as JSON for deterministic prompting.
        # Redact in case the caller embedded secrets.
        import json as _json

        redacted = redact(_json.dumps(inputs, indent=2, default=str, sort_keys=True))
        return (
            "Run the agent with the following structured inputs:\n\n"
            "```json\n" + redacted + "\n```\n\n"
            "Produce the output specified by the agent file. "
            "End with the required provenance footer."
        )

    def run(
        self,
        agent_name: str,
        inputs: dict[str, Any],
        *,
        client_slug: str | None = None,
        task: str | None = None,
        max_tokens: int = 2048,
    ) -> AgentRun:
        if client_slug is not None:
            client_slug = validate_slug(client_slug, allow_underscore_prefix=True)

        agent = Agent.load(agent_name, self.settings.repo_root)
        artifact = RunArtifact(
            agent=agent.name,
            repo_root=self.settings.repo_root,
            client_slug=client_slug,
            task=task,
            inputs=inputs,
        )

        system = self.system_prompt(agent)
        user = self.user_message(inputs)

        try:
            resp = self.llm.complete(
                model=self.settings.agent_model,
                system=system,
                messages=[{"role": "user", "content": user}],
                max_tokens=max_tokens,
            )
        except Exception as e:
            artifact.error = redact(str(e))
            path = artifact.write()
            logger.error("agent %s failed: %s", agent_name, redact(str(e)))
            return AgentRun(
                name=agent.name,
                output_text="",
                response=None,
                artifact_path=path,
                error=artifact.error,
            )

        artifact.output_text = resp.text
        artifact.extra = {
            "model": resp.model,
            "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens,
            "cache_read_tokens": resp.cache_read_tokens,
            "cache_creation_tokens": resp.cache_creation_tokens,
            "stop_reason": resp.stop_reason,
        }
        path = artifact.write()
        return AgentRun(
            name=agent.name,
            output_text=resp.text,
            response=resp,
            artifact_path=path,
        )
