#!/bin/bash
# 서버 중지
# 사용법: bash scripts/stop.sh

if [ -f ~/fact/logs/server.pid ]; then
    PID=$(cat ~/fact/logs/server.pid)
    if kill -0 $PID 2>/dev/null; then
        kill $PID
        echo "서버 종료됨 (PID: $PID)"
    else
        echo "서버가 실행 중이 아닙니다"
    fi
    rm -f ~/fact/logs/server.pid
else
    # PID 파일 없으면 포트로 찾기
    if lsof -t -i:8000 > /dev/null 2>&1; then
        kill -9 $(lsof -t -i:8000)
        echo "서버 종료됨"
    else
        echo "서버가 실행 중이 아닙니다"
    fi
fi
