#!/bin/zsh
set -euo pipefail
source "$(dirname "$0")/_prelude.sh"
exec /usr/bin/env python3 -m app.cli automation "$@"
