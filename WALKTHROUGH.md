# Walkthrough: 系統優化紀錄

## 最新變更摘要（v2 — AI 語意分析 + iOS 回覆偵測）

| 檔案 | 變更類型 | 說明 |
|:---|:---:|:---|
| [ai_analyzer.py](ai_analyzer.py) | 🆕 新增 | Gemini 2.5 Flash AI 語意分析模組（含關鍵字 fallback）|
| [scraper.py](scraper.py) | 🔄 重寫 | 新增 iOS 網頁爬蟲偵測開發者回覆（BeautifulSoup）|
| [notifier.py](notifier.py) | ✏️ 更新 | 加入指數退避重試機制（3 次：2s → 4s → 8s）|
| [config.py](config.py) | ✏️ 更新 | 新增 AI 設定、通知重試設定、GCP 路徑自動切換 |
| [main.py](main.py) | ✏️ 更新 | 整合 AI 分析流程、GCP Cloud Functions handler、UTF-8 修復 |
| [.env.example](.env.example) | ✏️ 更新 | 新增 GEMINI_API_KEY |
| [requirements.txt](requirements.txt) | ✏️ 更新 | 新增 google-generativeai、beautifulsoup4、functions-framework |
| [deploy_gcp.sh](deploy_gcp.sh) | 🆕 新增 | GCP Cloud Functions 一鍵部署腳本 |

---

## 關鍵設計決策

### 1. AI 語意分析架構
```
classify_reviews.py（對外介面）
└── ai_analyzer.py
    ├── Gemini 2.5 Flash API（主要）→ 批次分析，回傳 JSON
    └── 關鍵字 Fallback（備援）→ 無 API 或配額耗盡時自動切換
```

### 2. iOS 開發者回覆偵測
```
scraper.py
├── iTunes RSS Feed → 抓取評論內容（穩定）
└── App Store 網頁爬蟲 → 偵測回覆狀態（BeautifulSoup）
    ├── 成功 → 比對使用者名稱+評論前20字
    └── 失敗 → graceful degradation，標記為未知
```

### 3. 通知重試機制
```
NotificationChannel.send()
└── _retry_on_failure 裝飾器
    ├── 第 1 次失敗 → 等 2 秒
    ├── 第 2 次失敗 → 等 4 秒
    └── 第 3 次失敗 → 放棄，回傳 False
```

### 4. 部署架構
- **Windows 本機**：PAD 排程 → `python main.py` → Exit Code + JSON
- **GCP 雲端**：Cloud Scheduler → Cloud Functions HTTP → `cloud_function_handler()`

---

## 驗證結果

| 測試項目 | 結果 |
|:---|:---:|
| Gemini AI 分析（3 則測試評論） | ✅ 分類/情緒/優先度皆正確 |
| 關鍵字 Fallback（API 不可用時） | ✅ 自動切換 |
| iOS 網頁爬蟲回覆偵測 | ✅ 正常運作（Apple 阻擋時 graceful degradation） |
| 通知重試機制 | ✅ 指數退避正常 |
| Email 通知 | ✅ 發送成功 |
| Teams 通知（Adaptive Card） | ✅ 發送成功 |
| Excel 資料庫更新 | ✅ 含 AI 分析欄位 |
| Windows UTF-8 亂碼修復 | ✅ 中文正常顯示 |
| 完整端到端流程 | ✅ 18.7 秒完成 |
