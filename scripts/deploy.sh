#!/bin/bash
# EC2에서 최신 코드 Pull + 서버 재시작
# 사용법: bash scripts/deploy.sh
set -e

cd ~/fact

echo "=== 최신 코드 Pull ==="
git pull origin main

echo "=== 의존성 업데이트 ==="
uv sync

echo "=== 서버 재시작 ==="
bash scripts/stop.sh
sleep 1
mkdir -p logs
bash scripts/start.sh

echo ""
echo "배포 완료!"
