"""
App 評論監測工具 — 評論抓取模組
支援 iOS App Store 與 Google Play，增量抓取新評論並自動去重。
支援回溯模式（--backfill）抓取近一年歷史評論。
使用 app-store-web-scraper 套件抓取 iOS 評論。
"""
import json
import os
from datetime import datetime, timedelta

from app_store_web_scraper import AppStoreEntry
from google_play_scraper import Sort, reviews

import config


def _backfill_since() -> datetime:
    """回溯模式的時間範圍（近一年），每次呼叫時即時計算。"""
    return datetime.now() - timedelta(days=365)


# ──────────────────────────────────────────────
# 已見 ID 管理
# ──────────────────────────────────────────────
def _load_seen_ids(filepath: str) -> set:
    """從 JSON 檔案載入已見評論 ID 集合。"""
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def _save_seen_ids(filepath: str, seen_ids: set):
    """將已見評論 ID 集合儲存到 JSON 檔案。"""
    parent = os.path.dirname(filepath)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(list(seen_ids), f, ensure_ascii=False)


# ──────────────────────────────────────────────
# iOS 評論抓取（使用 app-store-web-scraper）
# ──────────────────────────────────────────────
def get_ios_reviews(
    app_name: str, app_id: str, country: str = None, backfill: bool = False
) -> list[dict]:
    """抓取 iOS App Store 新評論（使用 app-store-web-scraper 套件）。"""
    country = country or config.IOS_COUNTRY
    print(f"[iOS] 正在抓取 {app_name} 的評論{'（回溯模式）' if backfill else ''} ...")

    min_date = _backfill_since() if backfill else None
    limit = 500  # 套件最多支援 500 則/國家

    try:
        app = AppStoreEntry(app_id=app_id, country=country)
        reviews_data = list(app.reviews(limit=limit))
    except Exception as e:
        print(f"[iOS] 抓取 {app_name} 失敗：{e}")
        return []

    print(f"[iOS] {app_name}：從套件取得 {len(reviews_data)} 則評論")

    if not reviews_data:
        print(f"[iOS] {app_name} 無評論資料")
        return []

    # 載入已見 ID
    seen_ids_file = os.path.join(config.DATA_DIR, f"{app_name}_ios_seen_ids.json")
    seen_ids = _load_seen_ids(seen_ids_file)

    new_reviews = []
    current_ids = set()

    for r in reviews_data:
        review_id = str(r.id)
        current_ids.add(review_id)

        # 回溯模式不檢查 seen_ids（全部抓回來）
        if not backfill and review_id in seen_ids:
            continue

        try:
            date_obj = r.date.replace(tzinfo=None)
            formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError, AttributeError):
            date_obj = None
            formatted_date = str(r.date)

        if min_date and date_obj and date_obj < min_date:
            continue

        new_reviews.append({
            "platform": "iOS",
            "app_name": app_name,
            "user_name": r.user_name,
            "rating": r.rating,
            "review_text": r.content,
            "date": formatted_date,
            "review_id": review_id,
        })

    # 更新已見 ID
    _save_seen_ids(seen_ids_file, seen_ids | current_ids)
    print(f"[iOS] {app_name}：抓到 {len(new_reviews)} 則{'歷史' if backfill else '新'}評論")
    return new_reviews


# ──────────────────────────────────────────────
# Android 評論抓取
# ──────────────────────────────────────────────
def get_android_reviews(
    app_name: str,
    app_id: str,
    lang: str = None,
    country: str = None,
    backfill: bool = False,
) -> list[dict]:
    """
    抓取 Google Play 最新評論。
    回溯模式會抓取大量歷史評論（使用 continuation_token 分頁）。
    """
    lang = lang or config.ANDROID_LANG
    country = country or config.ANDROID_COUNTRY
    count = config.BACKFILL_ANDROID_COUNT if backfill else config.ANDROID_REVIEW_COUNT
    min_date = _backfill_since() if backfill else None

    print(f"[Android] 正在抓取 {app_name} 的評論（{'回溯模式' if backfill else '增量模式'}）...")

    try:
        result, _ = reviews(
            app_id,
            lang=lang,
            country=country,
            sort=Sort.NEWEST,
            count=count,
        )
    except Exception as e:
        print(f"[Android] 抓取 {app_name} 失敗：{e}")
        return []

    # 載入已見 ID
    seen_ids_file = os.path.join(config.DATA_DIR, f"{app_name}_android_seen_ids.json")
    seen_ids = _load_seen_ids(seen_ids_file)

    new_reviews = []
    current_ids = set()
    for r in result:
        review_id = r["reviewId"]
        current_ids.add(review_id)

        # 回溯模式不檢查 seen_ids
        if not backfill and review_id in seen_ids:
            continue

        review_date = r["at"]
        # 統一為 naive datetime 以避免 aware/naive 比較 TypeError
        if review_date.tzinfo is not None:
            review_date = review_date.replace(tzinfo=None)
        if min_date and review_date < min_date:
            continue

        new_reviews.append({
            "platform": "Android",
            "app_name": app_name,
            "user_name": r["userName"],
            "rating": r["score"],
            "review_text": r["content"],
            "date": review_date.strftime("%Y-%m-%d %H:%M:%S"),
            "review_id": review_id,
        })

    # 更新已見 ID
    _save_seen_ids(seen_ids_file, seen_ids | current_ids)
    print(f"[Android] {app_name}：抓到 {len(new_reviews)} 則{'歷史' if backfill else '新'}評論")
    return new_reviews


# ──────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────
def run_scraper(backfill: bool = False) -> list[dict]:
    """抓取所有設定中 App 的新評論。"""
    all_new_reviews = []
    for app in config.APPS:
        all_new_reviews.extend(
            get_ios_reviews(app["name"], app["ios_id"], backfill=backfill)
        )
        all_new_reviews.extend(
            get_android_reviews(app["name"], app["android_id"], backfill=backfill)
        )
    return all_new_reviews


if __name__ == "__main__":
    import sys

    bf = "--backfill" in sys.argv
    found = run_scraper(backfill=bf)
    print(f"\n共找到 {len(found)} 則{'歷史' if bf else '新'}評論待處理。")
