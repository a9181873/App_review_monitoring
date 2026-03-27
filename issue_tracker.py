"""
App 評論監測工具 — 關鍵議題追蹤模組
自動從評論中歸納高頻問題，追蹤議題是否在新版本改善。
使用 Gemini AI（若可用）或關鍵字頻率統計。
"""
import json
import os
from collections import Counter
from datetime import datetime, timedelta

import pandas as pd

import config

ISSUES_FILE = os.path.join(config.DATA_DIR, "tracked_issues.json")

# 預設關鍵字群組（fallback，無 AI 時使用）
DEFAULT_ISSUE_KEYWORDS = {
    "閃退/當機": ["閃退", "當機", "crash", "崩潰", "閃掉", "強制關閉"],
    "登入問題": ["登入", "登不進", "無法登入", "login", "帳號", "密碼錯誤", "驗證"],
    "載入緩慢": ["慢", "lag", "卡", "轉圈", "載入", "loading", "等很久"],
    "介面問題": ["介面", "UI", "畫面", "版面", "跑版", "顯示異常", "亂掉"],
    "通知問題": ["通知", "推播", "沒收到", "notification"],
    "更新後異常": ["更新後", "更新", "新版", "升級後"],
    "功能缺失": ["希望", "建議", "可以增加", "拜託", "應該要有", "缺少"],
}


def _load_tracked_issues() -> dict:
    """載入已追蹤的議題紀錄。"""
    if os.path.exists(ISSUES_FILE):
        with open(ISSUES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"issues": [], "last_updated": None}


def _save_tracked_issues(data: dict):
    """儲存議題紀錄。"""
    os.makedirs(os.path.dirname(ISSUES_FILE), exist_ok=True)
    data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ISSUES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _keyword_based_detection(reviews_df: pd.DataFrame) -> list[dict]:
    """用關鍵字比對找出高頻議題。"""
    issue_counts: dict[str, list] = {}

    for issue_name, keywords in DEFAULT_ISSUE_KEYWORDS.items():
        matched_reviews = []
        for _, row in reviews_df.iterrows():
            text = str(row.get("review_text", "")).lower()
            if any(kw.lower() in text for kw in keywords):
                matched_reviews.append({
                    "review_id": str(row.get("review_id", "")),
                    "text": str(row.get("review_text", ""))[:100],
                    "rating": int(row["rating"]) if pd.notna(row.get("rating")) else 0,
                    "date": str(row.get("date", "")),
                    "app_name": str(row.get("app_name", "")),
                    "platform": str(row.get("platform", "")),
                })
        if matched_reviews:
            issue_counts[issue_name] = matched_reviews

    # 依出現次數排序
    sorted_issues = sorted(issue_counts.items(), key=lambda x: len(x[1]), reverse=True)
    return [
        {
            "issue_name": name,
            "count": len(matched),
            "avg_rating": sum(r["rating"] for r in matched) / len(matched),
            "sample_reviews": matched[:5],
            "apps_affected": list(set(r["app_name"] for r in matched)),
        }
        for name, matched in sorted_issues
    ]


def _ai_based_detection(reviews_df: pd.DataFrame) -> list[dict] | None:
    """用 Gemini AI 歸納議題（若 API 可用）。"""
    if not config.GEMINI_API_KEY:
        return None

    try:
        import google.generativeai as genai
    except ImportError:
        return None

    # 取最近的負面評論（1~3星）作為分析素材
    low_reviews = reviews_df[reviews_df["rating"] <= 3] if "rating" in reviews_df.columns else reviews_df
    if len(low_reviews) == 0:
        return []

    # 最多取 50 則避免 token 過長
    sample = low_reviews.head(50)
    reviews_text = "\n".join(
        f"[{row.get('app_name', '')}][{row.get('platform', '')}][{int(row.get('rating', 0))}星] {str(row.get('review_text', ''))[:150]}"
        for _, row in sample.iterrows()
    )

    prompt = f"""你是 App 評論分析專家。以下是近期的低分評論（1~3星），請歸納出主要的問題議題。

評論清單：
{reviews_text}

請以 JSON 陣列格式回覆，每個議題包含：
- issue_name: 議題名稱（簡短，如「閃退問題」「登入異常」）
- description: 問題描述（一句話）
- severity: 嚴重度（高/中/低）
- count: 約略涉及幾則評論
- apps_affected: 影響的 App 名稱列表

只回覆 JSON，不要其他文字。按嚴重度和數量排序。"""

    try:
        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        text = response.text.strip()
        # 清理 markdown code block
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
        return json.loads(text)
    except Exception as e:
        print(f"[議題追蹤] AI 分析失敗：{e}，fallback 到關鍵字")
        return None


def detect_issues(period_days: int = 7) -> list[dict]:
    """
    偵測近 N 天的關鍵議題。
    優先用 AI，fallback 到關鍵字。
    """
    excel_path = os.path.join(config.REPORTS_DIR, "App評論監測_資料庫.xlsx")
    if not os.path.exists(excel_path):
        print("[議題追蹤] Excel 資料庫不存在，無法分析")
        return []

    df = pd.read_excel(excel_path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        cutoff = datetime.now() - timedelta(days=period_days)
        df = df[df["date"] >= cutoff]

    if len(df) == 0:
        print(f"[議題追蹤] 近 {period_days} 天無評論資料")
        return []

    print(f"[議題追蹤] 分析近 {period_days} 天的 {len(df)} 則評論...")

    # 優先 AI
    issues = _ai_based_detection(df)
    method = "AI"
    if issues is None:
        issues = _keyword_based_detection(df)
        method = "關鍵字"

    print(f"[議題追蹤] 使用{method}分析，發現 {len(issues)} 個議題")

    # 更新追蹤紀錄
    tracked = _load_tracked_issues()
    tracked["issues"] = issues
    _save_tracked_issues(tracked)

    return issues


def format_issues_report(issues: list[dict], period_days: int = 7) -> str:
    """將議題列表格式化為 Markdown 報告。"""
    now = datetime.now()
    report = f"# 關鍵議題追蹤報告（近 {period_days} 天）\n"
    report += f"分析時間：{now:%Y-%m-%d %H:%M}\n\n"

    if not issues:
        report += "本期間未偵測到顯著議題。\n"
        return report

    for i, issue in enumerate(issues, 1):
        name = issue.get("issue_name", "未知議題")
        count = issue.get("count", 0)
        severity = issue.get("severity", "")
        desc = issue.get("description", "")
        apps = issue.get("apps_affected", [])
        avg_rating = issue.get("avg_rating")

        severity_icon = {"高": "🔴", "中": "🟡", "低": "🟢"}.get(severity, "⚪")

        report += f"## {i}. {severity_icon} {name}（{count} 則）\n"
        if desc:
            report += f"- 說明：{desc}\n"
        if severity:
            report += f"- 嚴重度：{severity}\n"
        if avg_rating is not None:
            report += f"- 平均星等：{avg_rating:.1f}\n"
        if apps:
            report += f"- 影響 App：{', '.join(apps)}\n"

        # 範例評論
        samples = issue.get("sample_reviews", [])
        if samples:
            report += "- 代表評論：\n"
            for s in samples[:3]:
                report += f"  - [{s.get('platform', '')}] {s.get('text', '')}\n"
        report += "\n"

    return report


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    found = detect_issues(period_days=days)
    print(format_issues_report(found, period_days=days))
