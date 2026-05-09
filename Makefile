.DEFAULT_GOAL := help
.PHONY: help install verify eval eval-% test test-cov lint format security \
        bandit pip-audit gitleaks docker docker-build new-client clean status

# ---- Config -----------------------------------------------------------------

AGENTS := $(notdir $(basename $(wildcard agents/*.md)))
EVALS  := $(addprefix eval-,$(AGENTS))
PYTHON ?= python3
VENV   ?= .venv

# ---- Targets ----------------------------------------------------------------

help:
	@echo "GTM Agency OS — make targets"
	@echo ""
	@echo "  Setup:"
	@echo "    make install              Create .venv and install dev deps via uv (or pip)"
	@echo ""
	@echo "  Verify + eval (CI gates):"
	@echo "    make verify               Doctrine self-checks + agent/eval pairing"
	@echo "    make eval                 Run all agent evals (auto: judge if API key set, else structural)"
	@echo "    make eval-<agent>         Run a single agent's evals"
	@echo "    make test                 Run pytest"
	@echo "    make test-cov             pytest with coverage; fails < 80%"
	@echo ""
	@echo "  Security:"
	@echo "    make security             bandit + pip-audit + ruff + gitleaks (if installed)"
	@echo "    make bandit               static security scan of gtmos/"
	@echo "    make pip-audit            CVE scan of installed deps"
	@echo "    make gitleaks             secret scan of full git history (needs gitleaks installed)"
	@echo ""
	@echo "  Hygiene:"
	@echo "    make lint                 ruff lint"
	@echo "    make format               ruff format"
	@echo ""
	@echo "  Operations:"
	@echo "    make new-client SLUG=x    Scaffold clients/<x>/ from clients/_example/"
	@echo "    make docker-build         Build the runtime container"
	@echo "    make status               Print repo health summary"
	@echo "    make clean                Remove transient run artifacts older than 30 days"
	@echo ""
	@echo "Agents detected: $(AGENTS)"

install:
	@if command -v uv >/dev/null 2>&1; then \
	  uv venv -p 3.12 $(VENV) && . $(VENV)/bin/activate && uv pip install -e '.[dev]' ; \
	else \
	  $(PYTHON) -m venv $(VENV) && . $(VENV)/bin/activate && pip install --upgrade pip && pip install -e '.[dev]' ; \
	fi
	@echo "✓ install complete: . $(VENV)/bin/activate"

verify:
	@bash scripts/verify.sh

eval: verify
	@bash scripts/run-evals.sh

eval-%:
	@bash scripts/run-evals.sh $*

test:
	@. $(VENV)/bin/activate 2>/dev/null && pytest -q -m "not integration" || pytest -q -m "not integration"

test-cov:
	@. $(VENV)/bin/activate 2>/dev/null && pytest -q -m "not integration" --cov=gtmos --cov-fail-under=80 || pytest -q -m "not integration" --cov=gtmos --cov-fail-under=80

lint:
	@. $(VENV)/bin/activate 2>/dev/null && ruff check gtmos tests || ruff check gtmos tests

format:
	@. $(VENV)/bin/activate 2>/dev/null && ruff format gtmos tests || ruff format gtmos tests

security: bandit pip-audit lint
	@command -v gitleaks >/dev/null 2>&1 && $(MAKE) gitleaks || echo "(skipping gitleaks — not installed; brew install gitleaks)"
	@echo "✓ security: PASS"

bandit:
	@. $(VENV)/bin/activate 2>/dev/null && bandit -r gtmos -c pyproject.toml --quiet || bandit -r gtmos -c pyproject.toml --quiet

pip-audit:
	@# Editable installs cause pip-audit to log a non-actionable warning;
	@# we drop --strict so the run only fails on real CVEs.
	@. $(VENV)/bin/activate 2>/dev/null && pip-audit --skip-editable || pip-audit --skip-editable

gitleaks:
	@gitleaks detect --redact --no-banner --source . --verbose

docker-build docker:
	@docker build -t gtm-agency-os:local .

new-client:
	@if [ -z "$(SLUG)" ]; then echo "ERROR: SLUG=<slug> required"; exit 2; fi
	@if [ -d "clients/$(SLUG)" ]; then echo "ERROR: clients/$(SLUG) already exists"; exit 2; fi
	@cp -R clients/_example clients/$(SLUG)
	@find clients/$(SLUG) -type f \( -name '*.md' \) -print0 | xargs -0 sed -i '' "s/_example/$(SLUG)/g"
	@echo "✓ Scaffolded clients/$(SLUG)/. Edit client.md before running anything."

status:
	@echo "Agents:   $(words $(AGENTS)) ($(AGENTS))"
	@echo "Evals:    $(words $(wildcard evals/*.yaml))"
	@echo "Routines: $(words $(wildcard routines/*.md))"
	@echo "Clients:  $(words $(filter-out clients/_example,$(wildcard clients/*)))"
	@echo "Runs:     $(words $(wildcard runs/*/*.md))"

clean:
	@find runs/ -type f -name '*.md' -mtime +30 -delete 2>/dev/null || true
	@echo "✓ Pruned run artifacts > 30 days."
