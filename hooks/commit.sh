#!/bin/sh
# broom's commit hook sees every Bash call, because Claude Code's `if` patterns can't match commands like
# `T=~/repo; git -C $T commit`. It also notes a command that runs tests, for the turn's end to find. Input that can be
# neither a commit nor a test run leaves here, before Python starts: most Bash calls cost a shell start (about 12 ms)
# instead of an interpreter start (about 33 ms on macOS's system Python). bin/broom then reads the command itself and
# filters precisely.
here=${0%/*}
[ "$here" = "$0" ] && here=.
input=$(cat)
case $input in
  *git*commit* | *commit*git*) ;;
  *)
    . "$here/maytest.sh"
    may_test "$input" || exit 0
    ;;
esac
printf '%s' "$input" | exec "$here/../bin/broom" hook commit
