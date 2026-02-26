@echo off
chcp 65001 >nul
REM =============================================
REM  FACT 프로젝트 원클릭 배포 (로컬 → EC2)
REM  사용법: deploy.bat
REM =============================================

set EC2_IP=3.36.96.197
set PEM_FILE=C:\fact\fact.pem
set EC2_USER=ubuntu

echo.
echo ============================================
echo   FACT 프로젝트 배포 시작
echo ============================================
echo.

REM 1. Git push
echo [1/3] Git push...
git add -A
git commit -m "deploy update" 2>nul || echo (변경사항 없음)
git push origin main 2>nul || git push origin master 2>nul

REM 2. EC2에서 deploy.sh 실행
echo [2/3] EC2 배포 중...
ssh -i "%PEM_FILE%" %EC2_USER%@%EC2_IP% "cd ~/fact && git pull origin main && uv sync && bash scripts/stop.sh; mkdir -p logs && bash scripts/start.sh"

REM 3. 확인
echo.
echo [3/3] 배포 완료!
echo 접속: http://%EC2_IP%:8000
echo.
pause
