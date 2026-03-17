# Microsoft Teams 通知設定指南

## 步驟 1：在 Teams 頻道建立 Webhook

1. 開啟 **Microsoft Teams**，到你想接收通知的 **頻道**
2. 點擊頻道名稱旁的 **「⋯」** → **「管理頻道」**（或「連接器」/「Connectors」）
3. 搜尋 **「Incoming Webhook」** → 點擊 **「設定」**
4. 輸入名稱（例如：`App 評論監測機器人`），可上傳圖示
5. 點擊 **「建立」**
6. 複製產生的 **Webhook URL**（格式：`https://xxx.webhook.office.com/webhookb2/...`）

> ⚠️ 如果找不到「Incoming Webhook」，請聯繫 Teams 管理員啟用此功能。

---

## 步驟 2：設定環境變數

### 方法 A：系統設定（永久生效）

1. 搜尋 **「編輯系統環境變數」** → 點擊 **「環境變數」**
2. 在「使用者變數」中新增：

| 變數名稱 | 值 |
|:---|:---|
| `TEAMS_ENABLED` | `true` |
| `TEAMS_WEBHOOK_URL` | 貼上 Webhook URL |

3. 按確定，**重新啟動終端機**使變數生效

### 方法 B：PowerShell 臨時設定（僅當次生效）

```powershell
$env:TEAMS_ENABLED = "true"
$env:TEAMS_WEBHOOK_URL = "https://xxx.webhook.office.com/webhookb2/..."
python main.py
```

---

## 步驟 3：驗證

```powershell
python -c "from notifier import NotificationManager; m = NotificationManager(); print([type(c).__name__ for c in m.channels])"
```

應看到 `['EmailChannel', 'TeamsChannel']`，表示兩個管道皆已註冊。

執行 `python main.py` 後，成功時會顯示：
```
[NotificationManager] Teams 管道已註冊
[Teams] 通知發送成功
```
