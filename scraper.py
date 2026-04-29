"""
App 評論監測工具 — 評論抓取模組
支援 iOS App Store 與 Google Play，增量抓取新評論並自動去重。
支援回溯模式（--backfill）抓取近一年歷史評論。

2026-04 更新：
  - iOS：優先走 App Store Connect API（JWT 認證，即時資料），失敗時降級到
    iTunes RSS。ASC 路徑會自動過濾「開發者已回復」的評論以免重複通知。
  - iOS RSS（降級路徑）：自家實作直呼 iTunes RSS 並輪替瀏覽器 UA，繞過套件
    0.2.0 的 UA 封鎖問題。注意 RSS 本身有 24–72 小時 CDN 快取延遲。
  - Android：改用 continuation_token 迴圈分頁，遇到已見 ID 連續出現就停，
    避免單次 count=200 漏掉爆量新評論。
"""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from google_play_scraper import Sort, reviews

import config
import ios_asc
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
_ANDROID_STOP_AFTER_SEEN = 50  # 連續遇到 50 則已見 ID 才停


def _backfill_since() -> datetime:
    """回溯模式的時間範圍（近一年），每次呼叫時即時計算。"""
    return datetime.now() - timedelta(days=365)


# ──────────────────────────────────────────────
# 已見評論狀態管理（改用 {id: fingerprint} 偵測編輯）
# ──────────────────────────────────────────────
def _review_fingerprint(content: str, rating: int) -> str:
    """以內容+星數的 SHA1 前 16 碼當作評論指紋；變更即視為編輯。"""
    raw = f"{content or ''}|{rating}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def _load_seen_ids(filepath: str) -> tuple[dict, bool]:
    """
    載入已見評論狀態。回傳 (seen_dict, is_fresh)。
    seen_dict: {review_id: fingerprint_or_None}
    向下相容：舊版檔案是字串 list，會轉成 {id: None}（首次執行不會誤判編輯）。
    """
    filename = os.path.basename(filepath)
    sync_down(filename)

    if not os.path.exists(filepath):
        return {}, True

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        # 舊格式：list of review_id
        return {rid: None for rid in data}, False
    if isinstance(data, dict):
        return data, False
    return {}, True


def _save_seen_ids(filepath: str, seen_dict: dict):
    parent = os.path.dirname(filepath)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(seen_dict, f, ensure_ascii=False)

    filename = os.path.basename(filepath)
    sync_up(filename)


def _classify_review(
    review_id: str, fingerprint: str, seen_dict: dict,
) -> str:
    """
    依 seen_dict 判斷評論狀態：
      "new"     — 從未見過
      "edited"  — 看過但內容/星數變了（編輯）
      "seen"    — 看過且未變
      "legacy"  — 看過但舊檔沒指紋資料（無法判斷，視為已見不通知）
    """
    if review_id not in seen_dict:
        return "new"
    prior = seen_dict[review_id]
    if prior is None:
        return "legacy"
    if prior == fingerprint:
        return "seen"
    return "edited"


