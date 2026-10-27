@echo off
chcp 65001 > nul
cd /d "%~dp0"
set PYTHONUTF8=1

if "%GEMINI_API_KEY%"=="" (
  echo GEMINI_API_KEY が設定されていません。
  echo コマンドプロンプトで  setx GEMINI_API_KEY "あなたのキー"  を実行してから、もう一度開いてください。
  pause
  exit /b 1
)

set /p TOPIC=動画のテーマを入力してください（空欄なら「工場の安全対策」）:
if "%TOPIC%"=="" set TOPIC=工場の安全対策

python -m pip install -q -r requirements.txt
python make_video.py "%TOPIC%"
pause
