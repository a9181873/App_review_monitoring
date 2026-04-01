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
#
# 安全性：敏感變數（密碼、API Key、Webhook URL）使用 GCP Secret Manager
#         非敏感變數（SMTP server/port/recipients）使用一般環境變數
# ============================================================

set -e

# ── 設定區 ──────────────────────────────────────
PROJECT_ID="project20260401"
REGION="asia-east1"           # 台灣最近的區域
FUNCTION_NAME="app-review-monitor"
BACKFILL_FUNCTION_NAME="app-review-monitor-backfill"
SCHEDULER_JOB="app-review-daily"
SCHEDULE="0 11 * * *"        # 每天早上 11:00 (台灣時間)
TIMEZONE="Asia/Taipei"
RUNTIME="python312"
MEMORY="512MB"
TIMEOUT="540s"                # 9 分鐘（Cloud Functions 最大 540s）
GCS_BUCKET="${PROJECT_ID}-app-review-data"  # GCS Bucket for 持久化

# ── 敏感變數名稱（存入 Secret Manager）─────────
SECRET_KEYS=("EMAIL_PASSWORD" "GEMINI_API_KEY" "TEAMS_WEBHOOK_URL" "EMAIL_SENDER")

# ── 非敏感變數（一般環境變數）────────────────────
PLAIN_KEYS=("EMAIL_SMTP_SERVER" "EMAIL_SMTP_PORT" "EMAIL_RECIPIENTS")

