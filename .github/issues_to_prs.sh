#!/usr/bin/env bash
# Find open issues labeled `agent:ready` with no PR referencing them,
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
LOC_CEILING="${LOC_CEILING:-300}"
NKD_IMAGE="${NKD_IMAGE:-nkd-agents:issues}"
NKD_MODEL="${NKD_MODEL:-claude-opus-4-7}"
PER_ISSUE_TIMEOUT="${PER_ISSUE_TIMEOUT:-45m}"
PROMPT_FILE=".github/nkd/issue_to_pr.md"

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "missing $PROMPT_FILE" >&2
  exit 1
fi

echo "repo=$REPO loc_ceiling=$LOC_CEILING image=$NKD_IMAGE"

mapfile -t ISSUES < <(
  gh issue list --repo "$REPO" \
    --label "agent:ready" --state open \
    --json number --jq '.[].number'
)

if [[ ${#ISSUES[@]} -eq 0 ]]; then
  echo "no agent:ready issues"
  exit 0
fi

run_issue() {
  local N="$1"

  # Skip if an *open* PR already references this issue. Closed-unmerged PRs
  # leave timeline events behind; we want those issues re-picked up. Merged
  # PRs that close the issue drop it from `--state open` already.
  local HAS_PR
  HAS_PR=$(
    gh api -H "Accept: application/vnd.github+json" \
      "repos/$REPO/issues/$N/timeline" --paginate \
      --jq '[.[] | select(
              .event == "cross-referenced"
              and .source.issue.pull_request != null
              and .source.issue.state == "open"
            )] | length'
  )
  if [[ "${HAS_PR:-0}" -gt 0 ]]; then
    echo "issue #$N: skip (open PR already references it)"
    return 0
  fi

  local TITLE SLUG LOG PROMPT
  TITLE=$(gh issue view "$N" --repo "$REPO" --json title --jq .title)
  SLUG=$(
    echo "$TITLE" \
      | tr '[:upper:]' '[:lower:]' \
      | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$//g' \
      | cut -c1-40
  )
  SLUG="${SLUG:-issue-$N}-$N"
  LOG="/tmp/worker-$SLUG.log"

  echo "issue #$N: dispatching (slug=$SLUG)"

  PROMPT=$(
    cat <<EOF
REPO=$REPO
ISSUE=$N
SLUG=$SLUG
LOC_CEILING=$LOC_CEILING

$(cat "$PROMPT_FILE")
EOF
  )

  # One container per issue. Don't let one failure take down the batch.
  timeout "$PER_ISSUE_TIMEOUT" docker run --rm \
    -v "$PWD:/workspace" \
    -w /workspace \
    -e ANTHROPIC_API_KEY \
    -e GH_TOKEN \
    -e GITHUB_TOKEN="$GH_TOKEN" \
    -e NKD_MODEL="$NKD_MODEL" \
    -e NKD_LOG_LEVEL=20 \
    -e PROMPT="$PROMPT" \
    "$NKD_IMAGE" \
    bash -lc '
      git config --global user.name  "nkd-agents-bot"
      git config --global user.email "nkd-agents-bot@users.noreply.github.com"
      gh auth setup-git
      nkd -p "$PROMPT"
    ' > "$LOG" 2>&1 \
    || echo "issue #$N: worker exited non-zero (see $LOG)"
}

# Dispatch all issues in parallel; wait for all to finish.
for N in "${ISSUES[@]}"; do
  run_issue "$N" &
done
wait