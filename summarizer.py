"""
App 評論監測工具 — 摘要報告模組
產出每日 Markdown 格式的評論摘要報告。
"""
import os
from datetime import datetime

import config


def generate_summary(reviews: list[dict], report_path: str) -> tuple[str, str]:
    """
    根據評論清單產出 Markdown 摘要報告。
    :return: (summary_text, email_subject)
    """
    today = datetime.now().strftime("%Y-%m-%d")

    if not reviews:
        summary = f"# App 評論日報 ({today})\n\n今日無新增待處理評論。"
        subject = f"【App 評論日報】{today} ✅ 今日無新增待處理評論"
    else:
        ios_count = sum(1 for r in reviews if r["platform"] == "iOS")
        android_count = sum(1 for r in reviews if r["platform"] == "Android")

        # App 分組統計
        app_stats = {}
        for r in reviews:
            key = r["app_name"]
            app_stats.setdefault(key, {"iOS": 0, "Android": 0})
            app_stats[key][r["platform"]] += 1

        summary = f"# App 評論日報 ({today})\n\n"
        summary += "## 統計摘要\n"
        summary += f"- iOS 新評論：{ios_count} 則\n"
        summary += f"- Android 新評論：{android_count} 則\n\n"

        # 各 App 統計
        for app_name, counts in app_stats.items():
            summary += f"### {app_name}\n"
            summary += f"- iOS: {counts['iOS']} 則 / Android: {counts['Android']} 則\n\n"

        summary += "## 詳細評論清單\n"

        for r in reviews:
            reply_tag = "✅已回覆" if r.get("is_replied") else "⚠️未回覆"
            summary += f"### [{r['platform']}] {r['app_name']} - {r['user_name']} ({r['rating']}星) [{reply_tag}]\n"
            summary += f"- **日期**: {r['date']}\n"
            summary += f"- **分類**: {r.get('category', 'N/A')}\n"
            summary += f"- **情緒**: {r.get('sentiment', 'N/A')}\n"
            summary += f"- **優先度**: {r.get('priority', 'N/A')}\n"
            summary += f"- **內容**: {r['review_text']}\n\n"

        subject = f"【App 評論日報】{today} — iOS {ios_count} 則 / Android {android_count} 則新評論"

    # 確保報告目錄存在
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(summary)

    return summary, subject


if __name__ == "__main__":
    test_reviews = [
        {
            "platform": "iOS",
            "app_name": "台灣人壽",
            "user_name": "TestUser",
            "rating": 5,
            "review_text": "Good",
            "date": "2026-03-10",
            "category": "正面評價",
            "sentiment": "正面",
            "priority": "低",
        }
    ]
    report = os.path.join(config.REPORTS_DIR, "report_test.md")
    summary, subject = generate_summary(test_reviews, report)
    print(f"Subject: {subject}")
    print(f"Summary:\n{summary}")
