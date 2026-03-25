"""
抓取台灣人壽近 2 年 iOS + Android 評論，並匯出至 Excel。
"""
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

# 確保 parent 資料夾在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
config.ensure_dirs()

from app_store_web_scraper import AppStoreEntry
from google_play_scraper import Sort, reviews

TWO_YEARS_AGO = datetime.now() - timedelta(days=730)
APP_NAME = "台灣人壽"
IOS_APP_ID = "1035225274"
ANDROID_APP_ID = "com.taiwanlife.app"


def fetch_ios_reviews():
    """使用 app-store-web-scraper 抓取 iOS 評論。"""
    print(f"[iOS] 正在抓取 {APP_NAME} 近 2 年評論 ...")
    app = AppStoreEntry(app_id=IOS_APP_ID, country="tw")
    all_reviews = []
    for r in app.reviews(limit=500):
        try:
            date_obj = r.date.replace(tzinfo=None)
        except Exception:
            continue
        if date_obj < TWO_YEARS_AGO:
            continue
        all_reviews.append({
            "platform": "iOS",
            "app_name": APP_NAME,
            "review_id": str(r.id),
            "user_name": r.user_name,
            "rating": r.rating,
            "title": r.title,
            "review_text": r.content,
            "date": date_obj.strftime("%Y-%m-%d %H:%M:%S"),
            "app_version": r.app_version,
        })
    print(f"[iOS] 共取得 {len(all_reviews)} 則近 2 年評論")
    return all_reviews


def fetch_android_reviews():
    """使用 google_play_scraper 抓取 Android 評論。"""
    print(f"[Android] 正在抓取 {APP_NAME} 近 2 年評論 ...")
    all_reviews = []
    try:
        result, _ = reviews(
            ANDROID_APP_ID,
            lang="zh-tw",
            country="tw",
            sort=Sort.NEWEST,
            count=3000,
        )
    except Exception as e:
        print(f"[Android] 抓取失敗：{e}")
        return []

    for r in result:
        review_date = r["at"]
        if review_date.tzinfo is not None:
            review_date = review_date.replace(tzinfo=None)
        if review_date < TWO_YEARS_AGO:
            continue

        is_replied = r.get("replyContent") is not None
        all_reviews.append({
            "platform": "Android",
            "app_name": APP_NAME,
            "review_id": r["reviewId"],
            "user_name": r["userName"],
            "rating": r["score"],
            "title": "",
            "review_text": r["content"],
            "date": review_date.strftime("%Y-%m-%d %H:%M:%S"),
            "app_version": r.get("reviewCreatedVersion", ""),
            "is_replied": is_replied,
            "reply_text": r.get("replyContent", ""),
        })
    print(f"[Android] 共取得 {len(all_reviews)} 則近 2 年評論")
    return all_reviews


if __name__ == "__main__":
    ios_reviews = fetch_ios_reviews()
    android_reviews = fetch_android_reviews()

    all_data = ios_reviews + android_reviews
    if not all_data:
        print("無評論資料")
        sys.exit(1)

    df = pd.DataFrame(all_data)
    output_file = os.path.join(config.DATA_DIR, f"{APP_NAME}_近2年評論_{datetime.now():%Y%m%d}.xlsx")
    df.to_excel(output_file, index=False, engine="openpyxl")
    print(f"\n✅ 匯出完成：{output_file}")
    print(f"   iOS: {len(ios_reviews)} 則, Android: {len(android_reviews)} 則, 合計: {len(all_data)} 則")
