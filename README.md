# App 評論監測工具 (App Review Monitoring Tool)

這是一個輕量、跨平台且可全自動化運行的 App 評論監控與通知系統。
本工具可定時抓取指定 App 於 **Google Play** 與 **App Store** 的最新使用者評論，透過獨創的**關鍵字優先分類邏輯**找出高風險問題，並自動生成摘要報表傳送至 **Microsoft Teams** 與 **Email**。

主要專為解決「不知名套件被阻擋」、「單純依靠星級難以找出關鍵問題（如：給五星但內文說閃退）」等痛點而生。

---

## 🌟 核心特色 (Features)

*   **雙平台支援**：同時監控 iOS (App Store) 與 Android (Google Play) 評論。
*   **穩定的 iOS 爬蟲**：採用 Apple 官方 iTunes RSS Feed 解析，100% 免疫反爬蟲機制。
*   **智慧優先級分類**：不依賴昂貴且緩慢的 LLM API。內建自訂關鍵字對應字典 (`classify_reviews.py`)，**關鍵字權重高於星級**。
*   **增量抓取防呆機制**：透過 `data/` 目錄保存 `seen_ids.json`，確保每次執行只處理「全新的客訴」，過濾雜訊。
*   **本地永久資料庫**：每次抓取後會自動彙整、去重複，並寫入本機 `reports/` 目錄下的 Excel 檔案 (`App評論監測_資料庫.xlsx`)。
*   **多通道推播**：支援 Email (SMTP) 報表寄送與 Microsoft Teams (Adaptive Card) 頻道即時推播。
*   **雲端零成本部署**：本架構經過優化，可完美運行於 Google Cloud Platform (GCP) 的 `e2-micro` 永久免費虛擬機上。

---

## 🛠️ 技術堆疊 (Tech Stack)

*   **語言**: Python 3.10+
*   **Android 爬取**: `google-play-scraper`
*   **iOS 爬取**: Native `requests` (iTunes RSS API)
*   **資料處理**: `pandas`, `openpyxl`
*   **任務排程**: Linux Crontab (若部署於雲端/伺服器) / Windows 工作排程器

---

## 🚀 快速開始 (Quick Start)

### 1. 環境安裝
請確保電腦中已安裝 Python 3，接著在終端機執行：
```bash
pip install -r requirements.txt
# 或手動安裝： pip install requests pandas google-play-scraper openpyxl
```

### 2. 環境變數與設定檔 (`config.py`)
所有的核心設定皆集中在 `config.py`，您可以直接修改該檔案，或透過設定系統的環境變數來覆蓋：

*   **目標 App 設定**：在 `APPS` 陣列中填寫您要監測的應用程式與對應的 Store IDs。
*   **Email 發送設定**：
    *   `EMAIL_ENABLED = True`
    *   `EMAIL_SENDER`: 您的發信信箱 (如：Gmail)
    *   `EMAIL_PASSWORD`: 您的應用程式專用密碼 (請勿使用登入密碼)
    *   `EMAIL_RECIPIENTS`: 接收報表的信箱清單
*   **Teams 通知設定**：
    *   `TEAMS_ENABLED = True`
    *   `TEAMS_WEBHOOK_URL`: 您在 Teams 頻道取得的 Incoming Webhook 網址。

### 3. 本機執行測試
直接執行主程式，系統會印出詳細的抓取日誌，並產生 Markdown 報告：
```bash
python main.py
```
> **💡 提示**：若想重置抓取紀錄（讓程式將所有歷史評論都視為新評論發送一次），請刪除 `data/` 目錄下的所有 JSON 檔案。

---

## ☁️ GCP 免費虛擬機部署指南

若您希望系統每天自動執行而不需要開著您的個人電腦，可以將本專案部署至 GCP。
詳細的圖文步驟與 Teams Webhook 申請方式，請參考本專案生成的：
👉  **`GCP_TEAMS_GUIDE.md`** 以及 **`ARCHITECTURE_PPT.md`**

簡單摘要：
1. 於 GCP 開啟一台 `e2-micro` (us-central1)。
2. 透過 gcloud 或 SSH 將本專案上傳。
3. 執行 `crontab -e` 設定每日定時排程：
   `0 11 * * * cd ~/app-monitor && /usr/bin/python3 main.py >> cron.log 2>&1`

---

## 📂 專案目錄結構
```text
App_review_monitoring/
├── main.py              # 主程式切入點
├── scraper.py           # 負責 iOS/Android 的抓取與 ID 去重
├── classify_reviews.py  # 關鍵字比對與優先級演算邏輯
├── summarizer.py        # 產出 Markdown 格式日報
├── append_to_excel.py   # 新增資料至 Excel 資料庫
├── notifier.py          # Email 與 Teams 派發模組
├── config.py            # 全域變數與環境參數
├── requirements.txt     # Python 依賴清單
├── data/                # [自動生成] 存放已讀 review_id 的 JSON 緩存
└── reports/             # [自動生成] 存放 Excel 資料庫與 Markdown 報表
```
