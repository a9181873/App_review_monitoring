"""
App 評論監測工具 — 評論抓取模組
支援 iOS App Store 與 Google Play，增量抓取新評論並自動去重。
支援回溯模式（--backfill）抓取近一年歷史評論。
使用 app-store-web-scraper 套件抓取 iOS 評論。
"""
import json
import os
import re
from datetime import datetime, timedelta

import requests
from app_store_web_scraper import AppStoreEntry
from google_play_scraper import Sort, reviews

import config

# 只回報此日期之後的評論（避免歷史評論灌爆通知）
MIN_REVIEW_DATE = datetime(2026, 1, 1)


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
# iOS 開發者回覆偵測（網頁爬蟲，使用 Review ID 比對）
# ──────────────────────────────────────────────
def _check_ios_replies_by_id(app_id: str, country: str = "tw") -> dict[str, bool]:
    """
    從 App Store 網頁版抓取開發者回覆狀態，以 review_id 為 key。
    回傳 {review_id: has_reply} 的字典。
    若爬蟲失敗則回傳空 dict（fallback 為全部標記未回覆）。
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("[iOS] beautifulsoup4 未安裝，跳過回覆偵測")
        return {}

    url = f"https://apps.apple.com/{country}/app/id{app_id}?see-all=reviews"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text

        reply_map: dict[str, bool] = {}

        # 從 HTML 中直接用正則表達式提取 review ID 和回覆狀態
        # App Store HTML 結構：<article aria-labelledby="review-{ID}-title">
        # 若該 article 內含 developer-response-container 則為已回覆
        soup = BeautifulSoup(html, "html.parser")
        articles = soup.find_all("article")
        for article in articles:
            # 從 aria-labelledby 提取 review ID
            label_id = article.get("aria-labelledby", "")
            match = re.search(r"review-(\d+)-title", label_id)
            if not match:
                continue
            review_id = match.group(1)

            # 判斷是否有開發者回覆區塊
            has_reply = bool(article.find(
                lambda t: t.name == "div" and t.get("class")
                and any("developer-response" in c for c in t["class"])
            ))
            reply_map[review_id] = has_reply

        if reply_map:
            replied_count = sum(1 for v in reply_map.values() if v)
            print(f"[iOS] 網頁爬蟲成功，{len(reply_map)} 則評論中 {replied_count} 則已回覆")
        else:
            print("[iOS] 網頁爬蟲未取得評論（可能被 Apple 阻擋或無評論），回覆狀態標記為未知")
        return reply_map

    except Exception as e:
        print(f"[iOS] 網頁爬蟲失敗（{e}），回覆狀態將標記為未知")
        return {}


# ──────────────────────────────────────────────
# iOS 評論抓取（使用 app-store-web-scraper）
# ──────────────────────────────────────────────
def get_ios_reviews(
    app_name: str, app_id: str, country: str = None, backfill: bool = False
) -> list[dict]:
    """抓取 iOS App Store 新評論（使用 app-store-web-scraper 套件）。"""
    country = country or config.IOS_COUNTRY
    print(f"[iOS] 正在抓取 {app_name} 的評論{'（回溯模式）' if backfill else ''} ...")

    min_date = _backfill_since() if backfill else MIN_REVIEW_DATE
    limit = 500 if backfill else 500  # 套件最多支援 500 則/國家

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

    # 嘗試網頁爬蟲偵測回覆狀態（以 review_id 為 key）
    reply_map = _check_ios_replies_by_id(app_id, country)

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

        if date_obj and date_obj < min_date:
            continue

        # 用 review_id 查詢回覆狀態
        is_replied = reply_map.get(review_id, False)

        review_dict = {
            "platform": "iOS",
            "app_name": app_name,
            "user_name": r.user_name,
            "rating": r.rating,
            "review_text": r.content,
            "date": formatted_date,
            "is_replied": is_replied,
            "review_id": review_id,
        }

        # 過濾已回覆的 iOS 評論（僅在非回溯模式且設定開啟時）
        if not backfill and config.IGNORE_REPLIED_IOS_REVIEWS and is_replied:
            continue

        new_reviews.append(review_dict)

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
    min_date = _backfill_since() if backfill else MIN_REVIEW_DATE

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
        if review_date < min_date:
            continue

        is_replied = r.get("replyContent") is not None

        # 非回溯模式才過濾已回覆評論
        if not backfill and config.IGNORE_REPLIED_ANDROID_REVIEWS and is_replied:
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
