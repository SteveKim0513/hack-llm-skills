#!/bin/sh
# 사전 점검용(선택). 설치할 패키지는 없고 python3 버전만 확인한다.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
PY=$(command -v python3 || true)
if [ -z "$PY" ] || ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'; then
  echo "python3 (3.8 이상)가 필요합니다. macOS: xcode-select --install 또는 brew install python" >&2
  exit 127
fi
"$PY" -c 'import sys; print("python", sys.version.split()[0], "OK")'
[ -f "$HERE/web/index.html" ] && echo "화면 파일 OK" || { echo "web/index.html이 없습니다" >&2; exit 1; }
echo "준비 완료. 실행: $HERE/start.sh"
