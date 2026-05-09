.DEFAULT_GOAL := help
.PHONY: help verify eval eval-% new-client clean status

# ---- Config ------------------------------------------------------------------

AGENTS := $(notdir $(basename $(wildcard agents/*.md)))
EVALS  := $(addprefix eval-,$(AGENTS))

# ---- Targets -----------------------------------------------------------------

help:
	@echo "GTM Agency OS — make targets"
	@echo ""
	@echo "  make verify              Run CLAUDE.md self-verification (4 checks)"
	@echo "  make eval                Run all agent evals (CI gate)"
	@echo "  make eval-<agent>        Run a single agent's evals (e.g., eval-weekly-review)"
	@echo "  make new-client SLUG=x   Scaffold clients/<x>/ from clients/_example/"
	@echo "  make status              Print repo health summary"
	@echo "  make clean               Remove transient run artifacts older than 30 days"
	@echo ""
	@echo "Agents detected: $(AGENTS)"

verify:
	@bash scripts/verify.sh

eval: verify
	@bash scripts/run-evals.sh

eval-%:
	@bash scripts/run-evals.sh $*

new-client:
	@if [ -z "$(SLUG)" ]; then echo "ERROR: SLUG=<slug> required"; exit 2; fi
	@if [ -d "clients/$(SLUG)" ]; then echo "ERROR: clients/$(SLUG) already exists"; exit 2; fi
	@cp -R clients/_example clients/$(SLUG)
	@sed -i '' "s/_example/$(SLUG)/g" clients/$(SLUG)/client.md clients/$(SLUG)/campaigns/*.md
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
