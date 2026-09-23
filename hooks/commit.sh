#!/bin/sh
# broom's commit hook sees every Bash call, because Claude Code's `if` patterns can't match commands like
# `T=~/repo; git -C $T commit`. Input that can't hold a commit leaves here, before Python starts: most Bash calls
# cost a shell start (about 12 ms) instead of an interpreter start (about 33 ms on macOS's system Python).
# bin/broom then reads the command itself and filters precisely.
input=$(cat)
case $input in
  *git*commit* | *commit*git*) ;;
  *) exit 0 ;;
esac
printf '%s' "$input" | exec "$(dirname "$0")/../bin/broom" hook commit
