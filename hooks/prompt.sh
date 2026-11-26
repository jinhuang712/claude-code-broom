#!/bin/sh
# broom's synchronous prompt hook (UserPromptSubmit). After Claude put a question to the user with `broom known --ask`,
# the next prompt holds the answer, and Claude must be told then which findings it asked about: an async hook's output
# would reach Claude only on a later turn. A question leaves answer-due.jsonl in the session's directory; while there is
# none, this leaves before Python starts, so a prompt costs a shell start and one file test.
here=${0%/*}
[ "$here" = "$0" ] && here=.
input=$(cat)
. "$here/maytest.sh"
json_field "$input" session_id
data=${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/broom-claude-code-broom}
[ -f "$data/sessions/$value/answer-due.jsonl" ] || exit 0
printf '%s' "$input" | exec "$here/../bin/broom" hook answer
