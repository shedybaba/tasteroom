#!/usr/bin/env bash
# Pre-push safety check. Looks for the VALUES of the keys in .env (never prints them) in:
#   1. files tracked by git or staged   2. the entire git history   3. the built frontend bundle
# Also confirms .env is ignored and untracked. Exit code 1 if anything is found.
set -u
cd "$(dirname "$0")/.."
fail=0

[ -f .env ] || { echo "No .env found: nothing to check against."; exit 0; }
git check-ignore -q .env || { echo "FAIL: .env is NOT git-ignored"; fail=1; }
git ls-files --error-unmatch .env >/dev/null 2>&1 && { echo "FAIL: .env is tracked by git"; fail=1; }

# values of secret-looking variables (KEY / SECRET / TOKEN), quotes and spaces stripped
values=$(grep -E '^[A-Za-z_]*(KEY|SECRET|TOKEN)[A-Za-z_]*[[:space:]]*=' .env | cut -d= -f2- | tr -d ' "'"'" | awk 'length($0) >= 8')
n=0
while IFS= read -r v; do
  [ -z "$v" ] && continue
  n=$((n + 1))
  git grep -qF -- "$v" $(git rev-list --all 2>/dev/null | head -200) -- . 2>/dev/null && { echo "FAIL: secret #$n found in git history/tracked files"; fail=1; }
  git grep --cached -qF -- "$v" 2>/dev/null && { echo "FAIL: secret #$n found in staged files"; fail=1; }
  [ -d frontend/dist ] && grep -rqF -- "$v" frontend/dist 2>/dev/null && { echo "FAIL: secret #$n found in frontend/dist"; fail=1; }
done <<< "$values"

[ "$fail" -eq 0 ] && echo "OK: checked $n secret value(s) against tracked files, history and the frontend bundle; .env is ignored and untracked."
exit $fail
