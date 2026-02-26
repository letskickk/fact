@echo off
chcp 65001 >nul
REM =============================================
REM  데이터 파일 업로드 (PDF, 쿠키 등)
REM  사용법: scripts\upload-data.bat
REM =============================================

set EC2_IP=3.36.96.197
set PEM_FILE=C:\fact\fact.pem
set EC2_USER=ubuntu

echo.
echo === 데이터 파일 업로드 ===
echo.

REM PDF 파일 업로드
if exist "C:\fact\data\facts" (
    echo [1/2] PDF 파일 업로드 중...
    scp -i "%PEM_FILE%" -r "C:\fact\data\facts" %EC2_USER%@%EC2_IP%:/home/ubuntu/fact/data/
    echo PDF 업로드 완료
) else (
    echo data\facts 폴더 없음, 건너뜀
)

REM 쿠키 파일 업로드
if exist "C:\fact\data\youtube_cookies.txt" (
    echo [2/2] 쿠키 파일 업로드 중...
    scp -i "%PEM_FILE%" "C:\fact\data\youtube_cookies.txt" %EC2_USER%@%EC2_IP%:/home/ubuntu/fact/data/
    echo 쿠키 업로드 완료
) else (
    echo 쿠키 파일 없음, 건너뜀
)

echo.
echo === 업로드 완료! ===
echo.
pause
