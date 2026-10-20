#!/bin/sh
# criteria 로컬 웹을 시작한다. 인자는 criteria_web.py로 그대로 넘긴다.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
PY=$(command -v python3 || true)
if [ -z "$PY" ] || ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'; then
  echo "python3 (3.8 이상)가 필요합니다. macOS: xcode-select --install 또는 brew install python" >&2
  exit 127
fi
exec "$PY" "$HERE/criteria_web.py" "$@"
