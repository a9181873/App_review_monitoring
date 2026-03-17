"""
App 評論監測工具 — 主程式
整合抓取、分類、存檔、摘要、通知等流程。

Power Automate Desktop (PAD) 設計考量：
  - 結束碼：0 = 成功，1 = 部分失敗，2 = 完全失敗
  - 最後一行固定輸出 JSON 摘要，方便 PAD 用「執行 DOS 指令」取得 %CommandOutput%
  - 摘要報告路徑寫入 JSON，PAD 可直接讀取該檔案作為郵件附件或內容
"""
import json
import os
import sys
from datetime import datetime

import config
from append_to_excel import append_to_excel
from classify_reviews import classify_reviews
from notifier import send_notification
from scraper import run_scraper
from summarizer import generate_summary


def main() -> int:
    """
    執行所有流程，回傳結束碼：
      0 = 成功
      1 = 部分失敗（抓取成功但通知失敗等）
      2 = 嚴重錯誤
    """
    start_time = datetime.now()
    print(f"{'='*50}")
    print(f"  App 評論監測任務啟動：{start_time:%Y-%m-%d %H:%M:%S}")
    print(f"{'='*50}\n")

    exit_code = 0

    # 1. 抓取評論
    try:
        reviews = run_scraper()
        print(f"\n📥 共抓取到 {len(reviews)} 則新評論\n")
    except Exception as e:
        print(f"❌ 抓取評論時發生錯誤：{e}")
        _write_pad_output(success=False, error=str(e))
        return 2

    # 2. 關鍵字分類
    if reviews:
        reviews = classify_reviews(reviews)
        print("✅ 關鍵字分類完成\n")

    # 3. 更新 Excel 資料庫
    excel_path = os.path.join(config.REPORTS_DIR, "App評論監測_資料庫.xlsx")
    try:
        append_to_excel(reviews, excel_path)
    except Exception as e:
        print(f"⚠️ 寫入 Excel 失敗：{e}")
        exit_code = 1

    # 4. 產出摘要報告
    today_str = datetime.now().strftime("%Y-%m-%d")
    report_path = os.path.join(config.REPORTS_DIR, f"report_{today_str}.md")
    summary, subject = generate_summary(reviews, report_path)
    print(f"📝 摘要報告已產出：{report_path}\n")

    # 5. 發送通知（Email / Teams）
    notify_results = send_notification(subject, summary)
    for channel, success in notify_results.items():
        status = "✅ 成功" if success else "⚠️ 失敗或未設定"
        print(f"  {channel}: {status}")
    if notify_results and not any(notify_results.values()):
        exit_code = max(exit_code, 1)

    end_time = datetime.now()
    print(f"\n{'='*50}")
    print(f"  任務完成：{end_time:%Y-%m-%d %H:%M:%S}")
    print(f"{'='*50}")

    # 最後一行輸出 JSON 摘要，供 PAD 的 %CommandOutput% 解析
    _write_pad_output(
        success=(exit_code == 0),
        review_count=len(reviews),
        report_path=report_path,
        excel_path=excel_path,
        subject=subject,
        notify_results=notify_results,
    )
    return exit_code


def _write_pad_output(**data):
    """
    將結構化結果寫到 reports/latest_result.json 並印到 stdout 最後一行。
    PAD 可透過以下兩種方式取得：
      1. 讀取 latest_result.json 檔案
      2. 解析 %CommandOutput% 的最後一行 JSON
    """
    result_path = os.path.join(config.REPORTS_DIR, "latest_result.json")
    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # 最後一行印出 JSON，供 PAD 直接讀取
    print(f"\n__PAD_RESULT__:{json.dumps(data, ensure_ascii=False)}")


if __name__ == "__main__":
    sys.exit(main())
