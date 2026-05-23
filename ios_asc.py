"""
iOS App Store Connect API 評論抓取模組。

官方 REST API，JWT 認證，即時且完整的評論資料（含開發者回復關聯）。
相較 iTunes RSS 的 24–72 小時延遲，此路徑能拿到剛發佈的評論。

所需環境變數：
  ASC_KEY_ID            — App Store Connect Keys 頁面的 Key ID
  ASC_ISSUER_ID         — 同頁面上方的 Issuer ID
  ASC_PRIVATE_KEY_PATH  — .p8 私鑰檔案路徑（本機用）
  ASC_PRIVATE_KEY       — 或直接填入 .p8 內容（GCP/雲端用，避免放檔案）

JWT 規格：ES256 演算法，audience 固定為 "appstoreconnect-v1"，最長 20 分鐘。
"""
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

try:
    import jwt  # PyJWT
    _HAS_JWT = True
except ImportError:
    _HAS_JWT = False


ASC_KEY_ID = os.getenv("ASC_KEY_ID", "")
ASC_ISSUER_ID = os.getenv("ASC_ISSUER_ID", "")
ASC_PRIVATE_KEY = os.getenv("ASC_PRIVATE_KEY", "")
ASC_PRIVATE_KEY_PATH = os.getenv("ASC_PRIVATE_KEY_PATH", "")

_API_BASE = "https://api.appstoreconnect.apple.com"
_JWT_TTL_SECONDS = 20 * 60  # ASC 上限
_token_cache: dict = {"token": None, "exp": 0}

# ── 重試設定 ──
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2  # 秒，指數退避：2 → 4 → 8
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def is_configured() -> bool:
    """檢查 ASC API 所需金鑰是否齊全，且 PyJWT 可用。"""
    if not _HAS_JWT:
        return False
    if not (ASC_KEY_ID and ASC_ISSUER_ID):
        return False
    if ASC_PRIVATE_KEY:
        return True
    if ASC_PRIVATE_KEY_PATH and os.path.exists(ASC_PRIVATE_KEY_PATH):
        return True
    return False


def _load_private_key() -> str:
    if ASC_PRIVATE_KEY:
        # 允許將 \n 存成實體字元（雲端環境變數常見寫法）
        return ASC_PRIVATE_KEY.replace("\\n", "\n")
    with open(ASC_PRIVATE_KEY_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _get_jwt() -> str:
    now = int(time.time())
    if _token_cache["token"] and _token_cache["exp"] - now > 60:
        return _token_cache["token"]

    exp = now + _JWT_TTL_SECONDS
    headers = {"alg": "ES256", "kid": ASC_KEY_ID, "typ": "JWT"}
    payload = {
        "iss": ASC_ISSUER_ID,
        "iat": now,
        "exp": exp,
        "aud": "appstoreconnect-v1",
    }
    token = jwt.encode(
        payload, _load_private_key(), algorithm="ES256", headers=headers,
    )
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    _token_cache["token"] = token
    _token_cache["exp"] = exp
    return token


def _request(url: str) -> dict:
    """發送 ASC API 請求，含指數退避重試（429/5xx）。"""
    last_err: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {_get_jwt()}",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code in _RETRYABLE_STATUSES and attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                print(f"[ASC] HTTP {e.code}，{delay}s 後重試（{attempt + 1}/{_MAX_RETRIES}）")
                time.sleep(delay)
                _token_cache["exp"] = 0  # 強制刷新 JWT 避免過期
                last_err = e
                continue
            raise RuntimeError(f"ASC API HTTP {e.code}: {body}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                print(f"[ASC] 連線錯誤，{delay}s 後重試（{attempt + 1}/{_MAX_RETRIES}）：{e}")
                time.sleep(delay)
                last_err = e
                continue
            raise RuntimeError(f"ASC API 連線失敗（已重試 {_MAX_RETRIES} 次）：{e}") from e

    raise RuntimeError(
        f"ASC API 請求失敗（已重試 {_MAX_RETRIES} 次）：{last_err}"
    )


def fetch_reviews(app_id: str, max_reviews: int = 200) -> list[dict]:
    """
    抓取指定 app 的評論（依建立時間由新到舊）。

    回傳每則 dict 含：
      review_id, user_name, rating, title, content, date_obj, has_response
    其中 has_response=True 表示開發者已經回復過，可在通知層濾掉。
    """
    if not is_configured():
        raise RuntimeError("ASC API 未設定（缺 KEY_ID / ISSUER_ID / 私鑰或 PyJWT）")

    page_size = min(max_reviews, 200)
    url = (
        f"{_API_BASE}/v1/apps/{app_id}/customerReviews"
        f"?sort=-createdDate&limit={page_size}&include=response"
    )

    results: list[dict] = []
    while url and len(results) < max_reviews:
        payload = _request(url)

        # 從 included 區段推算有開發者回復的評論 ID
        response_review_ids: set[str] = set()
        for item in payload.get("included", []) or []:
            if item.get("type") != "customerReviewResponses":
                continue
            rel = (
                item.get("relationships", {})
                .get("review", {})
                .get("data", {})
            ) or {}
            rid = rel.get("id")
            if rid:
                response_review_ids.add(rid)

        for data in payload.get("data", []) or []:
            attrs = data.get("attributes", {}) or {}
            review_id = data.get("id", "")
            if not review_id:
                continue

            date_str = attrs.get("createdDate") or ""
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                dt = None

            # 有兩種來源：include response 的關聯 data、或在 included 找到的 review id
            rel_resp = (
                data.get("relationships", {})
                .get("response", {})
                .get("data")
            )
            has_response = bool(rel_resp) or review_id in response_review_ids

            results.append({
                "review_id": review_id,
                "user_name": attrs.get("reviewerNickname", "") or "",
                "rating": int(attrs.get("rating", 0) or 0),
                "title": attrs.get("title", "") or "",
                "content": attrs.get("body", "") or "",
                "date_obj": dt,
                "has_response": has_response,
            })

        next_link = (payload.get("links") or {}).get("next")
        url = next_link if len(results) < max_reviews else None

    return results[:max_reviews]
