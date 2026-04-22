#!/usr/bin/env bash
# Dispatch `nkd` in parallel on each open `agent:ready` issue without an open PR.
# Env: ANTHROPIC_API_KEY, GH_TOKEN. Optional: REPO, NKD_MODEL, PER_ISSUE_TIMEOUT.
set -euo pipefail

REPO="${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
: "${NKD_MODEL:=claude-sonnet-4-6}" "${PER_ISSUE_TIMEOUT:=45m}"

for ISSUE in $(gh issue list --repo "$REPO" --label agent:ready --state open --json number --jq '.[].number'); do
  n=$(gh api "repos/$REPO/issues/$ISSUE/timeline" --paginate \
        --jq '[.[]|select(.event=="cross-referenced" and .source.issue.pull_request!=null and .source.issue.state=="open")]|length' \
        | awk '{s+=$1} END{print s+0}')
  if [[ "$n" -gt 0 ]]; then echo "#$ISSUE: skip (open PR exists)"; continue; fi
  echo "#$ISSUE: dispatching"
  PROMPT="Resolve issue #$ISSUE in $REPO. Follow skills/issue_to_pr/SKILL.md."
  timeout "$PER_ISSUE_TIMEOUT" docker run --rm \
    -e ANTHROPIC_API_KEY -e GH_TOKEN -e NKD_MODEL -e PROMPT -e REPO \
    nkd-agents:issues bash -lc '
      git config --global user.name  nkd-agent
      git config --global user.email nkd-agent@users.noreply.github.com
      gh auth setup-git && gh repo clone "$REPO" /work && cd /work && nkd -p "$PROMPT"
    ' &> "/tmp/worker-$ISSUE.log" &
done
wait
