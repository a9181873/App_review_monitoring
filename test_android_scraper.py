"""
Android 評論抓取快速測試腳本
"""
from datetime import datetime

from google_play_scraper import Sort, reviews


def test_android(app_id: str):
    print(f"Testing Android reviews for {app_id} ...")
    result, _ = reviews(
        app_id,
        lang="zh-tw",
        country="tw",
        sort=Sort.NEWEST,
        count=20,
    )

    print(f"Total reviews fetched: {len(result)}")
    for r in result:
        replied = "已回覆" if r["replyContent"] else "未回覆"
        print(f"  {r['at']:%Y-%m-%d} | ★{r['score']} | {r['userName']} | {replied}")
        print(f"    {r['content'][:60]}...")
    print()


if __name__ == "__main__":
    test_android("com.taiwanlife.app")
    print("-" * 50)
    test_android("com.taiwanlife.teamwalk")
