#!/usr/bin/env bash
# Dispatch `nkd` in parallel on each open `agent:ready` issue without an open PR.
# Env: ANTHROPIC_API_KEY, GH_TOKEN. Optional: REPO, NKD_MODEL, PER_ISSUE_TIMEOUT.
set -euo pipefail

REPO="${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
: "${NKD_MODEL:=claude-sonnet-4-6}" "${PER_ISSUE_TIMEOUT:=45m}"
PROMPT=$(cat .github/nkd/issue_to_pr.md)

for ISSUE in $(gh issue list --repo "$REPO" --label agent:ready --state open --json number --jq '.[].number'); do
  n=$(gh api "repos/$REPO/issues/$ISSUE/timeline" --paginate \
        --jq '[.[]|select(.event=="cross-referenced" and .source.issue.pull_request!=null and .source.issue.state=="open")]|length' \
        | awk '{s+=$1} END{print s+0}')
  if [[ "$n" -gt 0 ]]; then echo "#$ISSUE: skip (open PR exists)"; continue; fi
  echo "#$ISSUE: dispatching"
  ISSUE=$ISSUE timeout "$PER_ISSUE_TIMEOUT" docker run --rm \
    -e ANTHROPIC_API_KEY -e GH_TOKEN -e NKD_MODEL -e PROMPT -e REPO -e ISSUE \
    nkd-agents:issues bash -lc '
      git config --global user.name  nkd-agent
      git config --global user.email nkd-agent@users.noreply.github.com
      gh auth setup-git && gh repo clone "$REPO" /work && cd /work && nkd -p "$PROMPT"
    ' &> "/tmp/worker-$ISSUE.log" &
done
wait
