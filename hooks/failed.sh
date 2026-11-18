#!/bin/sh
# broom's hook for a Bash command that failed (PostToolUseFailure): it notes a failed test run, for the turn's end to find.
# A command that can't be a test run leaves here, before Python starts, as in commit.sh.
here=${0%/*}
[ "$here" = "$0" ] && here=.
input=$(cat)
. "$here/maytest.sh"
may_test "$input" || exit 0
printf '%s' "$input" | exec "$here/../bin/broom" hook test-failed
