# App Store Connect API 設定指南

設定 ASC API 後，iOS 評論從 iTunes RSS 的 **24–72 小時延遲** 升級為 **即時資料**，且能自動過濾「開發者已回復」的評論。

---

## 費用

| 項目 | 費用 |
|:---|:---|
| Apple Developer Program 年費 | **USD $99／年**（約 NT$3,200） |
| ASC API 調用 | **免費**（含在會員年費內，無額外費用） |

> 必須加入 Apple Developer Program 才能使用 ASC API。個人或組織帳號皆可，年費相同。

---

## 申請流程（約 10 分鐘）

### 前置條件
- 已付費加入 [Apple Developer Program](https://developer.apple.com/programs/)
- 在 App Store Connect 具有 **Admin** 或 **App Manager** 角色
- 登入 [App Store Connect](https://appstoreconnect.apple.com/)

### 步驟 1：進入 Keys 頁面
**Users and Access** → 左側 **Integrations** 標籤 → **App Store Connect API** 區塊

### 步驟 2：建立 API Key
1. 點擊 **「+」**（Generate API Key）
2. **Name**：自訂名稱（如 `app-review-monitor`）
3. **Access**：選擇 **「App Manager」**（最低權限即可讀取評論）
4. 點擊 **Generate**

### 步驟 3：下載私鑰（.p8）
- 產生後會自動下載一個 `.p8` 檔案（**僅此一次下載機會**）
- 檔案命名規則：`AuthKey_XXXXXXXXXX.p8`
- **立即備份**，Apple 不保留副本

### 步驟 4：記錄憑證
頁面會顯示三項資訊，全部需要：

| 欄位 | 位置 | 對應環境變數 |
|:---|:---|:---|
| **Issuer ID** | Keys 頁面上方（UUID 格式） | `ASC_ISSUER_ID` |
| **Key ID** | 剛剛產生的 Key 那一列 | `ASC_KEY_ID` |
| **Private Key** | 下載的 `.p8` 檔案內容 | `ASC_PRIVATE_KEY` 或 `ASC_PRIVATE_KEY_PATH` |

---

## 設定方式

### 本機／Docker（使用檔案路徑）
```bash
# .env
ASC_KEY_ID=ABC1234567
ASC_ISSUER_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
ASC_PRIVATE_KEY_PATH=/path/to/AuthKey_ABC1234567.p8
```

### 雲端／CI（直接貼內容）
```bash
# .env
ASC_KEY_ID=ABC1234567
ASC_ISSUER_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
ASC_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nMIGTAgEAMBM...\n-----END PRIVATE KEY-----"
```

> 雲端環境變數中的換行用 `\n` 表示，程式會自動轉換。

---

## 驗證

設定完成後執行一次，log 出現 `[iOS/ASC]` 而非 `[iOS/RSS]` 即成功：

```
[iOS/ASC] 台灣人壽：ASC 取得 50 則，抓到 3 則新評論
```

若失敗會自動降級到 RSS 並顯示錯誤原因：

```
[iOS/ASC] 台灣人壽 失敗，降級至 RSS：ASC API HTTP 401: ...
```

---

## 常見錯誤

| HTTP 狀態 | 原因 | 解決 |
|:---|:---|:---|
| 401 | JWT 簽名無效 | 檢查 Key ID / Issuer ID / .p8 內容是否正確 |
| 403 | 權限不足 | Key 的 Access 需至少為 App Manager |
| 404 | App ID 不存在 | 確認 `config.py` 中的 `ios_id` 正確 |
| 429 | 請求過於頻繁 | API 每小時限額約 3,600 次，正常使用不會觸發 |

---

## 補充說明

- **不需上傳 .p8 到 GitHub**：`.gitignore` 已排除 `.p8` 檔案
- **Key 可撤銷重發**：在 Keys 頁面點擊「Revoke」即可，舊 Key 即刻失效
- **多個 App 共用同一組 Key**：只需一組 ASC API Key 即可存取所有 App 的評論
