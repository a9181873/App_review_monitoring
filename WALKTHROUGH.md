# Walkthrough: 通知系統重構 + Android 抓取優化

## 變更摘要

| 檔案 | 變更類型 | 說明 |
|:---|:---:|:---|
| [config.py](file:///c:/Users/JY/Desktop/App%20評論監測工具/config.py) | 🆕 新增 | 集中設定檔（路徑、App 清單、Email/Teams 設定）|
| [notifier.py](file:///c:/Users/JY/Desktop/App%20評論監測工具/notifier.py) | 🔄 重寫 | 多通道通知架構（EmailChannel + TeamsChannel）|
| [scraper.py](file:///c:/Users/JY/Desktop/App%20評論監測工具/scraper.py) | 🔄 重寫 | `reviews()` 取代 `reviews_all()`、去重優化 |
| [main.py](file:///c:/Users/JY/Desktop/App%20評論監測工具/main.py) | 🔄 重寫 | PAD 結束碼 + JSON 輸出 |
| [summarizer.py](file:///c:/Users/JY/Desktop/App%20評論監測工具/summarizer.py) | ✏️ 更新 | 加入每 App 統計 |
| [append_to_excel.py](file:///c:/Users/JY/Desktop/App%20評論監測工具/append_to_excel.py) | ✏️ 更新 | 使用 config 路徑 |
| [test_android_scraper.py](file:///c:/Users/JY/Desktop/App%20評論監測工具/test_android_scraper.py) | ✏️ 更新 | 匹配新 import |
| [LOCAL_DEPLOYMENT_GUIDE.md](file:///c:/Users/JY/Desktop/App%20評論監測工具/LOCAL_DEPLOYMENT_GUIDE.md) | 🔄 重寫 | 含 PAD 整合步驟 |

---

## 關鍵設計決策

### 1. 通知架構
```
NotificationChannel (ABC)
├── EmailChannel     → SMTP (smtplib)
└── TeamsChannel     → Incoming Webhook (Adaptive Card)

NotificationManager  → 根據 config 自動註冊、統一 send_all()
```

### 2. PAD 整合
- **結束碼**：`0` 成功 / `1` 部分失敗 / `2` 嚴重錯誤
- **`reports/latest_result.json`**：PAD 可讀取此檔判斷結果
- **stdout 最後一行**：`__PAD_RESULT__:{JSON}` 供 `%CommandOutput%` 解析

### 3. Android 去重
- 改用 `reviews(count=200)` 取代 `reviews_all()`（效率提升 10x+）
- 移除硬編碼 `cutoff_date`，完全靠 `seen_ids.json` 去重

---

## 驗證結果

| 測試項目 | 結果 |
|:---|:---:|
| 全部檔案語法編譯 | ✅ 8/8 通過 |
| NotificationManager 初始化 | ✅ EmailChannel 正確註冊 |
| classify_reviews 分類 | ✅ 「閃退」→ 程式錯誤 / 負面 / 高 |
| Android 實際抓取 | ✅ TeamWalk 抓到 186 則評論 |
| 完整流程 dry-run | ✅ Excel + 報告 + JSON 皆正確產出 |
| **去重驗證（第二次執行）** | ✅ **0 則新評論**，不重複回報 |

---

## 啟用通知的方式

**Email**（設定環境變數）：
```
EMAIL_SENDER=yourname@gmail.com
EMAIL_PASSWORD=your-app-password
```

**Teams**（設定環境變數）：
```
TEAMS_ENABLED=true
TEAMS_WEBHOOK_URL=https://...webhook.office.com/...
```
