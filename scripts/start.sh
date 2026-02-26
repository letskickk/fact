#!/bin/bash
# 서버 시작 (백그라운드)
# 사용법: bash scripts/start.sh
set -e

cd ~/fact

# 기존 서버 종료
if lsof -t -i:8000 > /dev/null 2>&1; then
    echo "기존 서버 종료 중..."
    kill -9 $(lsof -t -i:8000) 2>/dev/null || true
    sleep 1
fi

# deno PATH
export DENO_INSTALL="$HOME/.deno"
export PATH="$DENO_INSTALL/bin:$PATH"

echo "서버 시작 중..."
nohup uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 > ~/fact/logs/server.log 2>&1 &
echo $! > ~/fact/logs/server.pid

sleep 2
if kill -0 $(cat ~/fact/logs/server.pid) 2>/dev/null; then
    echo "서버 실행 중 (PID: $(cat ~/fact/logs/server.pid))"
    echo "로그 확인: tail -f ~/fact/logs/server.log"
else
    echo "서버 시작 실패! 로그 확인:"
    cat ~/fact/logs/server.log
fi
