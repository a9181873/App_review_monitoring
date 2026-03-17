def classify_reviews(reviews):
    """
    使用關鍵字比對進行分類，不需呼叫 AI API。
    """
    if not reviews:
        return []
    
    # 定義關鍵字與分類的對應關係
    keyword_map = {
        '程式錯誤': ['閃退', '當機', '錯誤', 'Bug', '不能用', '無法登入', '失敗', '黑屏', '白屏', '卡住'],
        '功能建議': ['希望', '建議', '功能', '優化', '增加', '改善', '如果可以', '能不能'],
        'UX體驗': ['難用', '複雜', '找不到', '介面', '字太小', '操作', '不直覺', '廣告'],
        '正面評價': ['好用', '棒', '讚', '方便', '五星', '感謝', '推', '滿意', '不錯']
    }
    
    classified_reviews = []
    for r in reviews:
        text = r['review_text'].lower()
        category = '其他問題'
        sentiment = '中性'
        priority = '低'
        
        # 進行關鍵字比對
        for cat, keywords in keyword_map.items():
            if any(kw.lower() in text for kw in keywords):
                category = cat
                break
        
        # 根據分類與評分初步判斷情緒與優先度（分類優先於評分）
        if category == '程式錯誤':
            sentiment = '負面'
            priority = '高'
        elif category == '正面評價':
            sentiment = '正面'
            priority = '低'
        elif category in ['功能建議', 'UX體驗']:
            sentiment = '中性'
            priority = '中'
        elif r['rating'] <= 2:
            sentiment = '負面'
            priority = '高'
        elif r['rating'] >= 4:
            sentiment = '正面'
            priority = '低'
            
        r.update({
            "category": category,
            "sentiment": sentiment,
            "priority": priority
        })
        classified_reviews.append(r)
        
    return classified_reviews

if __name__ == "__main__":
    test_reviews = [
        {"review_text": "這款 App 閃退嚴重，根本不能用！", "rating": 1},
        {"review_text": "介面很漂亮，但功能可以再多一點。", "rating": 4}
    ]
    print(classify_reviews(test_reviews))
