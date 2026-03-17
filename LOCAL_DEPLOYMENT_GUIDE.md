# App 評論監測工具：地端自動化部署手冊 (Python + Power Automate Desktop)

本手冊指導您如何在 **Windows 電腦** 上部署 App 評論監測工具，並結合 **Power Automate Desktop (PAD)** 實現每日自動化執行與通知。

---

## 1. 環境準備

### 1.1 安裝 Python
1. 前往 [Python 官網](https://www.python.org/) 下載並安裝（建議 3.10+）。
2. **重要**：安裝時請務必勾選 **"Add Python to PATH"**。

### 1.2 安裝必要套件
```bash
pip install google-play-scraper app-store-scraper pandas openpyxl requests
```

### 1.3 設定環境變數（選用）
以下環境變數用於啟用通知功能，可在「系統環境變數」中設定：

| 變數名稱 | 說明 | 範例 |
|:---|:---|:---|
| `EMAIL_SENDER` | 寄件人 Gmail 地址 | `yourname@gmail.com` |
| `EMAIL_PASSWORD` | Gmail App 密碼（非一般密碼）| `abcd efgh ijkl mnop` |
| `EMAIL_RECIPIENTS` | 收件人，逗號分隔 | `a@gmail.com,b@gmail.com` |
| `TEAMS_ENABLED` | 是否啟用 Teams 通知 | `true` |
| `TEAMS_WEBHOOK_URL` | Teams Incoming Webhook URL | `https://...webhook.office.com/...` |

---

## 2. 程式碼結構

將所有檔案放在同一資料夾中（例如：`C:\AppReviewTool`）。

| 檔案 | 說明 |
|:---|:---|
| `config.py` | **設定檔**：集中管理路徑、App 清單、通知設定 |
| `main.py` | **主程式**：整合所有流程，是 PAD 執行的入口 |
| `scraper.py` | **抓取模組**：iOS App Store + Google Play 增量抓取 |
| `classify_reviews.py` | **分類模組**：關鍵字比對分類、情緒與優先度標記 |
| `append_to_excel.py` | **資料庫模組**：寫入 Excel 並自動去重 |
| `summarizer.py` | **報告模組**：產出每日 Markdown 摘要 |
| `notifier.py` | **通知模組**：支援 Email (SMTP) + Teams (Webhook) |

執行後自動產生的子目錄：

| 目錄 | 說明 |
|:---|:---|
| `data/` | 已見評論 ID（用於去重） |
| `reports/` | Excel 資料庫、每日報告、最新結果 JSON |

---

## 3. Power Automate Desktop (PAD) 整合

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
cd /d C:\AppReviewTool && python main.py
```
> 將 `C:\AppReviewTool` 替換為實際路徑。
> 輸出存入 `%CommandOutput%`。

### 步驟 3：判斷執行結果（選用）
拖入 **「讀取 JSON 檔案」** 或 **「讀取文字檔」** 動作：
- 檔案路徑：`C:\AppReviewTool\reports\latest_result.json`
- 可取得 `review_count`、`report_path`、`success` 等欄位

### 步驟 4：用 PAD 發送通知（選用，若不使用程式內建通知）
1. **Outlook**：拖入「發送電子郵件訊息 (V2)」，讀取 `report_YYYY-MM-DD.md` 作為郵件內容
2. **Teams**：拖入「張貼訊息到 Teams」，將報告內容貼入指定頻道

### 步驟 5：設定排程
1. 在 PAD 控制面板中 → 流程旁 「...」 → 「詳細資料」
2. 設定「週期性」觸發器（建議：每天早上 9:00）

---

## 4. 關鍵字分類說明

目前的分類邏輯使用 **關鍵字比對**（不需 API），可在 `classify_reviews.py` 中修改 `keyword_map`：

| 分類 | 關鍵字範例 |
|:---|:---|
| 程式錯誤 | 閃退、當機、Bug、不能用、無法登入 |
| 功能建議 | 希望、建議、優化、增加、改善 |
| UX體驗 | 難用、複雜、找不到、介面、字太小 |
| 正面評價 | 好用、讚、方便、五星、感謝 |

---

## 5. 常見問題 (FAQ)

**Q: 執行時出現 "python 不是內部或外部命令"？**
A: 重新安裝 Python 並勾選 "Add Python to PATH"，或在 DOS 指令中使用完整路徑。

**Q: 如何修改監測的 App？**
A: 修改 `config.py` 中的 `APPS` 清單。

**Q: Email 發不出去怎麼辦？**
A: 確認已設定 Gmail App 密碼（非一般密碼），並設定 `EMAIL_SENDER` 和 `EMAIL_PASSWORD` 環境變數。

**Q: 如何啟用 Teams 通知？**
A: 在 Teams 頻道中建立 Incoming Webhook，取得 URL 後設定 `TEAMS_WEBHOOK_URL` 和 `TEAMS_ENABLED=true` 環境變數。
