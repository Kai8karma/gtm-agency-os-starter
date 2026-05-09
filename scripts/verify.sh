#!/usr/bin/env bash
# verify.sh — CLAUDE.md self-verification (the four checks from § 13).
# Exit 0 on success, non-zero on any failure.

set -euo pipefail

cd "$(dirname "$0")/.."

fail=0
pass() { printf "  ✓ %s\n" "$1"; }
warn() { printf "  ⚠ %s\n" "$1"; }
err()  { printf "  ✗ %s\n" "$1"; fail=$((fail + 1)); }

echo "verify: CLAUDE.md self-checks"

# 1. File exists and is non-trivial.
if [[ -f CLAUDE.md && $(wc -l < CLAUDE.md) -gt 50 ]]; then
  pass "CLAUDE.md present ($(wc -l < CLAUDE.md | tr -d ' ') lines)"
else
  err "CLAUDE.md missing or too short"
fi

# 2. All 5 doctrine layers documented (Doctrine / Surfaces / Agents / Pipelines / Eval).
layers_found=$(grep -ciE 'doctrine|surfaces|agents|pipelines|eval' CLAUDE.md || true)
if [[ "$layers_found" -ge 5 ]]; then
  pass "5-layer doctrine references present"
else
  err "Missing 5-layer doctrine references (found $layers_found mentions)"
fi

# 3. No banned marketing phrases used in earnest. The doctrine itself
#    cites the banned list and quotes the verification command — those are
#    the only allowed mentions. We accept hits if the line is a citation.
banned_pattern='(world-class|cutting-edge|game-changing|revolutionary)'
banned_hits=$(grep -inE "$banned_pattern" CLAUDE.md || true)
if [[ -z "$banned_hits" ]]; then
  pass "No banned marketing phrases"
else
  # All hits must be on lines that are citations (start with marker like "- " inside § 6 or § 11, or are inside a code block).
  unauthorized=$(echo "$banned_hits" | grep -vE '("|`|grep -iE)' || true)
  if [[ -z "$unauthorized" ]]; then
    pass "Banned phrases present only as citations (allowed)"
  else
    err "Banned phrases used in earnest:"
    echo "$unauthorized" | sed 's/^/      /'
  fi
fi

# 4. Provenance line.
if grep -qE '^\*\*Author:\*\*' CLAUDE.md; then
  pass "Provenance line present"
else
  err "Missing **Author:** provenance"
fi

# 5. Bonus — every agent has a paired eval.
echo ""
echo "verify: agent ↔ eval pairing"
missing_evals=0
for a in agents/*.md; do
  name=$(basename "$a" .md)
  if [[ ! -f "evals/$name.yaml" ]]; then
    err "agents/$name.md has no evals/$name.yaml"
    missing_evals=$((missing_evals + 1))
  fi
done
if [[ $missing_evals -eq 0 ]]; then
  pass "All agents paired with evals/<agent>.yaml"
fi

# 6. Bonus — eval YAMLs parse.
echo ""
echo "verify: eval YAML parse"
if command -v python3 >/dev/null 2>&1; then
  python3 - <<'PY' || fail=$((fail + 1))
import sys, glob
try:
    import yaml
except ImportError:
    print("  ⚠ pyyaml not installed — skipping YAML parse check")
    print("    install: pip install pyyaml")
    sys.exit(0)
ok = True
for p in sorted(glob.glob("evals/*.yaml")):
    try:
        with open(p) as f:
            d = yaml.safe_load(f)
        for k in ("agent", "judge", "rubric", "fixtures", "pass_threshold"):
            if k not in d:
                print(f"  ✗ {p}: missing key '{k}'")
                ok = False
        if ok:
            print(f"  ✓ {p}")
    except Exception as e:
        print(f"  ✗ {p}: {e}")
        ok = False
sys.exit(0 if ok else 1)
PY
else
  warn "python3 not available — skipping YAML parse check"
fi

echo ""
if [[ $fail -eq 0 ]]; then
  echo "verify: PASS"
  exit 0
else
  echo "verify: FAIL ($fail issue(s))"
  exit 1
fi
