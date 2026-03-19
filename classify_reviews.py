"""
App 評論監測工具 — 評論分類模組
優先使用 AI (Gemini) 語意分析，若 API 不可用則 fallback 到關鍵字比對。
"""
from ai_analyzer import analyze_reviews_batch

import config


def classify_reviews(reviews: list[dict]) -> list[dict]:
    """
    分類評論：優先用 Gemini AI，fallback 用關鍵字。
    """
    if not reviews:
        return []

    return analyze_reviews_batch(reviews, batch_size=config.AI_BATCH_SIZE)


if __name__ == "__main__":
    test_reviews = [
        {"review_text": "這款 App 閃退嚴重，根本不能用！", "rating": 1,
         "platform": "iOS", "app_name": "Test"},
        {"review_text": "介面很漂亮，但功能可以再多一點。", "rating": 4,
         "platform": "Android", "app_name": "Test"},
    ]
    print(classify_reviews(test_reviews))
