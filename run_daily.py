"""
每日評論監測 — 輕量模式（不含 AI 語意分析）
僅抓取新評論 + 輸出摘要，適合 cron / Docker 排程。
"""
import os
import sys

os.chdir("/opt/data/app_review_monitor")
os.environ.setdefault("EMAIL_ENABLED", "false")
os.environ.setdefault("TEAMS_ENABLED", "false")

from dotenv import load_dotenv
load_dotenv()

import config
from scraper import run_scraper
from summarizer import generate_summary

config.ensure_dirs()

try:
    reviews = run_scraper(backfill=False)
except Exception as e:
    print(f"❌ 抓取失敗：{e}")
    sys.exit(1)

today_str = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
report_path = os.path.join(config.REPORTS_DIR, f"report_{today_str}.md")
summary, subject = generate_summary(reviews, report_path)

print(summary)

# 簡要統計
ios_count = sum(1 for r in reviews if r["platform"] == "iOS")
android_count = sum(1 for r in reviews if r["platform"] == "Android")
edited_count = sum(1 for r in reviews if r.get("is_edited"))

parts = [f"iOS {ios_count}", f"Android {android_count}"]
if edited_count:
    parts.append(f"編輯 {edited_count}")
print(f"\n📊 {' / '.join(parts)} 則")
