# shellcheck shell=zsh
# Sourced by all household wrapper scripts. Sets up VAULT_ROOT and PYTHONPATH.
source "$(dirname "$0")/config.sh"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FALLBACK_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ ! -d "$VAULT_ROOT" || ! -r "$VAULT_ROOT" ]]; then
    export VAULT_ROOT="$FALLBACK_ROOT"
fi
cd "$VAULT_ROOT"
export PYTHONPATH="$VAULT_ROOT:${PYTHONPATH:-}"
