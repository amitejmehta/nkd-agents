#!/usr/bin/env bash
# Find open issues labeled `agent:ready` with no open PR referencing them,
# and dispatch `nkd -p` (headless, inside Docker) on each to turn them into PRs.
#
# Required env:
#   ANTHROPIC_API_KEY   Anthropic key
#   GH_TOKEN            GitHub token with contents:write + pull-requests:write
# Optional env:
#   REPO                default: inferred from `gh repo view`
#   LOC_CEILING         default: 300
#   NKD_IMAGE           default: nkd-agents:issues
#   NKD_MODEL           default: claude-opus-4-7
#   PER_ISSUE_TIMEOUT   default: 45m

set -euo pipefail

REPO="${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
: "${LOC_CEILING:=300}" "${NKD_IMAGE:=nkd-agents:issues}" "${NKD_MODEL:=claude-sonnet-4-6}" "${PER_ISSUE_TIMEOUT:=45m}"
BASE_PROMPT=$(cat .github/nkd/issue_to_pr.md)

has_open_pr() {
  local N=$1
  local n
  n=$(gh api -H "Accept: application/vnd.github+json" \
        "repos/$REPO/issues/$N/timeline" --paginate \
        --jq '[.[] | select(.event=="cross-referenced"
                            and .source.issue.pull_request!=null
                            and .source.issue.state=="open")] | length')
  [[ "${n:-0}" -gt 0 ]]
}

run_issue() {
  local N=$1 LOG="/tmp/worker-$1.log"
  if has_open_pr "$N"; then
    echo "issue #$N: skip (open PR already references it)"
    return 0
  fi
  echo "issue #$N: dispatching"
  local PROMPT="REPO=$REPO
ISSUE=$N
LOC_CEILING=$LOC_CEILING

$BASE_PROMPT"
  timeout "$PER_ISSUE_TIMEOUT" docker run --rm \
    -e ANTHROPIC_API_KEY -e GH_TOKEN -e NKD_MODEL -e PROMPT -e REPO \
    "$NKD_IMAGE" bash -lc '
      git config --global user.name  nkd-agent
      git config --global user.email nkd-agent@users.noreply.github.com
      gh auth setup-git
      gh repo clone "$REPO" /work && cd /work
      nkd -p "$PROMPT"
    ' &> "$LOG" || echo "issue #$N: worker exited non-zero (see $LOG)"
}

mapfile -t ISSUES < <(
  gh issue list --repo "$REPO" --label agent:ready --state open \
    --json number --jq '.[].number'
)
[[ ${#ISSUES[@]} -eq 0 ]] && { echo "no agent:ready issues"; exit 0; }

echo "repo=$REPO issues=${#ISSUES[@]} image=$NKD_IMAGE"
for N in "${ISSUES[@]}"; do run_issue "$N" & done
wait