#!/bin/sh
# python3가 없거나 실패해도 사용자 입력을 막지 않도록 항상 0으로 끝난다.
HERE=$(cd "$(dirname "$0")" && pwd)
PY=$(command -v python3) || exit 0
"$PY" "$HERE/criteria_hook.py" || exit 0
exit 0
