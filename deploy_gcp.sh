#!/bin/bash
# ============================================================
# App 評論監測工具 — GCP Cloud Functions 部署腳本
#
# 使用方式：
#   bash deploy_gcp.sh                  # 部署增量模式 (日常監控)
#   bash deploy_gcp.sh --with-backfill  # 同時部署回溯用的函式
#
# 前置條件：
#   1. 安裝 gcloud CLI: https://cloud.google.com/sdk/docs/install
#   2. 登入: gcloud auth login
#   3. 設定 .env 中的所有環境變數
# ============================================================

set -e

# ── 設定區 ──────────────────────────────────────
PROJECT_ID="project-45f9a5d1-4ff8-4dae-b47"
REGION="asia-east1"           # 台灣最近的區域
FUNCTION_NAME="app-review-monitor"
BACKFILL_FUNCTION_NAME="app-review-monitor-backfill"
SCHEDULER_JOB="app-review-daily"
SCHEDULE="0 11 * * *"        # 每天早上 11:00 (台灣時間)
TIMEZONE="Asia/Taipei"
RUNTIME="python312"
MEMORY="512MB"
TIMEOUT="540s"                # 9 分鐘（Cloud Functions 最大 540s）

# ── 讀取 .env ──────────────────────────────────
ENV_VARS=""
if [ -f .env ]; then
    while IFS='=' read -r key value; do
        # 跳過空行和註解
        [[ -z "$key" || "$key" == \#* ]] && continue
        # 移除可能的引號
        value=$(echo "$value" | sed 's/^["'\'']\|["'\''"]$//g')
        if [ -z "$ENV_VARS" ]; then
            ENV_VARS="${key}=${value}"
        else
            ENV_VARS="${ENV_VARS},${key}=${value}"
        fi
    done < .env
fi

echo "=========================================="
echo "  部署 App 評論監測工具到 GCP"
echo "  Project: ${PROJECT_ID}"
echo "  Region:  ${REGION}"
echo "=========================================="

# ── 設定 GCP 專案 ──────────────────────────────
gcloud config set project "${PROJECT_ID}"

# ── 啟用必要的 API ─────────────────────────────
echo ""
echo "[1/5] 啟用 GCP API..."
gcloud services enable \
    cloudfunctions.googleapis.com \
    cloudscheduler.googleapis.com \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    --quiet

# ── 部署 Cloud Function (增量模式) ─────────────
echo ""
echo "[2/5] 部署 Cloud Function: ${FUNCTION_NAME}..."
gcloud functions deploy "${FUNCTION_NAME}" \
    --gen2 \
    --region="${REGION}" \
    --runtime="${RUNTIME}" \
    --memory="${MEMORY}" \
    --timeout="${TIMEOUT}" \
    --entry-point=cloud_function_handler \
    --trigger-http \
    --allow-unauthenticated \
    --set-env-vars="${ENV_VARS}" \
    --source=. \
    --quiet

# ── 取得 Function URL ──────────────────────────
FUNCTION_URL=$(gcloud functions describe "${FUNCTION_NAME}" \
    --gen2 \
    --region="${REGION}" \
    --format="value(serviceConfig.uri)")

echo "  Function URL: ${FUNCTION_URL}"

# ── 設定 Cloud Scheduler ──────────────────────
echo ""
echo "[3/5] 設定 Cloud Scheduler: ${SCHEDULER_JOB}..."

# 刪除舊的排程（如果存在）
gcloud scheduler jobs delete "${SCHEDULER_JOB}" \
    --location="${REGION}" --quiet 2>/dev/null || true

gcloud scheduler jobs create http "${SCHEDULER_JOB}" \
    --location="${REGION}" \
    --schedule="${SCHEDULE}" \
    --time-zone="${TIMEZONE}" \
    --uri="${FUNCTION_URL}" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"mode": "incremental"}' \
    --attempt-deadline="${TIMEOUT}" \
    --quiet

echo "  排程已設定：${SCHEDULE} (${TIMEZONE})"

# ── 部署回溯用 Function（可選）─────────────────
if [ "$1" == "--with-backfill" ]; then
    echo ""
    echo "[4/5] 部署回溯用 Cloud Function: ${BACKFILL_FUNCTION_NAME}..."
    gcloud functions deploy "${BACKFILL_FUNCTION_NAME}" \
        --gen2 \
        --region="${REGION}" \
        --runtime="${RUNTIME}" \
        --memory="1024MB" \
        --timeout="${TIMEOUT}" \
        --entry-point=cloud_function_backfill_handler \
        --trigger-http \
        --allow-unauthenticated \
        --set-env-vars="${ENV_VARS}" \
        --source=. \
        --quiet

    BACKFILL_URL=$(gcloud functions describe "${BACKFILL_FUNCTION_NAME}" \
        --gen2 \
        --region="${REGION}" \
        --format="value(serviceConfig.uri)")

    echo "  Backfill URL: ${BACKFILL_URL}"
    echo ""
    echo "  手動觸發回溯：curl -X POST ${BACKFILL_URL}"
fi

# ── 驗證 ──────────────────────────────────────
echo ""
echo "[5/5] 驗證部署..."
gcloud functions describe "${FUNCTION_NAME}" \
    --gen2 \
    --region="${REGION}" \
    --format="table(name,state,serviceConfig.uri)"

echo ""
echo "=========================================="
echo "  部署完成！"
echo "  日常排程：每天 11:00 AM (台北時間)"
echo "  手動觸發：curl -X POST ${FUNCTION_URL}"
echo "=========================================="
