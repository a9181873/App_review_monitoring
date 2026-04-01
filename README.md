# App 評論監測工具 (App Review Monitoring Tool)

這是一個輕量、跨平台且可全自動化運行的 App 評論監控與通知系統。
本工具可定時抓取指定 App 於 **Google Play** 與 **App Store** 的最新使用者評論，透過 **Gemini AI 語意分析** 智慧分類評論優先度，並自動生成摘要報表傳送至 **Microsoft Teams** 與 **Email**。

主要專為解決「不知名套件被阻擋」、「單純依靠星級難以找出關鍵問題（如：給五星但內文說閃退）」等痛點而生。

---

## 核心特色 (Features)

*   **雙平台支援**：同時監控 iOS (App Store) 與 Android (Google Play) 評論。
*   **穩定的 iOS 爬蟲**：採用 `app-store-web-scraper` 套件抓取 App Store 評論。
*   **AI 語意分析**：整合 Google Gemini 2.5 Flash（免費方案），自動分類評論為「程式錯誤 / 功能建議 / UX體驗 / 帳號問題 / 效能問題」等類別，並標記情緒與優先度。API 不可用時自動 fallback 至關鍵字分類。
*   **智慧通知**：僅通知今天/昨天的新評論，舊評論靜默存入資料庫，不灌爆通知。
*   **增量抓取防呆機制**：透過 `data/` 目錄保存 `seen_ids.json`，確保每次執行只處理「全新的客訴」，過濾雜訊。
*   **雲端 / 本機雙模式儲存（storage.py）**：自動偵測執行環境，GCP 上使用 GCS Bucket 持久化資料（seen_ids + Excel），本機 / PAD 上則直接讀寫本地檔案。**未來從 GCP 搬到 PAD 不需改任何程式碼**。
*   **Cold Start 增量保護**：當 GCP 環境偵測到 `seen_ids.json` 不存在（首次 / 冷啟動）時，自動限制只抓取近 2 天評論，避免超過 Cloud Functions 9 分鐘上限。
*   **本地永久資料庫**：每次抓取後會自動彙整、去重複，並寫入 Excel 檔案 (`App評論監測_資料庫.xlsx`)，GCP 環境同步至 GCS Bucket。
*   **Email 附件功能**：每日通知 Email 會自動附帶最新的 Excel 資料庫檔案，方便離線查閱與備份。
*   **週報/月報彙整**：從 Excel 資料庫產出統計報告，含平均星等趨勢、情緒分布、各 App 星等分布、低分評論摘要。
*   **關鍵議題追蹤**：自動歸納近期高頻問題（如閃退、登入異常），優先用 Gemini AI 分析，fallback 到關鍵字比對，標示嚴重度。
*   **多通道推播（含重試）**：支援 Email (SMTP) 報表寄送（含附件）與 Microsoft Teams (Adaptive Card) 頻道即時推播，內建指數退避重試機制（預設 3 次）。
*   **回溯模式**：`python main.py --backfill` 可一次抓取近一年歷史評論 + AI 分析 + 存入 Excel（不發通知）。
*   **多平台部署**：支援 Windows 本機（PAD 排程）、GCP Cloud Functions + Cloud Scheduler 雲端部署。

---

## 技術堆疊 (Tech Stack)

*   **語言**: Python 3.10+
*   **Android 爬取**: `google-play-scraper`
*   **iOS 爬取**: `app-store-web-scraper`
*   **AI 分析**: `google-generativeai` (Gemini 2.5 Flash 免費方案)
*   **資料處理**: `pandas`, `openpyxl`
*   **雲端儲存**: `google-cloud-storage` (GCS 持久化)
*   **環境管理**: `python-dotenv`
*   **部署**: GCP Cloud Functions (Gen2) + Cloud Scheduler / Windows PAD

---

## 快速開始 (Quick Start)

### 1. 環境安裝
請確保電腦中已安裝 Python 3.10+，接著在終端機執行：
```bash
pip install -r requirements.txt
```

### 2. 環境變數設定
複製 `.env.example` 為 `.env`，填入必要設定：
```bash
cp .env.example .env
```

| 變數名稱 | 說明 |
|:---|:---|
| `EMAIL_SENDER` | 寄件人 Gmail 地址 |
| `EMAIL_PASSWORD` | Gmail App 密碼（非一般密碼）|
| `EMAIL_RECIPIENTS` | 收件人，逗號分隔 |
| `TEAMS_WEBHOOK_URL` | Teams Incoming Webhook URL |
| `GEMINI_API_KEY` | 從 [Google AI Studio](https://aistudio.google.com/apikey) 取得（免費） |

### 3. 本機執行
```bash
# 日常增量模式（抓新評論 + AI 分析 + 通知）
python main.py

# 回溯模式（抓近一年歷史 + AI 分析 + 存入 Excel，不發通知）
python main.py --backfill

# 週報（近 7 天統計 + 趨勢分析）
python main.py --weekly

# 月報（近 30 天統計 + 趨勢分析）
python main.py --monthly

# 關鍵議題追蹤報告
python main.py --issues
```

> **提示**：若想重置抓取紀錄，刪除 `data/` 目錄下的所有 JSON 檔案即可。

---

## 部署方式

### 方式 A：Windows 本機 + Power Automate Desktop
詳見 [`LOCAL_DEPLOYMENT_GUIDE.md`](LOCAL_DEPLOYMENT_GUIDE.md)。

### 方式 B：GCP Cloud Functions + Cloud Scheduler
詳見 [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md)。
- 使用 `deploy_gcp.sh` 一鍵部署
- Cloud Scheduler 每日定時觸發 HTTP endpoint
- 完全免費（在 GCP 免費額度內）

---

## 專案目錄結構
```text
App 評論監測工具/
├── main.py              # 主程式入口（含 GCP Cloud Functions handler）
├── scraper.py           # iOS/Android 評論抓取與去重
├── ai_analyzer.py       # Gemini AI 語意分析（含關鍵字 fallback）
├── classify_reviews.py  # 分類整合（AI 優先，fallback 關鍵字）
├── storage.py           # 儲存抽象層（GCS / 本機自動切換）
├── append_to_excel.py   # Excel 資料庫寫入
├── summarizer.py        # Markdown 摘要報告產生
├── periodic_report.py   # 週報/月報彙整（從 Excel 資料庫統計）
├── issue_tracker.py     # 關鍵議題追蹤（AI + 關鍵字 fallback）
├── notifier.py          # Email + Teams 通知（含附件 + 指數退避重試）
├── config.py            # 集中設定檔（環境變數讀取）
├── .env.example         # 環境變數範本
├── requirements.txt     # Python 依賴清單
├── deploy_gcp.sh        # GCP 一鍵部署腳本（含 GCS Bucket 自動建立）
├── data/                # [自動生成] 已讀 review_id 的 JSON 緩存
└── reports/             # [自動生成] Excel 資料庫、Markdown 報表、JSON 結果
```
