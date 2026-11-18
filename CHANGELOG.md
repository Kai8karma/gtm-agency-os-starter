# Changelog

Notable changes to gtm-agency-os-starter. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed
- **Plugin manifest.** `.claude-plugin/plugin.json` failed
  `claude plugin validate` with two errors: `agents` and `commands` were
  arrays of objects, where Claude Code accepts paths. The manifest now
  validates. Runtime agents, Slack commands, routines, doctrine paths and
  the verification command moved under `metadata`, and the manifest
  version matches the package (0.4.1, was 0.1.0).
- **CI: lint.** Ruff was unpinned (`>=0.5,<1.0`) and a newer release
  flagged `SIM102` in `gtmos/pipelines/inbound_triage.py`. The nested `if`
  is flattened with no change in behaviour, and ruff is pinned to 0.17.5 in
  CI and in the `dev` extra.
- **CI: CVE audit.** `pip-audit --strict` failed because `gtmos` is not on
  PyPI and cannot be looked up. The job now audits the frozen set of
  third-party packages the project installs.
- **README.** The file tree listed Lemlist as a stub while the status table
  listed it as wired, and omitted `webhooks.py`, `brain.py`,
  `multi_tenant.py` and `skill_bridge.py`.

### Added
- `skills/doctrine/SKILL.md`, so the doctrine loads when the repository is
  installed as a Claude Code plugin. A `CLAUDE.md` at a plugin's root is
  not loaded as context.
- `CONTRIBUTING.md` and this changelog.

## [0.4.1] - 2026-05-11

### Added
- Voice card injection for voice-sensitive agents.
- Skill-queue CLI.

## [0.4.0] - 2026-05-10

### Added
- Brain outcome flywheel: recall before each agent call, outcome backfill.
- Lemlist connector, HMAC-verified webhook receiver, multi-tenant runs,
  tasks, evals and secrets.

## [0.3.0] - 2026-05-10

### Added
- Real connectors and pipelines: HubSpot CRM writes and Slack DMs, with the
  weekly-review and inbound-triage pipelines end to end.

## [0.2.0] - 2026-05-10

### Added
- Executable Python runtime (`gtmos`) and security hardening: Slack
  signature verification, slug and path validation, secret redaction.

## [0.1.0] - 2026-05-10

### Added
- Five-layer doctrine, five reference agents and their evals.

[Unreleased]: https://github.com/Kai8karma/gtm-agency-os-starter/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/Kai8karma/gtm-agency-os-starter/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/Kai8karma/gtm-agency-os-starter/releases/tag/v0.4.0
