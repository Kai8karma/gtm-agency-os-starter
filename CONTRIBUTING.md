# Contributing

Read [`CLAUDE.md`](./CLAUDE.md) first. It is the doctrine this repository
encodes, and it overrides this file where they differ.

## Set up

```bash
git clone https://github.com/Kai8karma/gtm-agency-os-starter && cd gtm-agency-os-starter
make install          # creates .venv and installs gtmos in editable mode
cp .env.example .env  # optional: everything below runs without keys
```

## The gates

Every pull request has to pass these. They are the same commands CI runs.

```bash
make verify      # doctrine self-checks: CLAUDE.md shape, every agent has an eval
make eval        # agents against their fixtures; offline unless ANTHROPIC_API_KEY is set
make test-cov    # pytest, fails under 80% coverage
make security    # bandit, pip-audit, ruff (and gitleaks if installed)
```

Coverage sits just above the 80% floor. New code needs tests, or the gate
fails for whoever comes next.

## Rules of the road

- **An agent and its eval change together.** `agents/<name>.md` without a
  matching `evals/<name>.yaml` fails `make verify`. If you change what an
  agent should do, add or update a fixture that would have caught the old
  behaviour.
- **No secret in a log or an error.** Route anything that might carry one
  through `gtmos.security.redact`.
- **Paths from outside go through `safe_join` and `validate_slug`.** Client
  slugs and run artifact paths are untrusted input.
- **Stubs fail closed.** A connector that is not wired raises
  `ConnectorUnavailable`. Do not return empty results from a stub.
- **Pin tooling that gates CI.** The linter is pinned on purpose; raise the
  version in `pyproject.toml` and `.github/workflows/security.yml` in the
  same pull request, and fix what it finds.

## Adding things

- **An agent:** `agents/<name>.md`, `evals/<name>.yaml`, and an entry under
  `metadata.runtimeAgents` in `.claude-plugin/plugin.json`.
- **A connector:** subclass the base in `gtmos/connectors/base.py`, cover
  it with `respx` tests, and add a row to the "wired vs. stubbed" table in
  the README. The table and the file tree must agree.
- **A per-engagement override:** `docs/STACK_OVERRIDES.md`, not a change to
  the defaults.

## Forking for your own agency

The brain flywheel (`gtmos/brain.py`) shells out to a `brain` CLI that is
not part of this repository. Without it the pipelines still run and skip
the recall step. `gtmos/skill_bridge.py` names Claude Code skills you may
not have installed; it only queues them. Neither is required to use the
doctrine, the agents or the evals.

## Security

See [`SECURITY.md`](./SECURITY.md). Please report vulnerabilities
privately.
