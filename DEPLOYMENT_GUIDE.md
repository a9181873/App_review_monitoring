# App 評論監測工具部署手冊 (Python + Power Automate)

本手冊旨在指導您如何部署 App 評論監測工具，並結合 **Microsoft Power Automate** 實現自動化排程與通知。

---

## 1. 環境準備

### 1.1 Python 環境安裝
請確保您的電腦已安裝 Python 3.10 或以上版本。
1. 前往 [Python 官網](https://www.python.org/) 下載並安裝。
2. 開啟終端機 (Terminal) 或命令提示字元 (CMD)，執行以下指令安裝必要套件：
   ```bash
   pip install google-play-scraper app-store-scraper pandas openpyxl openai
   ```

### 1.2 設定環境變數
本工具使用 Gemini AI (透過 OpenAI 相容介面) 進行分類。
- **Windows**: 
  1. 搜尋「編輯系統環境變數」。
  2. 點擊「環境變數」，在「系統變數」中新增 `OPENAI_API_KEY`，值為您的 API Key。
- **Mac/Linux**:
  在 `~/.bashrc` 或 `~/.zshrc` 中加入：
  ```bash
  export OPENAI_API_KEY='您的_API_KEY'
  ```

---

## 2. 程式碼結構說明

您的工具目錄 `/home/ubuntu/app_review_tool/` 包含以下核心檔案：

| 檔案名稱 | 功能描述 |
| :--- | :--- |
| `main.py` | **主程式**：整合所有流程，是自動化執行的入口。 |
| `scraper.py` | **抓取模組**：負責從 iOS App Store 與 Google Play 抓取評論。 |
| `classify_reviews.py` | **AI 模組**：呼叫 Gemini AI 對評論進行分類、情緒分析與優先度標記。 |
| `append_to_excel.py` | **資料庫模組**：將新評論寫入 Excel 檔案，並自動去重。 |
| `summarizer.py` | **報告模組**：產出每日 Markdown 摘要報告。 |
| `notifier.py` | **通知模組**：發送 Email 通知。 |

---

## 3. 結合 Power Automate 自動化

若要實現「每日自動執行」，建議使用 **Power Automate Desktop (PAD)**。

### 步驟 1：建立新的流程
1. 開啟 Power Automate Desktop，點擊「新增流程」，命名為「App 評論每日監測」。

### 步驟 2：設定排程 (或手動觸發)
在流程中加入以下動作：
1. **執行 Python 指令碼** (或 **執行 DOS 指令**)：
   - 指令：
     ```bash
     cd C:\您的路徑\app_review_tool && python main.py
     ```
   - *注意：請將路徑替換為您實際存放程式碼的位置。*

### 步驟 3：讀取報告並發送通知 (選用)
如果您希望由 Power Automate 發送 Outlook 郵件而非程式碼發送：
1. 使用「讀取文字檔案」動作，讀取 `reports/report_YYYY-MM-DD.md`。
2. 使用「發送電子郵件訊息 (V2)」動作，將讀取的內容作為郵件本文。

### 步驟 4：設定排程執行
1. 在 Power Automate 控制面板中，為此流程設定「週期性」觸發器（例如：每天早上 11:00）。

---

## 4. 常見問題 (FAQ)

**Q: 為什麼 iOS 抓不到評論？**
A: Apple RSS Feed 有時會因為地區限制或頻率限制導致回傳空值。程式已加入重試機制，若持續失敗，請檢查網路環境是否能正常存取 App Store 網頁。

**Q: 如何修改監測的 App？**
A: 請修改 `scraper.py` 中的 `apps` 列表，更換對應的 `ios_id` 與 `android_id`。

---

## 5. 檔案下載與備份
建議定期備份 `reports/App評論監測_資料庫.xlsx`，這是您長期的評論資產。
