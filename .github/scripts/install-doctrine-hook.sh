#!/usr/bin/env bash
# install-doctrine-hook.sh — install the doctrine pre-check as a git pre-commit
# hook in the current repo. Advisory: warns/blocks locally before push; the
# authoritative gate remains the CI workflow doctrine-check.yml.
#
# Usage:  bash .github/scripts/install-doctrine-hook.sh
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
HOOK="$ROOT/.git/hooks/pre-commit"
SCRIPT_REL=".github/scripts/doctrine_precommit.sh"

if [ ! -f "$ROOT/$SCRIPT_REL" ]; then
  echo "doctrine_precommit.sh not found at $SCRIPT_REL — copy it into this repo first." >&2
  exit 1
fi

cat > "$HOOK" <<'HOOK_EOF'
#!/usr/bin/env bash
# SZL doctrine pre-commit hook (advisory). Set DOCTRINE_SKIP=1 to bypass.
[ "${DOCTRINE_SKIP:-0}" = "1" ] && exit 0
ROOT="$(git rev-parse --show-toplevel)"
if [ -x "$ROOT/.github/scripts/doctrine_precommit.sh" ]; then
  bash "$ROOT/.github/scripts/doctrine_precommit.sh" --staged || {
    echo ""
    echo "Commit blocked by doctrine pre-check. Fix the overclaim, or bypass with: DOCTRINE_SKIP=1 git commit ..."
    exit 1
  }
fi
HOOK_EOF
chmod +x "$HOOK"
echo "✓ installed doctrine pre-commit hook at .git/hooks/pre-commit"
echo "  bypass once with: DOCTRINE_SKIP=1 git commit ..."
