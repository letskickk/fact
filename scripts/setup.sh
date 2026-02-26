#!/bin/bash
# EC2 초기 설정 스크립트 (Ubuntu 22.04)
# 사용법: bash scripts/setup.sh
set -e

echo "=== 시스템 업데이트 ==="
sudo apt update && sudo apt upgrade -y

echo "=== 필수 패키지 설치 ==="
sudo apt install -y ffmpeg unzip git

echo "=== Deno 설치 ==="
if ! command -v deno &> /dev/null; then
    curl -fsSL https://deno.land/install.sh | sh
    echo 'export DENO_INSTALL="$HOME/.deno"' >> ~/.bashrc
    echo 'export PATH="$DENO_INSTALL/bin:$PATH"' >> ~/.bashrc
    export DENO_INSTALL="$HOME/.deno"
    export PATH="$DENO_INSTALL/bin:$PATH"
    echo "Deno 설치 완료"
else
    echo "Deno 이미 설치됨: $(deno --version | head -1)"
fi

echo "=== uv 설치 ==="
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.local/bin/env
    echo "uv 설치 완료"
else
    echo "uv 이미 설치됨: $(uv --version)"
fi

echo "=== Python 의존성 설치 ==="
cd ~/fact
uv sync

echo "=== 디렉토리 생성 ==="
mkdir -p data/facts

echo ""
echo "========================================="
echo "  초기 설정 완료!"
echo "========================================="
echo ""
echo "다음 단계:"
echo "  1. .env 파일 생성: cp .env.example .env && nano .env"
echo "  2. PDF 업로드: data/facts/ 폴더에 파일 복사"
echo "  3. 쿠키 업로드: data/youtube_cookies.txt"
echo "  4. 서버 시작: bash scripts/start.sh"
