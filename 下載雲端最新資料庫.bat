@echo off
chcp 65001
echo =========================================================
echo   App 評論監測工具 - 雲端資料庫下載腳本
echo =========================================================
echo.
echo 正在連線至 GCP 雲端機器 (app-monitor-vm) 並下載最新的 Excel...
echo 請稍稍候...

gcloud compute scp "app-monitor-vm:~/app-monitor/reports/App評論監測_資料庫.xlsx" "reports\Cloud_Backup_雲端最新資料庫.xlsx" --project=project-45f9a5d1-4ff8-4dae-b47 --zone=us-central1-a --quiet

if %ERRORLEVEL% EQU 0 (
    echo.
    echo 成功！[報告/Cloud_Backup_雲端最新資料庫.xlsx] 已更新。
) else (
    echo.
    echo 下載失敗，請檢查網路或 GCP 登入狀態。
)
echo.
pause
