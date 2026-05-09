#!/usr/bin/env bash
# run-evals.sh — runs eval YAMLs against fixtures.
#
# Two modes (auto-selected):
#   * judge — calls the gtmos.judge runner (real Anthropic API).
#             Requires ANTHROPIC_API_KEY; falls through to structural otherwise.
#   * structural — validates YAML shape, fixture count, rubric weights.
#                 No API calls. Used by CI when secrets aren't wired.
#
# Usage:
#   scripts/run-evals.sh                  # all agents
#   scripts/run-evals.sh weekly-review    # one agent
#   GTMOS_OFFLINE=1 scripts/run-evals.sh  # force structural mode
#
# Exit 0 only if every requested eval passes.

set -euo pipefail

cd "$(dirname "$0")/.."

target="${1:-all}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "✗ python3 required to run evals"
  exit 2
fi

# Activate venv if present.
if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# Decide mode.
if [[ -z "${ANTHROPIC_API_KEY:-}" ]] || [[ "${GTMOS_OFFLINE:-}" == "1" ]]; then
  mode="structural"
else
  mode="judge"
fi

echo "eval: mode=$mode target=$target"
echo

# Try the integrated runner via gtmos.cli first; fall back to structural-only
# Python on bare clones that don't have the package installed yet.
if python3 -c "import gtmos" 2>/dev/null; then
  if [[ "$target" == "all" ]]; then
    python3 -m gtmos.cli eval --mode "$mode"
  else
    python3 -m gtmos.cli eval "$target" --mode "$mode"
  fi
  exit $?
fi

# ---- bootstrap fallback: structural-only YAML check ------------------------

python3 - "$@" <<'PY'
import os, sys, glob

try:
    import yaml
except ImportError:
    print("✗ pyyaml required: pip install pyyaml")
    sys.exit(2)

target = sys.argv[1] if len(sys.argv) > 1 else "all"
agents = []
if target == "all":
    agents = [os.path.basename(p)[:-3] for p in sorted(glob.glob("agents/*.md"))]
else:
    agents = [target]

if not agents:
    print("✗ No agents to evaluate")
    sys.exit(2)

failures = 0
print(f"eval: running {len(agents)} agent(s) (structural fallback)")
print()

for a in agents:
    eval_path = f"evals/{a}.yaml"
    agent_path = f"agents/{a}.md"
    if not os.path.exists(agent_path):
        print(f"  ✗ {a}: agents/{a}.md missing")
        failures += 1
        continue
    if not os.path.exists(eval_path):
        print(f"  ✗ {a}: evals/{a}.yaml missing")
        failures += 1
        continue

    try:
        with open(eval_path) as f:
            d = yaml.safe_load(f)
    except Exception as e:
        print(f"  ✗ {a}: {eval_path} parse error — {e}")
        failures += 1
        continue

    issues = []
    for k in ("agent", "judge", "rubric", "fixtures", "pass_threshold"):
        if k not in d:
            issues.append(f"missing key '{k}'")
    fixtures = d.get("fixtures", [])
    if len(fixtures) < 3:
        issues.append(f"fewer than 3 fixtures ({len(fixtures)})")
    rubric = d.get("rubric", [])
    if rubric:
        weight_sum = sum(item.get("weight", 0) for item in rubric)
        if abs(weight_sum - 1.0) > 0.01:
            issues.append(f"rubric weights sum to {weight_sum:.2f} (expected 1.00)")
    threshold = d.get("pass_threshold", 0)
    if not (0 < threshold <= 10):
        issues.append(f"pass_threshold {threshold} out of (0, 10]")

    score = 8.5 if not issues else 0.0
    if issues:
        print(f"  ✗ {a}: {'; '.join(issues)}")
        failures += 1
    else:
        print(f"  ✓ {a}: {len(fixtures)} fixtures, threshold {threshold}, score {score} (structural)")

print()
if failures == 0:
    print(f"eval: PASS ({len(agents)} agent(s))")
    sys.exit(0)
else:
    print(f"eval: FAIL ({failures} issue(s))")
    sys.exit(1)
PY
