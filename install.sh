#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' "Python 3.9+ is required. Install python3 using your OS package manager first." >&2
    exit 1
fi
exec python3 "$repo_dir/scripts/install.py" "$@"
