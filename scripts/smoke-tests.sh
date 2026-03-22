#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VAULT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$VAULT_ROOT"
export PYTHONPATH="$VAULT_ROOT:${PYTHONPATH:-}"

exec /usr/bin/env python3 -m unittest tests.test_smoke_automations -v
