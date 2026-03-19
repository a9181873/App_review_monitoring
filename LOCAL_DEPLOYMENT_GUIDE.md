# App 評論監測工具：地端自動化部署手冊 (Python + Power Automate Desktop)

本手冊指導您如何在 **Windows 電腦** 上部署 App 評論監測工具，並結合 **Power Automate Desktop (PAD)** 實現每日自動化執行與通知。

---

## 1. 環境準備

### 1.1 安裝 Python
1. 前往 [Python 官網](https://www.python.org/) 下載並安裝（建議 3.10+）。
2. **重要**：安裝時請務必勾選 **"Add Python to PATH"**。

### 1.2 安裝必要套件
```bash
pip install -r requirements.txt
```

### 1.3 設定環境變數
複製 `.env.example` 為 `.env`，填入必要設定：

| 變數名稱 | 說明 | 範例 |
|:---|:---|:---|
| `EMAIL_SENDER` | 寄件人 Gmail 地址 | `yourname@gmail.com` |
| `EMAIL_PASSWORD` | Gmail App 密碼（非一般密碼）| `abcd efgh ijkl mnop` |
| `EMAIL_RECIPIENTS` | 收件人，逗號分隔 | `a@gmail.com,b@gmail.com` |
| `TEAMS_WEBHOOK_URL` | Teams Incoming Webhook URL | `https://...webhook.office.com/...` |
| `GEMINI_API_KEY` | Gemini API Key（從 [AI Studio](https://aistudio.google.com/apikey) 取得）| `AIzaSy...` |

---

## 2. 程式碼結構

| 檔案 | 說明 |
|:---|:---|
| `config.py` | **設定檔**：集中管理路徑、App 清單、AI/通知設定 |
| `main.py` | **主程式**：整合所有流程（抓取 → AI 分析 → Excel → 報告 → 通知）|
| `scraper.py` | **抓取模組**：iOS RSS + 網頁爬蟲偵測回覆、Google Play 增量抓取 |
| `ai_analyzer.py` | **AI 模組**：Gemini 2.5 Flash 語意分析（含關鍵字 fallback）|
| `classify_reviews.py` | **分類模組**：整合 AI 分析與關鍵字分類 |
| `append_to_excel.py` | **資料庫模組**：寫入 Excel 並自動去重 |
| `summarizer.py` | **報告模組**：產出每日 Markdown 摘要 |
| `notifier.py` | **通知模組**：Email + Teams（含指數退避重試）|

執行後自動產生的子目錄：

| 目錄 | 說明 |
|:---|:---|
| `data/` | 已見評論 ID（用於去重） |
| `reports/` | Excel 資料庫、每日報告、最新結果 JSON |

---

## 3. 執行方式

```bash
# 日常增量模式（抓新評論 + AI 分析 + 通知）
python main.py

# 回溯模式（抓近一年歷史 + AI 分析 + 存入 Excel，不發通知）
python main.py --backfill
```

---

## 4. Power Automate Desktop (PAD) 整合

### 設計考量

`main.py` 已針對 PAD 做以下優化：

1. **結束碼**：`0` = 成功、`1` = 部分失敗、`2` = 嚴重錯誤
2. **結構化輸出**：
   - `reports/latest_result.json`：每次執行後產出，包含評論數、報告路徑、通知結果
   - stdout 最後一行以 `__PAD_RESULT__:` 為前綴的 JSON，可從 `%CommandOutput%` 解析
3. **純文字報告**：`reports/report_YYYY-MM-DD.md` 可直接作為郵件內容

### 步驟 1：建立新的流程
1. 開啟 Power Automate Desktop → 「新增流程」→ 命名為「App 評論每日監測」。

### 步驟 2：執行 Python 腳本
拖入 **「執行 DOS 指令」** 動作：
```cmd
cd /d C:\您的路徑\App 評論監測工具 && python main.py
```
> 輸出存入 `%CommandOutput%`。

### 步驟 3：判斷執行結果（選用）
拖入 **「讀取 JSON 檔案」** 動作：
- 檔案路徑：`C:\您的路徑\reports\latest_result.json`
- 可取得 `review_count`、`report_path`、`success` 等欄位

### 步驟 4：設定排程
1. 在 PAD 控制面板中 → 流程旁 「...」 → 「詳細資料」
2. 設定「週期性」觸發器（建議：每天早上 11:00）

---

## 5. 常見問題 (FAQ)

**Q: 執行時出現中文亂碼？**
A: 程式已內建 UTF-8 自動修復。若仍有問題，可設定環境變數 `PYTHONUTF8=1`。

**Q: AI 分析顯示 fallback？**
A: 確認 `.env` 中的 `GEMINI_API_KEY` 已填入，且為從 [Google AI Studio](https://aistudio.google.com/apikey) 取得的 Key（非 GCP Console）。

**Q: 如何修改監測的 App？**
A: 修改 `config.py` 中的 `APPS` 清單。

**Q: Email 發不出去怎麼辦？**
A: 確認已設定 Gmail App 密碼（非一般密碼），並在 `.env` 中填入 `EMAIL_SENDER` 和 `EMAIL_PASSWORD`。

**Q: 如何啟用 Teams 通知？**
A: 在 Teams 頻道建立 Incoming Webhook，取得 URL 後填入 `.env` 的 `TEAMS_WEBHOOK_URL`。
