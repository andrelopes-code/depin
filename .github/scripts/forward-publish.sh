#!/usr/bin/env bash
# Open, or comment on, one tracking issue per checker and version.
#
# The title carries both, so a checker that failed on four legs is one thread
# and a later release opens a new one rather than burying the earlier evidence.
# An existing open issue is commented on rather than replaced: the history of
# which releases were red is the evidence the support policy draws on.
set -euo pipefail

index='forward-issues/index.tsv'
if [ ! -s "$index" ]; then
  echo 'every leg passed; no tracking issue to open'
  exit 0
fi

while IFS=$'\t' read -r checker version body; do
  title="typing-forward: $checker $version"
  number="$(
    gh issue list --state open --search "$title in:title" --limit 50 --json number,title \
      --jq "map(select(.title == \"$title\")) | .[0].number // empty"
  )"
  if [ -n "$number" ]; then
    echo "updating #$number — $title"
    gh issue comment "$number" --body-file "$body"
  else
    echo "opening — $title"
    gh issue create --title "$title" --body-file "$body"
  fi
done <"$index"
