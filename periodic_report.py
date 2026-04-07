"""
App 評論監測工具 — 週報/月報彙整模組
從 Excel 資料庫讀取歷史評論，產出週報或月報。
"""
import os
from datetime import datetime, timedelta

import pandas as pd

import config


def _load_reviews(excel_path: str) -> pd.DataFrame:
    """載入 Excel 資料庫，回傳 DataFrame。"""
    if not os.path.exists(excel_path):
        print(f"[週報/月報] Excel 資料庫不存在：{excel_path}")
        return pd.DataFrame()
    df = pd.read_excel(excel_path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def _filter_by_period(df: pd.DataFrame, period: str) -> tuple[pd.DataFrame, str, str]:
    """
    依 period ('week' / 'month') 篩選對應時間範圍的評論。
    回傳 (filtered_df, period_label, date_range_str)。
    """
    now = datetime.now()
    if period == "week":
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        label = "週報"
        date_range = f"{start:%Y-%m-%d} ~ {now:%Y-%m-%d}"
    elif period == "month":
        start = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        label = "月報"
        date_range = f"{start:%Y-%m-%d} ~ {now:%Y-%m-%d}"
    else:
        raise ValueError(f"不支援的 period: {period}")

    filtered = df[df["date"] >= start].copy() if "date" in df.columns else df
    return filtered, label, date_range


def _build_report(df: pd.DataFrame, label: str, date_range: str) -> str:
    """從 DataFrame 組出 Markdown 報告。"""
    total = len(df)
    report = f"# App 評論{label} ({date_range})\n\n"

    if total == 0:
        report += "本期間無評論資料。\n"
        return report

    # ── 總覽 ──
    avg_rating = df["rating"].mean() if "rating" in df.columns else 0
    ios_count = len(df[df["platform"] == "iOS"]) if "platform" in df.columns else 0
    android_count = len(df[df["platform"] == "Android"]) if "platform" in df.columns else 0

    report += "## 總覽\n"
    report += f"- 評論總數：{total} 則\n"
    report += f"- 平均星等：{avg_rating:.1f} ⭐\n"
    report += f"- iOS：{ios_count} 則 / Android：{android_count} 則\n\n"

    # ── 各 App 統計 ──
    if "app_name" in df.columns:
        report += "## 各 App 統計\n"
        for app_name, group in df.groupby("app_name"):
            app_avg = group["rating"].mean() if "rating" in group.columns else 0
            report += f"\n### {app_name}\n"
            report += f"- 評論數：{len(group)} 則\n"
            report += f"- 平均星等：{app_avg:.1f}\n"

            # 星等分布
            if "rating" in group.columns:
                report += "- 星等分布："
                for star in range(5, 0, -1):
                    count = len(group[group["rating"] == star])
                    if count > 0:
                        report += f"{star}星({count}) "
                report += "\n"

    # ── 星等趨勢（按天）──
    if "date" in df.columns and "rating" in df.columns:
        report += "\n## 每日平均星等趨勢\n"
        daily = df.set_index("date").resample("D")["rating"].agg(["mean", "count"])
        daily = daily[daily["count"] > 0]
        for date_idx, row in daily.iterrows():
            bar = "█" * int(row["mean"])
            report += f"- {date_idx:%m/%d}：{row['mean']:.1f} {bar}（{int(row['count'])} 則）\n"

    # ── 情緒分布 ──
    if "sentiment" in df.columns:
        report += "\n## 情緒分布\n"
        sentiment_counts = df["sentiment"].value_counts()
        for sentiment, count in sentiment_counts.items():
            pct = count / total * 100
            report += f"- {sentiment}：{count} 則（{pct:.0f}%）\n"

    # ── 分類統計 ──
    if "category" in df.columns:
        report += "\n## 評論分類統計\n"
        cat_counts = df["category"].value_counts().head(10)
        for cat, count in cat_counts.items():
            report += f"- {cat}：{count} 則\n"

    # ── 低分評論摘要（1~2 星）──
    if "rating" in df.columns:
        low = df[df["rating"] <= 2]
        if len(low) > 0:
            report += f"\n## 低分評論（1~2 星，共 {len(low)} 則）\n"
            for _, r in low.head(20).iterrows():
                app = r.get("app_name", "")
                platform = r.get("platform", "")
                user = r.get("user_name", "")
                text = str(r.get("review_text", ""))[:100]
                date_str = r["date"].strftime("%m/%d") if pd.notna(r.get("date")) else ""
                report += f"- [{platform}] {app} — {user}（{int(r['rating'])}星, {date_str}）：{text}\n"

    return report


def generate_periodic_report(period: str = "week") -> tuple[str, str, str]:
    """
    產出週報或月報。
    :param period: 'week' 或 'month'
    :return: (report_text, subject, report_path)
    """
    from storage import sync_down

    excel_filename = "App評論監測_資料庫.xlsx"
    excel_path = os.path.join(config.REPORTS_DIR, excel_filename)
    # GCP 環境須先從 GCS 下載 Excel 資料庫
    sync_down(excel_filename, config.REPORTS_DIR)
    df = _load_reviews(excel_path)
    filtered, label, date_range = _filter_by_period(df, period)

    report = _build_report(filtered, label, date_range)
    subject = f"【App 評論{label}】{date_range} — 共 {len(filtered)} 則評論"

    # 儲存報告
    today_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{period}_report_{today_str}.md"
    report_path = os.path.join(config.REPORTS_DIR, filename)
    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"[{label}] 報告已產出：{report_path}（{len(filtered)} 則評論）")
    return report, subject, report_path


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "week"
    report, subject, path = generate_periodic_report(p)
    print(f"\nSubject: {subject}\n")
    print(report)
