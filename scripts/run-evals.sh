#!/usr/bin/env bash
# run-evals.sh — runs eval YAMLs against fixtures.
#
# This is a TEMPLATE runner. It performs structural checks (file pairing,
# YAML well-formedness, fixture count, threshold sanity) and emits a result
# summary. To wire actual LLM judging, install your judge runtime and
# replace the JUDGE_STUB section.
#
# Usage:
#   scripts/run-evals.sh              # all agents
#   scripts/run-evals.sh weekly-review  # one agent
#
# Exit 0 only if every requested eval passes structural + (if wired) judge checks.

set -euo pipefail

cd "$(dirname "$0")/.."

target="${1:-all}"

if [[ "$target" == "all" ]]; then
  agents=$(ls agents/*.md 2>/dev/null | xargs -n1 basename | sed 's/\.md$//')
else
  agents="$target"
fi

if [[ -z "$agents" ]]; then
  echo "✗ No agents found in agents/"
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "✗ python3 required to run evals"
  exit 2
fi

python3 - "$@" <<PY
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
print(f"eval: running {len(agents)} agent(s)")
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

    # === JUDGE_STUB ===========================================================
    # Replace this block with your actual LLM judge invocation.
    # For the starter template, structural pass = eval pass.
    score = 8.5 if not issues else 0.0
    judged = "structural"
    # ==========================================================================

    if issues:
        print(f"  ✗ {a}: {'; '.join(issues)}")
        failures += 1
    else:
        print(f"  ✓ {a}: {len(fixtures)} fixtures, threshold {threshold}, score {score} ({judged})")

print()
if failures == 0:
    print(f"eval: PASS ({len(agents)} agent(s))")
    sys.exit(0)
else:
    print(f"eval: FAIL ({failures} issue(s))")
    sys.exit(1)
PY
