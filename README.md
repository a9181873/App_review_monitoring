# App 評論監測工具 (App Review Monitoring Tool)

輕量、跨平台的自動化 App 評論監控系統。每日定時抓取指定 App 於 **Google Play** 與 **App Store** 的最新評論，支援 **AI 語意分析**（OpenRouter 免費模型）分類優先度，並自動產出摘要報告。

解決「只看星等無法發現關鍵問題（五星但內文說閃退）」、「評論已被編輯卻漏通知」等痛點。

---

## 核心特色

- **雙平台**：iOS (App Store) + Android (Google Play) 同步監控
- **編輯偵測**：以「內容 + 星等」SHA1 指紋比對，同一評論 ID 內容變更立即標記為編輯更新
- **AI 語意分析**：OpenRouter 免費模型（Qwen 3 80B）主力，Gemini 備援，API 全不可用時關鍵字 fallback
- **增量去重**：`data/` 目錄存 `seen_ids.json`，只通知「全新」與「已編輯」評論
- **Docker 一鍵部署**：`docker compose up` 即上線，環境零污染
- **輕量模式**：`run_daily.py` 純抓取 + 輸出文字摘要，適合 cron 排程
- **全功能模式**：`main.py` 含 Excel 資料庫、週報/月報、Email/Teams 通知、回溯模式
- **無 IP 封鎖風險**：Oracle Cloud / 自建 VPS IP 不在 Apple 黑名單，iOS RSS 直連

---

## 快速開始（Docker，推薦）

```bash
git clone https://github.com/a9181873/App_review_monitoring.git
cd App_review_monitoring
cp .env.example .env      # 編輯填入 OPENROUTER_API_KEY
bash run.sh               # build + 執行一次
```

每日排程（主機 crontab）：
```
0 8 * * * cd /path/to/App_review_monitoring && docker compose run --rm app-review
```

---

## 快速開始（本機 Python）

```bash
pip install -r requirements.txt
cp .env.example .env
python run_daily.py            # 輕量模式
python main.py --backfill      # 回溯模式（抓一年歷史）
python main.py --weekly        # 週報
```

---

## 環境變數

| 變數 | 必要 | 說明 |
|:---|:---|:---|
| `OPENROUTER_API_KEY` | 選填 | OpenRouter API Key，AI 語意分析主力（免費方案） |
| `GEMINI_API_KEY` | 選填 | Gemini API Key，備援 AI（免費方案） |
| `ASC_KEY_ID` | 選填 | App Store Connect Key ID，iOS 即時評論（[設定指南](ASC_SETUP_GUIDE.md)） |
| `ASC_ISSUER_ID` | 選填 | App Store Connect Issuer ID |
| `ASC_PRIVATE_KEY` | 選填 | .p8 私鑰內容（雲端用） |
| `ASC_PRIVATE_KEY_PATH` | 選填 | .p8 私鑰檔案路徑（本機用） |
| `EMAIL_SENDER` / `EMAIL_PASSWORD` | 選填 | Gmail SMTP 通知 |
| `TEAMS_WEBHOOK_URL` | 選填 | Teams 頻道通知 |

無 AI API Key 時自動使用關鍵字分類。

---

## 監控 App 清單

編輯 `config.py` 的 `APPS` 陣列即可增減：

```python
APPS = [
    {"name": "台灣人壽", "ios_id": "1035225274", "android_id": "com.taiwanlife.app"},
    {"name": "TeamWalk",   "ios_id": "1559679863", "android_id": "com.taiwanlife.teamwalk"},
]
```

---

## 架構

```
App_review_monitoring/
├── main.py              # 全功能主程式（含 GCP Cloud Functions handler）
├── run_daily.py          # 輕量模式（純抓取 + 摘要，適合 cron）
├── scraper.py            # iOS/Android 抓取 + SHA1 指紋編輯偵測
├── ai_analyzer.py        # AI 分析（OpenRouter → Gemini → 關鍵字）
├── classify_reviews.py   # 分類整合層
├── summarizer.py         # Markdown 摘要報告
├── append_to_excel.py    # Excel 資料庫寫入
├── periodic_report.py    # 週報/月報統計
├── issue_tracker.py      # 關鍵議題追蹤
├── notifier.py           # Email + Teams 通知（指數退避重試）
├── storage.py            # 本機 / GCS 雙模式儲存
├── ios_asc.py            # App Store Connect API（JWT 認證）
├── config.py             # 集中設定
├── Dockerfile            # Python 3.12-slim
├── docker-compose.yml    # volume 掛載 data/ + reports/
├── run.sh                # 一鍵 build + run
├── .env.example          # 環境變數範本（API Key 留空）
├── data/                 # [自動生成] seen_ids.json
└── reports/              # [自動生成] Excel、Markdown、JSON
```

---

## 部署方案比較

| 方案 | IP 封鎖風險 | iOS 延遲 | 適用場景 |
|:---|:---|:---|:---|
| **Docker + cron（Oracle / VPS）** | 無 | 24–72h (RSS) | ✅ 推薦 |
| GCP Cloud Functions + Scheduler | Apple 封 GCP IP | 需 n8n 中繼 | 有 GCP 依賴 |
| Windows + PAD | 無 | 24–72h (RSS) | 公司 PC |

---

## 技術堆疊

- **Python** 3.10+
- **Android**：`google-play-scraper`
- **iOS**：iTunes RSS + App Store Connect API（JWT 認證）
- **AI**：OpenRouter API（Qwen 3 80B 免費方案）→ Gemini 備援 → 關鍵字 fallback
- **資料**：pandas + openpyxl（Excel 資料庫）
- **雲端**：google-cloud-storage（GCS 持久化，選用）
- **部署**：Docker + docker-compose