# ──────────────────────────────────────────────
# iOS (ASC API) 主路徑
# ──────────────────────────────────────────────
def _get_ios_reviews_via_asc(
    app_name: str, app_id: str, backfill: bool,
) -> list[dict]:
    """
    透過 App Store Connect API 抓取 iOS 評論。
    過濾掉「開發者已回復」的評論，避免重複通知。
    """
    max_reviews = 1000 if backfill else 400
    raw = ios_asc.fetch_reviews(app_id, max_reviews=max_reviews)

    # ASC review_id 格式與 RSS 不同（UUID vs 數字），用獨立檔案避免誤判
    seen_ids_file = os.path.join(config.DATA_DIR, f"{app_name}_ios_asc_seen_ids.json")
    seen_dict, is_fresh = _load_seen_ids(seen_ids_file)

    if backfill:
        min_date = _backfill_since()
    elif is_fresh:
        min_date = datetime.now() - timedelta(days=2)
        print(f"[iOS/ASC] {app_name}：首次執行，僅抓取近 2 天評論（增量保護）")
    else:
        min_date = None

    new_reviews: list[dict] = []
    updated_dict: dict = dict(seen_dict)
    skipped_replied = 0
    edited_count = 0

    for item in raw:
        review_id = item["review_id"]
        text = item["content"] or ""
        if item.get("title"):
            text = f"{item['title']}\n{text}".strip()
        rating = item["rating"]
        fingerprint = _review_fingerprint(text, rating)

        status = _classify_review(review_id, fingerprint, seen_dict)
        updated_dict[review_id] = fingerprint

        if not backfill and status in ("seen", "legacy"):
            continue

        date_obj = item["date_obj"]
        if min_date and date_obj and date_obj < min_date:
            continue

        # 已回復的評論不納入通知（標記為已見，之後不再處理）
        if item.get("has_response"):
            skipped_replied += 1
            continue

        formatted_date = (
            date_obj.strftime("%Y-%m-%d %H:%M:%S") if date_obj else ""
        )
        is_edited = (status == "edited")
        if is_edited:
            edited_count += 1

        new_reviews.append({
            "platform": "iOS",
            "app_name": app_name,
            "user_name": item["user_name"],
            "rating": rating,
            "review_text": text,
            "date": formatted_date,
            "review_id": review_id,
            "is_edited": is_edited,
        })

    msg = (
        f"[iOS/ASC] {app_name}：ASC 取得 {len(raw)} 則，"
        f"抓到 {len(new_reviews)} 則{'歷史' if backfill else '新'}評論"
    )
    if edited_count:
        msg += f"（含 {edited_count} 則編輯更新）"
    if skipped_replied:
        msg += f"（略過 {skipped_replied} 則已回復）"
    print(msg)

    _save_seen_ids(seen_ids_file, updated_dict)
    return new_reviews


