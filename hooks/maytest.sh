# Whether a Bash call can be a test run, for hooks/commit.sh and hooks/failed.sh, which leave before Python starts when it
# cannot. Sourced, and made of what the shell does itself (parameter expansion, case, read), so it starts no process.
#
# It is a prefilter: it may say yes to a command that is none (`ls tests/`), and Python then reads the command's words;
# it must never say no to a test run. So it looks for the runners' own words in the command alone (the cwd and the
# transcript's path are no part of it), and in a repo that names test commands of its own in .broom.json it says yes to
# every call, since those words are not known here.

# The text of the JSON field $2 of the input $1 up to its closing quote, in `value`: the whole input when there is none.
# Claude Code writes JSON with no spaces; a space after the colon is read too.
json_field() {
  value=${1#*\"$2\":\"}
  [ "$value" = "$1" ] && value=${1#*\"$2\": \"}
  value=${value%%\"*}
}

may_test() {
  # the command runs to the first quote that ends a field: a quote inside it is escaped, so `","` never occurs in it
  cmd=${1#*\"command\":\"}
  [ "$cmd" = "$1" ] && cmd=${1#*\"command\": \"}
  cmd=${cmd%%\",\"*}
  cmd=${cmd%%\", \"*}
  case $cmd in
    *test* | *tox* | *nox* | *jest* | *mocha*) return 0 ;;
  esac
  repo_names_tests "$1"
}

# Whether the .broom.json of the repo the call runs in (a linked worktree reads the main worktree's) has test_commands.
repo_names_tests() {
  json_field "$1" cwd
  dir=$value
  while [ -n "$dir" ]; do
    if [ -e "$dir/.git" ]; then
      file=$dir/.broom.json
      if [ ! -f "$file" ] && [ -f "$dir/.git" ]; then
        read -r pointer < "$dir/.git"
        pointer=${pointer#gitdir: }
        file=${pointer%%/.git/worktrees/*}/.broom.json
      fi
      [ -f "$file" ] || return 1
      while IFS= read -r row || [ -n "$row" ]; do
        case $row in *'"test_commands"'*) return 0 ;; esac
      done < "$file"
      return 1
    fi
    case $dir in */*) dir=${dir%/*} ;; *) return 1 ;; esac
  done
  return 1
}