# ── 從 .env 讀取所有變數到 associative array ───
declare -A ENV_MAP
if [ -f .env ]; then
    while IFS='=' read -r key value; do
        [[ -z "$key" || "$key" == \#* ]] && continue
        value=$(echo "$value" | sed 's/^["'\'']\|["'\''"]$//g')
        ENV_MAP["$key"]="$value"
    done < .env
fi

echo "=========================================="
echo "  部署 App 評論監測工具到 GCP"
echo "  Project: ${PROJECT_ID}"
echo "  Region:  ${REGION}"
echo "  安全模式：敏感變數使用 Secret Manager"
echo "=========================================="

# ── 設定 GCP 專案 ──────────────────────────────
gcloud config set project "${PROJECT_ID}"

# ── 啟用必要的 API ─────────────────────────────
echo ""
echo "[1/6] 啟用 GCP API..."
gcloud services enable \
    cloudfunctions.googleapis.com \
    cloudscheduler.googleapis.com \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    secretmanager.googleapis.com \
    storage.googleapis.com \
    --quiet

# ── 建立 GCS Bucket（用於持久化 Excel / seen_ids）──
echo ""
echo "[1.5/6] 建立 GCS Bucket: ${GCS_BUCKET}..."
if ! gsutil ls -b "gs://${GCS_BUCKET}" &>/dev/null; then
    gsutil mb -p "${PROJECT_ID}" -l "${REGION}" "gs://${GCS_BUCKET}"
    echo "  ✓ 已建立 Bucket: ${GCS_BUCKET}"
else
    echo "  ✓ Bucket 已存在: ${GCS_BUCKET}"
fi

# ── 建立/更新 Secrets ──────────────────────────
echo ""
echo "[2/6] 設定 Secret Manager..."
for secret_key in "${SECRET_KEYS[@]}"; do
    secret_value="${ENV_MAP[$secret_key]}"
    if [ -z "$secret_value" ]; then
        echo "  ⚠ ${secret_key} 未在 .env 中設定，跳過"
        continue
    fi

    # 建立 secret（若已存在則跳過）
    if ! gcloud secrets describe "$secret_key" --quiet 2>/dev/null; then
        gcloud secrets create "$secret_key" --replication-policy="automatic" --quiet
        echo "  ✓ 建立 secret: ${secret_key}"
    fi

    # 新增版本（寫入最新值）
    echo -n "$secret_value" | gcloud secrets versions add "$secret_key" --data-file=- --quiet
    echo "  ✓ 更新 secret: ${secret_key}"
done

# ── 授權 Cloud Functions 服務帳號存取 Secrets ──
echo ""
echo "[3/6] 授權服務帳號存取 Secrets..."
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
SA_EMAIL="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for secret_key in "${SECRET_KEYS[@]}"; do
    secret_value="${ENV_MAP[$secret_key]}"
    [ -z "$secret_value" ] && continue
    gcloud secrets add-iam-policy-binding "$secret_key" \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="roles/secretmanager.secretAccessor" \
        --quiet > /dev/null 2>&1
done
echo "  ✓ 服務帳號 ${SA_EMAIL} 已授權"

# ── 組裝部署參數 ────────────────────────────────
# 非敏感環境變數
ENV_VARS=""
# 加入 GCS Bucket 名稱
ENV_VARS="GCS_BUCKET_NAME=${GCS_BUCKET},GCP_PROJECT_ID=${PROJECT_ID}"
for key in "${PLAIN_KEYS[@]}"; do
    val="${ENV_MAP[$key]}"
    [ -z "$val" ] && continue
    ENV_VARS="${ENV_VARS},${key}=${val}"
done

# Secret 映射（SECRET_NAME:版本=環境變數名）
SET_SECRETS=""
for secret_key in "${SECRET_KEYS[@]}"; do
    val="${ENV_MAP[$secret_key]}"
    [ -z "$val" ] && continue
    if [ -z "$SET_SECRETS" ]; then
        SET_SECRETS="${secret_key}=${secret_key}:latest"
    else
        SET_SECRETS="${SET_SECRETS},${secret_key}=${secret_key}:latest"
    fi
done

# ── 部署 Cloud Function (增量模式) ─────────────
echo ""
echo "[4/6] 部署 Cloud Function: ${FUNCTION_NAME}..."

DEPLOY_ARGS=(
    --gen2
    --region="${REGION}"
    --runtime="${RUNTIME}"
    --memory="${MEMORY}"
    --timeout="${TIMEOUT}"
    --entry-point=cloud_function_handler
    --trigger-http
    --allow-unauthenticated
    --source=.
    --quiet
)
[ -n "$ENV_VARS" ] && DEPLOY_ARGS+=(--set-env-vars="${ENV_VARS}")
[ -n "$SET_SECRETS" ] && DEPLOY_ARGS+=(--set-secrets="${SET_SECRETS}")

gcloud functions deploy "${FUNCTION_NAME}" "${DEPLOY_ARGS[@]}"

# ── 取得 Function URL ──────────────────────────
FUNCTION_URL=$(gcloud functions describe "${FUNCTION_NAME}" \
    --gen2 \
    --region="${REGION}" \
    --format="value(serviceConfig.uri)")

echo "  Function URL: ${FUNCTION_URL}"

# ── 設定 Cloud Scheduler ──────────────────────
echo ""
echo "[5/6] 設定 Cloud Scheduler: ${SCHEDULER_JOB}..."

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
    echo "[*] 部署回溯用 Cloud Function: ${BACKFILL_FUNCTION_NAME}..."

    BACKFILL_ARGS=(
        --gen2
        --region="${REGION}"
        --runtime="${RUNTIME}"
        --memory="1024MB"
        --timeout="${TIMEOUT}"
        --entry-point=cloud_function_backfill_handler
        --trigger-http
        --allow-unauthenticated
        --source=.
        --quiet
    )
    [ -n "$ENV_VARS" ] && BACKFILL_ARGS+=(--set-env-vars="${ENV_VARS}")
    [ -n "$SET_SECRETS" ] && BACKFILL_ARGS+=(--set-secrets="${SET_SECRETS}")

    gcloud functions deploy "${BACKFILL_FUNCTION_NAME}" "${BACKFILL_ARGS[@]}"

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
echo "[6/6] 驗證部署..."
gcloud functions describe "${FUNCTION_NAME}" \
    --gen2 \
    --region="${REGION}" \
    --format="table(name,state,serviceConfig.uri)"

echo ""
echo "=========================================="
echo "  部署完成！"
echo "  日常排程：每天 11:00 AM (台北時間)"
echo "  手動觸發：curl -X POST ${FUNCTION_URL}"
echo "  GCS 資料桶：${GCS_BUCKET}"
echo "=========================================="
