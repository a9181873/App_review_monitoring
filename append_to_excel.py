"""
App 評論監測工具 — Excel 資料庫模組
將評論追加到 Excel 檔案並自動去重。
"""
import os

import pandas as pd

import config


def append_to_excel(reviews: list[dict], excel_path: str):
    """將新評論追加到 Excel 檔案，依 review_id 去重。"""
    if not reviews:
        print("📊 無新評論需要寫入 Excel")
        return

    df_new = pd.DataFrame(reviews)

    if os.path.exists(excel_path):
        df_old = pd.read_excel(excel_path)
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
        df_combined = df_combined.drop_duplicates(subset=["review_id"], keep="first")
    else:
        os.makedirs(os.path.dirname(excel_path), exist_ok=True)
        df_combined = df_new

    df_combined.to_excel(excel_path, index=False)
    print(f"📊 Excel 資料庫已更新：{excel_path}（共 {len(df_combined)} 筆）")


if __name__ == "__main__":
    test_reviews = [
        {
            "platform": "iOS",
            "app_name": "台灣人壽",
            "user_name": "TestUser",
            "rating": 5,
            "review_text": "Good",
            "date": "2026-03-10",
            "review_id": "test_123",
        }
    ]
    test_path = os.path.join(config.REPORTS_DIR, "test_db.xlsx")
    append_to_excel(test_reviews, test_path)
