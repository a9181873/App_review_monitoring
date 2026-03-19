"""
App 評論監測工具 — 多通道通知模組
支援 Email (SMTP) 與 Microsoft Teams (Incoming Webhook)。
透過 NotificationManager 統一管理所有已啟用的通知管道。
含指數退避重試機制。
"""
import json
import smtplib
import time
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config


# ──────────────────────────────────────────────
# 重試裝飾器
# ──────────────────────────────────────────────
def _retry_on_failure(func):
    """指數退避重試裝飾器，使用 config 中的重試設定。"""

    def wrapper(*args, **kwargs):
        max_retries = config.NOTIFY_MAX_RETRIES
        base_delay = config.NOTIFY_RETRY_BASE_DELAY

        for attempt in range(1, max_retries + 1):
            result = func(*args, **kwargs)
            if result:
                return True
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                print(f"  ↳ 第 {attempt} 次失敗，{delay} 秒後重試...")
                time.sleep(delay)

        print(f"  ↳ 已重試 {max_retries} 次，全部失敗")
        return False

    return wrapper


# ──────────────────────────────────────────────
# 抽象基底類別
# ──────────────────────────────────────────────
class NotificationChannel(ABC):
    """所有通知管道的基底類別。"""

    @abstractmethod
    def _send_once(self, subject: str, body: str) -> bool:
        """單次發送嘗試。"""
        ...

    def send(self, subject: str, body: str) -> bool:
        """帶重試的發送。"""
        return _retry_on_failure(self._send_once)(subject, body)


# ──────────────────────────────────────────────
# Email Channel (SMTP)
# ──────────────────────────────────────────────
class EmailChannel(NotificationChannel):
    """透過 SMTP 發送 Email 通知。"""

    def __init__(
        self,
        smtp_server: str,
        smtp_port: int,
        sender: str,
        password: str,
        recipients: list[str],
    ):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.sender = sender
        self.password = password
        self.recipients = recipients

    def _send_once(self, subject: str, body: str) -> bool:
        if not self.sender or not self.password:
            print("[Email] 尚未設定寄件人或密碼，跳過 Email 通知。")
            return False

        msg = MIMEMultipart("alternative")
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.recipients)
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain", "utf-8"))
        html_body = body.replace("\n", "<br>")
        msg.attach(MIMEText(f"<html><body>{html_body}</body></html>", "html", "utf-8"))

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender, self.password)
                server.sendmail(self.sender, self.recipients, msg.as_string())
            print(f"[Email] 發送成功 → {', '.join(self.recipients)}")
            return True
        except Exception as e:
            print(f"[Email] 發送失敗：{e}")
            return False


# ──────────────────────────────────────────────
# Teams Channel (Incoming Webhook)
# ──────────────────────────────────────────────
class TeamsChannel(NotificationChannel):
    """透過 Incoming Webhook 發送 Microsoft Teams 通知。"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def _send_once(self, subject: str, body: str) -> bool:
        if not self.webhook_url:
            print("[Teams] 尚未設定 Webhook URL，跳過 Teams 通知。")
            return False

        try:
            import requests
        except ImportError:
            print("[Teams] 缺少 requests 套件，請執行 pip install requests")
            return False

        card_payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": subject,
                                "weight": "Bolder",
                                "size": "Medium",
                                "wrap": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": body,
                                "wrap": True,
                                "maxLines": 0,
                            },
                        ],
                    },
                }
            ],
        }

        try:
            resp = requests.post(
                self.webhook_url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(card_payload),
                timeout=30,
            )
            if resp.status_code in (200, 202):
                print("[Teams] 通知發送成功")
                return True
            else:
                print(f"[Teams] 發送失敗 (HTTP {resp.status_code}): {resp.text}")
                return False
        except Exception as e:
            print(f"[Teams] 發送失敗：{e}")
            return False


# ──────────────────────────────────────────────
# NotificationManager — 統一管理
# ──────────────────────────────────────────────
class NotificationManager:
    """根據 config 設定自動註冊啟用的通知管道，統一派發通知。"""

    def __init__(self):
        self.channels: list[NotificationChannel] = []
        self._auto_register()

    def _auto_register(self):
        """根據 config 設定自動註冊管道。"""
        if config.EMAIL_ENABLED:
            self.channels.append(
                EmailChannel(
                    smtp_server=config.EMAIL_SMTP_SERVER,
                    smtp_port=config.EMAIL_SMTP_PORT,
                    sender=config.EMAIL_SENDER,
                    password=config.EMAIL_PASSWORD,
                    recipients=config.EMAIL_RECIPIENTS,
                )
            )
            print("[NotificationManager] Email 管道已註冊")

        if config.TEAMS_ENABLED:
            self.channels.append(TeamsChannel(webhook_url=config.TEAMS_WEBHOOK_URL))
            print("[NotificationManager] Teams 管道已註冊")

        if not self.channels:
            print("[NotificationManager] 未啟用任何通知管道")

    def register_channel(self, channel: NotificationChannel):
        """手動註冊額外的通知管道。"""
        self.channels.append(channel)

    def send_all(self, subject: str, body: str) -> dict[str, bool]:
        """向所有已註冊的管道發送通知，回傳各管道的發送結果。"""
        results = {}
        for ch in self.channels:
            name = type(ch).__name__
            results[name] = ch.send(subject, body)
        return results


# ──────────────────────────────────────────────
# 便利函式（向後相容 & 快速使用）
# ──────────────────────────────────────────────
def send_notification(subject: str, body: str) -> dict[str, bool]:
    """快捷函式：建立 NotificationManager 並發送通知。"""
    manager = NotificationManager()
    return manager.send_all(subject, body)


if __name__ == "__main__":
    print("=== 通知管道測試 ===")
    manager = NotificationManager()
    print(f"已註冊管道: {[type(c).__name__ for c in manager.channels]}")
