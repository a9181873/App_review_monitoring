"""
App 評論監測工具 — 評論抓取模組
支援 iOS App Store 與 Google Play，增量抓取新評論並自動去重。
支援回溯模式（--backfill）抓取近一年歷史評論。

2026-04 更新：
  - iOS：改用自家實作直呼 iTunes RSS（帶 Mozilla UA），繞過 app-store-web-scraper
    0.2.0 的 UA 封鎖問題（Apple 會回空 feed）。
  - Android：改用 continuation_token 迴圈分頁，遇到已見 ID 連續出現就停，
    避免單次 count=200 漏掉爆量新評論。
"""
import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

from google_play_scraper import Sort, reviews

import config
from storage import sync_down, sync_up


_IOS_UAS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
]
_IOS_RSS_PAGE_LIMIT = 10   # Apple RSS 最多 10 頁
_IOS_PER_PAGE = 50         # 每頁 50 則
_ANDROID_PAGE_SIZE = 200   # Google Play 單頁上限
_ANDROID_MAX_PAGES = 20    # 增量模式最多分頁 20 次（= 4000 則）保險上限
_ANDROID_STOP_AFTER_SEEN = 50  # 連續遇到 50 則已見 ID 就停（確定已覆蓋所有新評論）


def _backfill_since() -> datetime:
    """回溯模式的時間範圍（近一年），每次呼叫時即時計算。"""
    return datetime.now() - timedelta(days=365)


# ──────────────────────────────────────────────
# 已見 ID 管理
# ──────────────────────────────────────────────
def _load_seen_ids(filepath: str) -> tuple[set, bool]:
    """從 JSON 檔案載入已見評論 ID 集合。回傳 (seen_ids, is_fresh)。"""
    filename = os.path.basename(filepath)
    sync_down(filename)

    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            ids = set(json.load(f))
            return ids, False
    return set(), True


def _save_seen_ids(filepath: str, seen_ids: set):
    parent = os.path.dirname(filepath)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(list(seen_ids), f, ensure_ascii=False)

    filename = os.path.basename(filepath)
    sync_up(filename)


# ──────────────────────────────────────────────
# iOS：直呼 iTunes RSS（自家實作，繞過套件 UA 封鎖）
# ──────────────────────────────────────────────
def _fetch_ios_page(country: str, app_id: str, page: int) -> dict:
    """抓單頁 iOS RSS。每個 UA 最多試 1 次，直到拿到 entries 或跑完 UA 列表。"""
    url = (
        f"https://itunes.apple.com/{country}/rss/customerreviews/"
        f"page={page}/id={app_id}/sortby=mostrecent/json"
    )
    last_data: dict | None = None
    last_err: Exception | None = None

    for idx, ua in enumerate(_IOS_UAS):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": ua,
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            last_data = data
            # feed 存在且有 entry 才算成功；若空 feed 代表被擋，換 UA
            feed = data.get("feed", {}) or {}
            if feed.get("entry"):
                return data
            if idx < len(_IOS_UAS) - 1:
                time.sleep(1 + idx)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            if idx < len(_IOS_UAS) - 1:
                time.sleep(2 ** idx)

    if last_data is not None:
        return last_data  # 可能真的沒 entry（該頁無評論）
    raise RuntimeError(f"iOS RSS page {page} 所有 UA 皆失敗：{last_err}")


def _parse_ios_entry(entry: dict) -> dict | None:
    try:
        review_id = str(entry["id"]["label"])
        date_str = entry["updated"]["label"]
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            dt = None

        return {
            "review_id": review_id,
            "date_obj": dt,
            "user_name": entry["author"]["name"]["label"],
            "title": entry.get("title", {}).get("label", ""),
            "content": entry["content"]["label"],
            "rating": int(entry["im:rating"]["label"]),
        }
    except (KeyError, ValueError, TypeError) as e:
        print(f"[iOS] 解析評論條目失敗，略過：{e}")
        return None


