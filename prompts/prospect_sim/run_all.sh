#!/usr/bin/env bash
# Run all prospect_sim evals. Each is a single-responsibility binary check.
# Usage: bash prompts/prospect_sim/run_all.sh [--model MODEL]

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$(cd "$SCRIPT_DIR/../.." && pwd)/skills/prompt_eval/run.py"
MODEL_ARG=("$@")

EVALS=(
  character_break
  premature_capitulation
  phantom_objection
  persona_inconsistency
  stage_directions
  excessive_cooperation
)

PASSED=0
FAILED=0
FAILED_EVALS=()

for eval in "${EVALS[@]}"; do
  echo "━━━ $eval ━━━"
  if python "$RUNNER" "$SCRIPT_DIR/$eval" "${MODEL_ARG[@]}"; then
    PASSED=$((PASSED + 1))
  else
    FAILED=$((FAILED + 1))
    FAILED_EVALS+=("$eval")
  fi
  echo ""
done

echo "════════════════════════════"
echo "Evals passed: $PASSED / $((PASSED + FAILED))"
if [ ${#FAILED_EVALS[@]} -gt 0 ]; then
  echo "Failed: ${FAILED_EVALS[*]}"
  exit 1
fi