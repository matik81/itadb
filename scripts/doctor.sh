#!/usr/bin/env bash
# Read-only Linux toolchain checks; never print host paths or credentials.
set -uo pipefail
status=0
check() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    printf 'OK     %s\n' "$label"
  else
    printf 'ERRORE %s\n' "$label"
    status=1
  fi
}
check 'Sistema Linux' test "$(uname -s)" = Linux
check 'Git' git --version
check 'uv' uv --version
check 'Python 3.13 gestibile da uv (senza download)' uv python find --no-python-downloads 3.13
check 'Node.js 24' node -e 'process.exit(Number(process.versions.node.split(".")[0]) === 24 ? 0 : 1)'
check 'npm' npm --version
check 'Docker Engine raggiungibile' docker info
check 'Docker Compose' docker compose version
if command -v gh >/dev/null 2>&1; then
  printf 'OK     GitHub CLI (facoltativa)\n'
else
  printf 'INFO   GitHub CLI assente (facoltativa)\n'
fi
exit "$status"