def get_ios_reviews(
    app_name: str, app_id: str, country: str = None, backfill: bool = False
) -> list[dict]:
    """抓取 iOS App Store 新評論（自家 RSS 實作）。"""
    country = (country or config.IOS_COUNTRY).lower()
    print(f"[iOS] 正在抓取 {app_name} 的評論{'（回溯模式）' if backfill else ''} ...")

    seen_ids_file = os.path.join(config.DATA_DIR, f"{app_name}_ios_seen_ids.json")
    seen_ids, is_fresh = _load_seen_ids(seen_ids_file)

    if backfill:
        min_date = _backfill_since()
        max_pages = _IOS_RSS_PAGE_LIMIT
    elif is_fresh:
        min_date = datetime.now() - timedelta(days=2)
        max_pages = _IOS_RSS_PAGE_LIMIT
        print(f"[iOS] {app_name}：首次執行，僅抓取近 2 天評論（增量保護）")
    else:
        min_date = None
        max_pages = _IOS_RSS_PAGE_LIMIT

    new_reviews: list[dict] = []
    current_ids: set[str] = set()
    total_fetched = 0

    for page in range(1, max_pages + 1):
        try:
            data = _fetch_ios_page(country, app_id, page)
        except Exception as e:
            print(f"[iOS] {app_name} page {page} 失敗：{e}")
            break

        feed = data.get("feed", {}) or {}
        entries = feed.get("entry")
        if not entries:
            break
        if not isinstance(entries, list):
            entries = [entries]

        total_fetched += len(entries)
        page_all_seen = True
        stop_by_date = False

        for entry in entries:
            parsed = _parse_ios_entry(entry)
            if not parsed:
                continue
            review_id = parsed["review_id"]
            current_ids.add(review_id)

            if not backfill and review_id in seen_ids:
                continue
            page_all_seen = False

            date_obj = parsed["date_obj"]
            formatted_date = (
                date_obj.strftime("%Y-%m-%d %H:%M:%S") if date_obj else ""
            )

            if min_date and date_obj and date_obj < min_date:
                stop_by_date = True
                continue

            new_reviews.append({
                "platform": "iOS",
                "app_name": app_name,
                "user_name": parsed["user_name"],
                "rating": parsed["rating"],
                "review_text": parsed["content"],
                "date": formatted_date,
                "review_id": review_id,
            })

        # 增量模式：若本頁全是已見 ID，再往後翻也只會更舊，停止
        if not backfill and page_all_seen and seen_ids:
            break
        if stop_by_date and not backfill:
            break

        time.sleep(0.3)

    print(f"[iOS] {app_name}：RSS 取得 {total_fetched} 則，抓到 "
          f"{len(new_reviews)} 則{'歷史' if backfill else '新'}評論")

    _save_seen_ids(seen_ids_file, seen_ids | current_ids)
    return new_reviews


# ──────────────────────────────────────────────
# Android 評論抓取（continuation_token 迴圈分頁）
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
    增量模式：分頁到連續遇到 _ANDROID_STOP_AFTER_SEEN 則已見 ID 就停。
    回溯模式：一路翻頁直到沒有 continuation_token 或超過 min_date。
    """
    lang = lang or config.ANDROID_LANG
    country = country or config.ANDROID_COUNTRY
    min_date = _backfill_since() if backfill else None

    print(f"[Android] 正在抓取 {app_name} 的評論（{'回溯模式' if backfill else '增量模式'}）...")

    seen_ids_file = os.path.join(config.DATA_DIR, f"{app_name}_android_seen_ids.json")
    seen_ids, is_fresh = _load_seen_ids(seen_ids_file)

    if is_fresh and not backfill:
        min_date = datetime.now() - timedelta(days=2)
        print(f"[Android] {app_name}：首次執行，僅抓取近 2 天評論（增量保護）")

    if backfill:
        max_pages = max(1, config.BACKFILL_ANDROID_COUNT // _ANDROID_PAGE_SIZE + 1)
    else:
        max_pages = _ANDROID_MAX_PAGES

    new_reviews: list[dict] = []
    current_ids: set[str] = set()
    consecutive_seen = 0
    token = None
    total_fetched = 0

    for page_idx in range(max_pages):
        try:
            if token is None:
                result, token = reviews(
                    app_id,
                    lang=lang,
                    country=country,
                    sort=Sort.NEWEST,
                    count=_ANDROID_PAGE_SIZE,
                )
            else:
                result, token = reviews(app_id, continuation_token=token)
        except Exception as e:
            print(f"[Android] 抓取 {app_name} 第 {page_idx + 1} 頁失敗：{e}")
            break

        if not result:
            break
        total_fetched += len(result)

        stop_by_date = False
        page_consecutive_seen = 0

        for r in result:
            review_id = r["reviewId"]
            current_ids.add(review_id)

            if not backfill and review_id in seen_ids:
                consecutive_seen += 1
                page_consecutive_seen += 1
                continue
            consecutive_seen = 0

            review_date = r["at"]
            if review_date.tzinfo is not None:
                review_date = review_date.replace(tzinfo=None)
            if min_date and review_date < min_date:
                stop_by_date = True
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

        if not backfill and consecutive_seen >= _ANDROID_STOP_AFTER_SEEN:
            break
        if stop_by_date and not backfill:
            break
        if token is None:
            break

        time.sleep(0.3)

    print(f"[Android] {app_name}：Play 取得 {total_fetched} 則，抓到 "
          f"{len(new_reviews)} 則{'歷史' if backfill else '新'}評論")

    _save_seen_ids(seen_ids_file, seen_ids | current_ids)
    return new_reviews


# ──────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────
def run_scraper(backfill: bool = False) -> list[dict]:
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