# ──────────────────────────────────────────────
# iOS (iTunes RSS) 降級路徑
# ──────────────────────────────────────────────
def _fetch_ios_rss_page(country: str, app_id: str, page: int) -> dict:
    """抓單頁 iTunes RSS。每個 UA 最多試 1 次。"""
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
            feed = data.get("feed", {}) or {}
            if feed.get("entry"):
                return data
            if idx < len(_IOS_UAS) - 1:
                time.sleep(1 + idx)
        except (urllib.error.URLError, urllib.error.HTTPError,
                TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            if idx < len(_IOS_UAS) - 1:
                time.sleep(2 ** idx)

    if last_data is not None:
        return last_data
    raise RuntimeError(f"iOS RSS page {page} 所有 UA 皆失敗：{last_err}")


def _parse_ios_rss_entry(entry: dict) -> dict | None:
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
        print(f"[iOS/RSS] 解析評論條目失敗，略過：{e}")
        return None


def _get_ios_reviews_via_rss(
    app_name: str, app_id: str, country: str, backfill: bool,
) -> list[dict]:
    """iTunes RSS 降級抓取（ASC 未設定或失敗時使用）。"""
    seen_ids_file = os.path.join(config.DATA_DIR, f"{app_name}_ios_seen_ids.json")
    seen_dict, is_fresh = _load_seen_ids(seen_ids_file)

    if backfill:
        min_date = _backfill_since()
    elif is_fresh:
        min_date = datetime.now() - timedelta(days=2)
        print(f"[iOS/RSS] {app_name}：首次執行，僅抓取近 2 天評論（增量保護）")
    else:
        min_date = None

    new_reviews: list[dict] = []
    updated_dict: dict = dict(seen_dict)
    total_fetched = 0
    edited_count = 0

    for page in range(1, _IOS_RSS_PAGE_LIMIT + 1):
        try:
            data = _fetch_ios_rss_page(country, app_id, page)
        except Exception as e:
            print(f"[iOS/RSS] {app_name} page {page} 失敗：{e}")
            break

        feed = data.get("feed", {}) or {}
        entries = feed.get("entry")
        if not entries:
            break
        if not isinstance(entries, list):
            entries = [entries]

        total_fetched += len(entries)
        page_all_skip = True
        stop_by_date = False

        for entry in entries:
            parsed = _parse_ios_rss_entry(entry)
            if not parsed:
                continue
            review_id = parsed["review_id"]

            text = parsed["content"] or ""
            if parsed["title"]:
                text = f"{parsed['title']}\n{text}".strip()
            rating = parsed["rating"]
            fingerprint = _review_fingerprint(text, rating)

            status = _classify_review(review_id, fingerprint, seen_dict)
            updated_dict[review_id] = fingerprint

            if not backfill and status in ("seen", "legacy"):
                continue
            page_all_skip = False

            date_obj = parsed["date_obj"]
            if min_date and date_obj and date_obj < min_date:
                stop_by_date = True
                continue

            formatted_date = (
                date_obj.strftime("%Y-%m-%d %H:%M:%S") if date_obj else ""
            )
            is_edited = (status == "edited")
            if is_edited:
                edited_count += 1

            new_reviews.append({
                "platform": "iOS",
                "app_name": app_name,
                "user_name": parsed["user_name"],
                "rating": rating,
                "review_text": text,
                "date": formatted_date,
                "review_id": review_id,
                "is_edited": is_edited,
            })

        if not backfill and page_all_skip and seen_dict:
            break
        if stop_by_date and not backfill:
            break

        time.sleep(0.3)

    msg = (
        f"[iOS/RSS] {app_name}：RSS 取得 {total_fetched} 則，抓到 "
        f"{len(new_reviews)} 則{'歷史' if backfill else '新'}評論"
    )
    if edited_count:
        msg += f"（含 {edited_count} 則編輯更新）"
    print(msg)

    if total_fetched == 0:
        print(f"[iOS/RSS] ⚠️ {app_name}：RSS 回傳 0 則評論，可能被 Apple 封鎖！")

    _save_seen_ids(seen_ids_file, updated_dict)
    return new_reviews


def get_ios_reviews(
    app_name: str, app_id: str, country: str = None, backfill: bool = False,
) -> list[dict]:
    """
    抓取 iOS 評論。優先走 ASC API，未設定或失敗時降級到 iTunes RSS。
    ASC 路徑會自動過濾已回復的評論。
    """
    country = (country or config.IOS_COUNTRY).lower()
    print(f"[iOS] 正在抓取 {app_name} 的評論{'（回溯模式）' if backfill else ''} ...")

    if ios_asc.is_configured():
        try:
            return _get_ios_reviews_via_asc(app_name, app_id, backfill)
        except Exception as e:
            print(f"[iOS/ASC] {app_name} 失敗，降級至 RSS：{e}")
    else:
        print(f"[iOS] ASC API 未設定，使用 RSS（注意：RSS 有 24–72 小時延遲）")

    return _get_ios_reviews_via_rss(app_name, app_id, country, backfill)


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
    seen_dict, is_fresh = _load_seen_ids(seen_ids_file)

    if is_fresh and not backfill:
        min_date = datetime.now() - timedelta(days=2)
        print(f"[Android] {app_name}：首次執行，僅抓取近 2 天評論（增量保護）")

    if backfill:
        max_pages = max(1, config.BACKFILL_ANDROID_COUNT // _ANDROID_PAGE_SIZE + 1)
    else:
        max_pages = _ANDROID_MAX_PAGES

    new_reviews: list[dict] = []
    updated_dict: dict = dict(seen_dict)
    consecutive_skip = 0
    edited_count = 0
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

        for r in result:
            review_id = r["reviewId"]
            content = r["content"] or ""
            rating = r["score"]
            fingerprint = _review_fingerprint(content, rating)

            status = _classify_review(review_id, fingerprint, seen_dict)
            updated_dict[review_id] = fingerprint

            if not backfill and status in ("seen", "legacy"):
                consecutive_skip += 1
                continue
            consecutive_skip = 0

            review_date = r["at"]
            if review_date.tzinfo is not None:
                review_date = review_date.replace(tzinfo=None)
            if min_date and review_date < min_date:
                stop_by_date = True
                continue

            is_edited = (status == "edited")
            if is_edited:
                edited_count += 1

            new_reviews.append({
                "platform": "Android",
                "app_name": app_name,
                "user_name": r["userName"],
                "rating": rating,
                "review_text": content,
                "date": review_date.strftime("%Y-%m-%d %H:%M:%S"),
                "review_id": review_id,
                "is_edited": is_edited,
            })

        if not backfill and consecutive_skip >= _ANDROID_STOP_AFTER_SEEN:
            break
        if stop_by_date and not backfill:
            break
        if token is None:
            break

        time.sleep(0.3)

    msg = (
        f"[Android] {app_name}：Play 取得 {total_fetched} 則，抓到 "
        f"{len(new_reviews)} 則{'歷史' if backfill else '新'}評論"
    )
    if edited_count:
        msg += f"（含 {edited_count} 則編輯更新）"
    print(msg)

    _save_seen_ids(seen_ids_file, updated_dict)
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
