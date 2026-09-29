"""有时限的查看会话；原始凭据与签名密钥只来自私有运行配置。"""

import hashlib
import hmac
import re
import secrets
import time


COOKIE_NAME = "__Host-ai_dashboard_session"
COOKIE_AGE = 180 * 24 * 60 * 60
COOKIE_PATTERN = re.compile(r"([0-9]{1,11})\.([0-9a-f]{32})\.([0-9a-f]{64})\Z")


def _key(secret: str, password: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), password.encode("utf-8"), hashlib.sha256).digest()


def issue_cookie(secret: str, password: str, now: int | None = None) -> str:
    issued = int(time.time()) if now is None else now
    payload = f"{issued}.{secrets.token_hex(16)}"
    signature = hmac.new(_key(secret, password), payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def valid_cookie(value: str | None, secret: str, password: str, now: int | None = None) -> bool:
    if not isinstance(value, str) or not (match := COOKIE_PATTERN.fullmatch(value)):
        return False
    current = int(time.time()) if now is None else now
    issued = int(match.group(1))
    if issued > current or current >= issued + COOKIE_AGE:
        return False
    payload = f"{match.group(1)}.{match.group(2)}".encode("ascii")
    expected = hmac.new(_key(secret, password), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(match.group(3), expected)
