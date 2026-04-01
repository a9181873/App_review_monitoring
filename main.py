"""
App 評論監測工具 — 主程式
整合抓取、分類、存檔、摘要、通知等流程。

使用方式：
  python main.py              # 日常增量模式（抓新評論 + 通知）
  python main.py --backfill   # 回溯模式（抓近一年歷史 + AI 分析 + 存入 Excel，不發通知）
  python main.py --weekly     # 產出週報並發送通知
  python main.py --monthly    # 產出月報並發送通知
  python main.py --issues     # 產出關鍵議題追蹤報告

Power Automate Desktop (PAD) 設計考量：
  - 結束碼：0 = 成功，1 = 部分失敗，2 = 完全失敗
  - 最後一行固定輸出 JSON 摘要，方便 PAD 用「執行 DOS 指令」取得 %CommandOutput%
"""
import io
import json
import os
import sys
from datetime import datetime, timedelta

# Windows 終端 UTF-8 支援（避免中文亂碼）
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

import config
from append_to_excel import append_to_excel
from classify_reviews import classify_reviews
from notifier import send_notification
from scraper import run_scraper
from issue_tracker import detect_issues, format_issues_report
from periodic_report import generate_periodic_report
from storage import sync_down, sync_up
from summarizer import generate_summary


def main(backfill: bool = None) -> int:
    """
    執行所有流程，回傳結束碼：
      0 = 成功
      1 = 部分失敗（抓取成功但通知失敗等）
      2 = 嚴重錯誤
    """
    config.ensure_dirs()
    if backfill is None:
        backfill = "--backfill" in sys.argv
    start_time = datetime.now()

    mode_label = "回溯模式（近一年歷史）" if backfill else "增量模式"
    print(f"{'='*50}")
    print(f"  App 評論監測任務啟動：{start_time:%Y-%m-%d %H:%M:%S}")
    print(f"  模式：{mode_label}")
    print(f"{'='*50}\n")

    exit_code = 0

    # 1. 抓取評論
    try:
        reviews = run_scraper(backfill=backfill)
        print(f"\n共抓取到 {len(reviews)} 則{'歷史' if backfill else '新'}評論\n")
    except Exception as e:
        print(f"抓取評論時發生錯誤：{e}")
        _write_pad_output(success=False, error=str(e))
        return 2

    # 2. AI 語意分析 + 分類
    if reviews:
        reviews = classify_reviews(reviews)
        ai_label = "AI 語意分析" if config.GEMINI_API_KEY else "關鍵字分類"
        print(f"{ai_label}完成\n")

    # 3. 更新 Excel 資料庫（所有新評論都存檔）
    excel_filename = "App評論監測_資料庫.xlsx"
    excel_path = os.path.join(config.REPORTS_DIR, excel_filename)
    try:
        # 從 GCS 下載舊 Excel（GCP 環境才會生效）
        sync_down(excel_filename, config.REPORTS_DIR)
        append_to_excel(reviews, excel_path)
        # 將更新後的 Excel 上傳回 GCS
        sync_up(excel_filename, config.REPORTS_DIR)
    except Exception as e:
        print(f"寫入 Excel 失敗：{e}")
        exit_code = 1

    # 4. 篩選「今天或昨天」的評論用於通知（舊評論只存檔不通知）
    if not backfill:
        yesterday = (datetime.now() - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        recent_reviews = []
        for r in reviews:
            try:
                rd = datetime.strptime(r["date"], "%Y-%m-%d %H:%M:%S")
            except (ValueError, KeyError):
                continue
            if rd >= yesterday:
                recent_reviews.append(r)
        old_count = len(reviews) - len(recent_reviews)
        if old_count > 0:
            print(f"已收錄 {old_count} 則較舊評論至 Excel（不納入通知）")
    else:
        recent_reviews = reviews

    # 5. 產出摘要報告（僅含近期評論）
    today_str = datetime.now().strftime("%Y-%m-%d")
    report_path = os.path.join(config.REPORTS_DIR, f"report_{today_str}.md")
    summary, subject = generate_summary(recent_reviews, report_path)
    print(f"摘要報告已產出：{report_path}\n")

    # 6. 發送通知（回溯模式不發通知，避免灌爆）
    notify_results = {}
    if backfill:
        print("[回溯模式] 跳過通知發送（歷史評論不通知）")
    elif not recent_reviews:
        print("無近期新評論，跳過通知發送")
    else:
        notify_results = send_notification(
            subject, summary,
            attachments=[excel_path] if os.path.exists(excel_path) else None,
        )
        for channel, success in notify_results.items():
            status = "成功" if success else "失敗或未設定"
            print(f"  {channel}: {status}")
        if notify_results and not any(notify_results.values()):
            exit_code = max(exit_code, 1)

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    print(f"\n{'='*50}")
    print(f"  任務完成：{end_time:%Y-%m-%d %H:%M:%S}（耗時 {duration:.1f} 秒）")
    print(f"{'='*50}")

    _write_pad_output(
        success=(exit_code == 0),
        mode="backfill" if backfill else "incremental",
        review_count=len(reviews),
        notified_count=len(recent_reviews) if not backfill else len(reviews),
        report_path=report_path,
        excel_path=excel_path,
        subject=subject,
        notify_results=notify_results,
    )
    return exit_code


def _write_pad_output(**data):
    """將結構化結果寫到 reports/latest_result.json 並印到 stdout。"""
    result_path = os.path.join(config.REPORTS_DIR, "latest_result.json")
    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n__PAD_RESULT__:{json.dumps(data, ensure_ascii=False)}")


# ──────────────────────────────────────────────
# GCP Cloud Functions 入口點
# ──────────────────────────────────────────────
def cloud_function_handler(request):
    """Cloud Functions HTTP 觸發入口（增量模式）。"""
    try:
        exit_code = main()
        status = "success" if exit_code == 0 else "partial_failure"
        return {"status": status, "exit_code": exit_code}, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


def cloud_function_backfill_handler(request):
    """Cloud Functions HTTP 觸發入口（回溯模式）。"""
    try:
        exit_code = main(backfill=True)
        status = "success" if exit_code == 0 else "partial_failure"
        return {"status": status, "exit_code": exit_code}, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


# ──────────────────────────────────────────────
# 週報/月報 & 議題追蹤 入口
# ──────────────────────────────────────────────
def run_periodic_report(period: str) -> int:
    """產出週報或月報並發送通知。"""
    config.ensure_dirs()
    report, subject, report_path = generate_periodic_report(period)
    print(f"\n{subject}\n")

    notify_results = send_notification(subject, report)
    for channel, success in notify_results.items():
        status = "成功" if success else "失敗或未設定"
        print(f"  {channel}: {status}")

    _write_pad_output(
        success=True, mode=period, report_path=report_path,
        subject=subject, notify_results=notify_results,
    )
    return 0


def run_issue_tracking(period_days: int = 7) -> int:
    """產出關鍵議題追蹤報告並發送通知。"""
    config.ensure_dirs()
    issues = detect_issues(period_days=period_days)
    report = format_issues_report(issues, period_days=period_days)
    subject = f"【App 關鍵議題追蹤】近 {period_days} 天 — {len(issues)} 個議題"

    report_path = os.path.join(
        config.REPORTS_DIR,
        f"issues_{datetime.now():%Y-%m-%d}.md",
    )
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"議題報告已產出：{report_path}\n")

    notify_results = send_notification(subject, report)
    for channel, success in notify_results.items():
        status = "成功" if success else "失敗或未設定"
        print(f"  {channel}: {status}")

    _write_pad_output(
        success=True, mode="issues", issue_count=len(issues),
        report_path=report_path, subject=subject, notify_results=notify_results,
    )
    return 0


if __name__ == "__main__":
    if "--weekly" in sys.argv:
        sys.exit(run_periodic_report("week"))
    elif "--monthly" in sys.argv:
        sys.exit(run_periodic_report("month"))
    elif "--issues" in sys.argv:
        sys.exit(run_issue_tracking())
    else:
        sys.exit(main())
