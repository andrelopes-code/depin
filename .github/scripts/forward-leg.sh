#!/usr/bin/env bash
# One leg of `typing-forward`: run the suite against $VERSION of $CHECKER and
# leave behind what the reporting job needs, whether or not it passed.
#
# The exit status is preserved, so a failing leg shows as failed in the run.
# The job carries `continue-on-error`, so it does not fail the workflow.
set -uo pipefail

mkdir -p forward-report

if [ "${SOURCE:-0}" = '1' ]; then
  set -- --source --checker "$CHECKER" --pin "$CHECKER=$VERSION"
else
  set -- --checker "$CHECKER" --pin "$CHECKER=$VERSION" --target-python "$TARGET"
fi

uv run --locked python -m scripts.conformance "$@" >forward-report/run.log 2>&1
status=$?

cat forward-report/run.log

{
  echo "checker=$CHECKER"
  echo "version=$VERSION"
  echo "leg=$LEG"
  echo "status=$status"
} >forward-report/meta.env

exit "$status"
