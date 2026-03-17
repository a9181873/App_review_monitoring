"""
App 評論監測工具 — 集中設定檔
所有可調整的參數皆在此管理，敏感資訊優先從環境變數讀取。
"""
import os

# ──────────────────────────────────────────────
# 路徑設定（預設為專案目錄下的子資料夾）
# ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

# 確保目錄存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

# ──────────────────────────────────────────────
# 監控的 App 清單
# ──────────────────────────────────────────────
APPS = [
    {
        "name": "台灣人壽",
        "ios_id": "1473215082",
        "android_id": "com.taiwanlife.app",
    },
    {
        "name": "TeamWalk",
        "ios_id": "1559679863",
        "android_id": "com.taiwanlife.teamwalk",
    },
]

# ──────────────────────────────────────────────
# Android 抓取設定
# ──────────────────────────────────────────────
ANDROID_REVIEW_COUNT = 200   # 每次抓取的最大評論數
ANDROID_LANG = "zh-tw"
ANDROID_COUNTRY = "tw"

# iOS 抓取設定
IOS_REVIEW_COUNT = 50
IOS_COUNTRY = "tw"

# ──────────────────────────────────────────────
# Email 通知設定
# ──────────────────────────────────────────────
EMAIL_ENABLED = True
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "s49281008@gmail.com")
EMAIL_PASSWORD = "myzr llsd jokp njwk"  # Gmail App 密碼
EMAIL_RECIPIENTS = [
    addr.strip()
    for addr in os.getenv("EMAIL_RECIPIENTS", "s49281008@gmail.com").split(",")
    if addr.strip()
]

# ──────────────────────────────────────────────
# Microsoft Teams 通知設定
# ──────────────────────────────────────────────
TEAMS_ENABLED = True
TEAMS_WEBHOOK_URL = "https://ctbctaiwanlife.webhook.office.com/webhookb2/00387e18-445d-436f-926f-30cbe038d8d8@ff3a4655-94b8-494e-9455-8d21f9db1c51/IncomingWebhook/05e4c95de2a84291b6e4bd96187d51d0/f86f5e27-f3d2-43c7-99fe-500e158abd12/V2zr2y7RKvtm-EorN092a0csv5wsmx_CUccYpm09Xgh281"
