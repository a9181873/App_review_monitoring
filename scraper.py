"""
App 評論監測工具 — 評論抓取模組
支援 iOS App Store 與 Google Play，增量抓取新評論並自動去重。
"""
import json
import os
from datetime import datetime

from google_play_scraper import Sort, reviews

import config

# 只回報此日期之後的評論（避免歷史評論灌爆通知）
MIN_REVIEW_DATE = datetime(2026, 1, 1)


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
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(list(seen_ids), f, ensure_ascii=False)


# ──────────────────────────────────────────────
# iOS 評論抓取 (改用 iTunes RSS Feed 避免阻擋)
# ──────────────────────────────────────────────
def get_ios_reviews(app_name: str, app_id: str, country: str = None) -> list[dict]:
    """抓取 iOS App Store 新評論 (透過官方 RSS Feed)。"""
    country = country or config.IOS_COUNTRY
    print(f"[iOS] 正在抓取 {app_name} 的評論 ...")

    import requests

    # 使用 iTunes RSS Feed API (JSON 格式)
    # 抓取前 10 頁 (page=1~10)，每頁最多 50 筆
    reviews_data = []
    for page in range(1, 11):
        url = f"https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"[iOS] 抓取 {app_name} 第 {page} 頁失敗：{e}")
            break

        feed = data.get("feed", {})
        entries = feed.get("entry", [])

        if not entries:
            break  # 沒有更多資料了

        # 如果只有一筆，有時會不是 list
        if isinstance(entries, dict):
            entries = [entries]

        # 過濾出真正的評論 (通常第一筆 entry 是 App 資訊本身，沒有 author)
        page_reviews = [entry for entry in entries if "author" in entry]
        if not page_reviews:
            break  # 該頁無評論資料
        reviews_data.extend(page_reviews)
        print(f"[iOS] {app_name} 第 {page} 頁：{len(page_reviews)} 則評論")

    if not reviews_data:
        print(f"[iOS] {app_name} 無評論資料")
        return []

    # 載入已見 ID
    seen_ids_file = os.path.join(config.DATA_DIR, f"{app_name}_ios_seen_ids.json")
    seen_ids = _load_seen_ids(seen_ids_file)

    new_reviews = []
    current_ids = set()

    for r in reviews_data:
        review_id = r.get("id", {}).get("label")
        if not review_id:
            continue

        current_ids.add(review_id)
        if review_id not in seen_ids:
            # 轉換時間格式 (e.g. 2024-03-01T12:00:00-07:00)
            date_str = r.get("updated", {}).get("label", "")
            try:
                date_obj = datetime.fromisoformat(date_str).replace(tzinfo=None)
                formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                date_obj = None
                formatted_date = date_str

            # 只回報 2026 年以後的評論
            if date_obj and date_obj < MIN_REVIEW_DATE:
                continue

            new_reviews.append(
                {
                    "platform": "iOS",
                    "app_name": app_name,
                    "user_name": r.get("author", {}).get("name", {}).get("label", "Unknown"),
                    "rating": int(r.get("im:rating", {}).get("label", 0)),
                    "review_text": r.get("content", {}).get("label", ""),
                    "date": formatted_date,
                    "is_replied": False,  # RSS feed 不提供回覆資訊
                    "review_id": review_id,
                }
            )

    # 更新已見 ID
    _save_seen_ids(seen_ids_file, seen_ids | current_ids)
    print(f"[iOS] {app_name}：抓到 {len(new_reviews)} 則新評論")
    return new_reviews


# ──────────────────────────────────────────────
# Android 評論抓取（已優化）
# ──────────────────────────────────────────────
def get_android_reviews(
    app_name: str,
    app_id: str,
    lang: str = None,
    country: str = None,
) -> list[dict]:
    """
    抓取 Google Play 最新評論。
    使用 reviews() 搭配 count 參數，僅抓取最近評論，大幅提升效率。
    已存在於 seen_ids 中的評論會自動跳過，不重複回報。
    """
    lang = lang or config.ANDROID_LANG
    country = country or config.ANDROID_COUNTRY
    print(f"[Android] 正在抓取 {app_name} 的評論 ...")

    try:
        result, _ = reviews(
            app_id,
            lang=lang,
            country=country,
            sort=Sort.NEWEST,
            count=config.ANDROID_REVIEW_COUNT,
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

        # 已見過的評論直接跳過，不重複回報
        if review_id in seen_ids:
            continue

        review_date = r["at"]

        # 只回報 2026 年以後的評論
        if review_date < MIN_REVIEW_DATE:
            continue

        # 過濾已回覆的評論（只通知未回覆的）
        is_replied = r.get("replyContent") is not None
        if config.IGNORE_REPLIED_ANDROID_REVIEWS and is_replied:
            continue

        new_reviews.append(
            {
                "platform": "Android",
                "app_name": app_name,
                "user_name": r["userName"],
                "rating": r["score"],
                "review_text": r["content"],
                "date": review_date.strftime("%Y-%m-%d %H:%M:%S"),
                "is_replied": is_replied,
                "review_id": review_id,
            }
        )

    # 更新已見 ID
    _save_seen_ids(seen_ids_file, seen_ids | current_ids)
    print(f"[Android] {app_name}：抓到 {len(new_reviews)} 則新評論")
    return new_reviews


# ──────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────
def run_scraper() -> list[dict]:
    """抓取所有設定中 App 的新評論。"""
    all_new_reviews = []
    for app in config.APPS:
        all_new_reviews.extend(get_ios_reviews(app["name"], app["ios_id"]))
        all_new_reviews.extend(get_android_reviews(app["name"], app["android_id"]))
    return all_new_reviews


if __name__ == "__main__":
    found = run_scraper()
    print(f"\n共找到 {len(found)} 則新評論待處理。")
