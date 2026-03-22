#!/bin/zsh
set -euo pipefail
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
source "$(dirname "$0")/_prelude.sh"
exec /usr/bin/env python3 -m app.cli notify "$@"
