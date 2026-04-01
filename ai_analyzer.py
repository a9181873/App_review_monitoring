"""
App 評論監測工具 — AI 語意分析模組
使用 Google Gemini API (免費方案) 進行評論的情緒分析與分類。
"""
import json
import time

import requests

import config


GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"


ANALYSIS_PROMPT = """你是一個 App 評論分析專家。請分析以下 App 評論，對每則評論回傳 JSON 格式的分析結果。

每則評論請回傳：
- category: 分類（程式錯誤/功能建議/UX體驗/正面評價/客服問題/帳號問題/效能問題/其他）
- sentiment: 情緒（正面/負面/中性）
- priority: 優先度（高/中/低）
- summary: 一句話摘要（15字以內）

重要：辨識反諷與諷刺語氣
- 「客服有在運作嗎？」「有人在管嗎？」「這公司還活著嗎？」→ 這些是諷刺，實際情緒為負面，分類為客服問題，優先度高
- 「真的很『好用』呢」「五星好評（反話）」→ 表面正面但實際負面，需看上下文與星級判斷
- 星級與文字矛盾時（如 1 星寫正面話），以星級為準判斷真實情緒

規則：
- 1-2 星且提到 bug/閃退/當機/錯誤 → 程式錯誤 + 負面 + 高
- 1-2 星的負面評論 → 優先度高
- 3 星 → 優先度中
- 4-5 星正面 → 優先度低
- 提到登入/密碼/驗證 → 帳號問題
- 提到慢/卡/載入 → 效能問題
- 提到客服/回覆/處理/沒人管/沒人理 → 客服問題
- 疑問句式（「...嗎？」）搭配低星級 → 通常是諷刺，視為負面

請以嚴格 JSON 陣列格式回傳，不要加任何 markdown 標記：
[{{"category":"...","sentiment":"...","priority":"...","summary":"..."}}, ...]

評論列表：
"""


def analyze_reviews_batch(reviews: list[dict], batch_size: int = 10) -> list[dict]:
    """
    批次送 Gemini 分析評論。
    每批 batch_size 則，自動處理 rate limit。
    """
    if not reviews:
        return reviews

    if not config.GEMINI_API_KEY:
        print("[AI] 未設定 GEMINI_API_KEY，使用關鍵字分類 fallback")
        return _keyword_fallback(reviews)

    analyzed = []
    for i in range(0, len(reviews), batch_size):
        batch = reviews[i : i + batch_size]
        prompt = ANALYSIS_PROMPT

        for idx, r in enumerate(batch):
            prompt += f"\n{idx + 1}. [{r.get('platform', '?')}] {r.get('app_name', '?')} - "
            prompt += f"{r.get('rating', '?')}星 - {r.get('review_text', '')}\n"

        try:
            resp = requests.post(
                GEMINI_API_URL,
                params={"key": config.GEMINI_API_KEY},
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=60,
            )
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            # 移除可能的 markdown code block
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0]
            results = json.loads(text)

            for j, r in enumerate(batch):
                if j < len(results):
                    r.update(results[j])
                else:
                    r.update(_keyword_single(r))
                analyzed.append(r)

            print(f"[AI] 已分析 {min(i + batch_size, len(reviews))}/{len(reviews)} 則評論")

            # Gemini free tier: 15 RPM → 成功時每批次間隔 4 秒
            if i + batch_size < len(reviews):
                time.sleep(4)

        except Exception as e:
            print(f"[AI] 批次分析失敗：{e}，此批次使用 fallback")
            for r in batch:
                r.update(_keyword_single(r))
                analyzed.append(r)

    return analyzed


def _keyword_single(r: dict) -> dict:
    """單則評論的關鍵字 fallback 分類。"""
    text = r.get("review_text", "").lower()
    rating = r.get("rating", 3)

    keyword_map = {
        "程式錯誤": ["閃退", "當機", "錯誤", "bug", "不能用", "無法登入", "失敗", "黑屏", "白屏", "卡住"],
        "客服問題": ["客服", "回覆", "沒人管", "沒人理", "處理", "反映", "投訴", "有在運作", "有人在管"],
        "功能建議": ["希望", "建議", "功能", "優化", "增加", "改善", "如果可以", "能不能"],
        "UX體驗": ["難用", "複雜", "找不到", "介面", "字太小", "操作", "不直覺", "廣告"],
        "帳號問題": ["登入", "密碼", "驗證", "帳號", "認證", "otp"],
        "效能問題": ["慢", "卡", "載入", "等很久", "lag", "延遲"],
        "正面評價": ["好用", "棒", "讚", "方便", "五星", "感謝", "推", "滿意", "不錯"],
    }

    category = "其他"
    for cat, keywords in keyword_map.items():
        if any(kw in text for kw in keywords):
            category = cat
            break

    if category == "程式錯誤":
        return {"category": category, "sentiment": "負面", "priority": "高", "summary": "程式異常回報"}
    elif category == "正面評價":
        return {"category": category, "sentiment": "正面", "priority": "低", "summary": "正面使用回饋"}
    elif rating <= 2:
        return {"category": category, "sentiment": "負面", "priority": "高", "summary": "低分負面評論"}
    elif rating >= 4:
        return {"category": category, "sentiment": "正面", "priority": "低", "summary": "高分正面評論"}
    else:
        return {"category": category, "sentiment": "中性", "priority": "中", "summary": "一般意見回饋"}


def _keyword_fallback(reviews: list[dict]) -> list[dict]:
    """全部使用關鍵字 fallback。"""
    for r in reviews:
        r.update(_keyword_single(r))
    return reviews
