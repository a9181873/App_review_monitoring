"""
App 評論監測工具 — 儲存抽象層
自動偵測環境：
  - GCP Cloud Functions → 使用 Google Cloud Storage (GCS) 持久化
  - 本機 / PAD          → 直接使用本地檔案系統（不需要 GCS）

未來從 GCP 搬到 PAD 時，完全不需要改任何程式碼。
"""
import os

import config

# GCS Bucket 名稱（部署腳本會自動建立）
GCS_BUCKET_NAME = os.getenv(
    "GCS_BUCKET_NAME",
    f"{os.getenv('GCP_PROJECT_ID', 'app-review-monitor')}-data",
)


def _is_gcp() -> bool:
    """判斷是否在 GCP Cloud Functions 環境中。"""
    return config._IS_GCP


def _get_gcs_bucket():
    """取得 GCS Bucket 物件（僅在 GCP 環境呼叫）。"""
    from google.cloud import storage as gcs

    client = gcs.Client()
    return client.bucket(GCS_BUCKET_NAME)


def sync_down(filename: str, local_dir: str = None) -> str:
    """
    從遠端同步檔案到本地。

    GCP 環境：從 GCS 下載到 local_dir（預設 /tmp）。
    本機環境：什麼都不做，直接回傳本地路徑。

    回傳：本地檔案的完整路徑（不管檔案是否存在）。
    """
    if local_dir is None:
        local_dir = config.DATA_DIR

    local_path = os.path.join(local_dir, filename)

    if not _is_gcp():
        return local_path

    # GCP: 從 GCS 下載
    try:
        bucket = _get_gcs_bucket()
        blob = bucket.blob(filename)
        if blob.exists():
            os.makedirs(local_dir, exist_ok=True)
            blob.download_to_filename(local_path)
            print(f"[Storage] 從 GCS 下載：{filename}")
        else:
            print(f"[Storage] GCS 中無此檔案：{filename}（首次執行）")
    except Exception as e:
        print(f"[Storage] 下載失敗（{filename}）：{e}")

    return local_path


def sync_up(filename: str, local_dir: str = None):
    """
    將本地檔案同步到遠端。

    GCP 環境：上傳到 GCS。
    本機環境：什麼都不做（檔案已在本地）。
    """
    if local_dir is None:
        local_dir = config.DATA_DIR

    local_path = os.path.join(local_dir, filename)

    if not _is_gcp():
        return

    if not os.path.exists(local_path):
        print(f"[Storage] 本地檔案不存在，跳過上傳：{filename}")
        return

    try:
        bucket = _get_gcs_bucket()
        blob = bucket.blob(filename)
        blob.upload_from_filename(local_path)
        print(f"[Storage] 已上傳至 GCS：{filename}")
    except Exception as e:
        print(f"[Storage] 上傳失敗（{filename}）：{e}")
