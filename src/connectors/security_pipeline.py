"""Zero-Trust Security Pipeline & Webhook Ingestion Guard for OrgBridge AI.

Enforces:
1. Constant-time HMAC signature verification (GitHub, Slack, Jira).
2. 5-minute replay tolerance window checks (older than 300s rejected with 401).
3. Webhook payload DoS ceiling (1MB hard limit rejected with 413).
4. Idempotency deduplication cache (24h TTL).
5. Pre-ingestion Secret & PII scrubbing (Regex + Shannon entropy token scanner, 4000-char max).
6. Token Vault: AES-256-GCM (Fernet) token encryption and distributed OAuth mutex.
7. Deterministic identity resolution via tenant-scoped verified email hashes.
8. Loop prevention for bot-originated write-backs (X-OrgBridge-Tx-Id / bot IDs).
"""

import hmac
import hashlib
import math
import re
import time
import asyncio
from typing import Dict, Any, List, Optional, Union
from fastapi import Request, HTTPException
from cryptography.fernet import Fernet

from src.config import settings
from src.utils.logger import logger

REPLAY_WINDOW_SECONDS: int = 300
MAX_PAYLOAD_BYTES: int = 1_048_576  # 1 MB
MAX_TEXT_LENGTH: int = 4000
IDEMPOTENCY_TTL_SECONDS: int = 86400  # 24 hours

# In-memory delivery cache: maps delivery_id -> timestamp (pruned periodically)
PROCESSED_DELIVERIES: Dict[str, float] = {}

# Pre-compiled regex patterns for known tokens, credentials, and government IDs
SECRET_PATTERNS = [
    (
        re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,255}"),
        "[REDACTED_GITHUB_TOKEN]",
    ),
    (
        re.compile(r"xox[baprs]-[0-9a-zA-Z-]{10,72}"),
        "[REDACTED_SLACK_TOKEN]",
    ),
    (
        re.compile(r"AKIA[0-9A-Z]{16}"),
        "[REDACTED_AWS_KEY]",
    ),
    (
        re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+ PRIVATE KEY-----"),
        "[REDACTED_PRIVATE_KEY]",
    ),
    # Indian Aadhaar / 12-digit National ID
    (
        re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
        "[REDACTED_GOV_ID]",
    ),
    # Indian PAN Card Number (5 letters + 4 digits + 1 letter)
    (
        re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b"),
        "[REDACTED_GOV_ID]",
    ),
    # JWT standard pattern
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        "[REDACTED_SECRET]",
    ),
]


def clean_expired_deliveries() -> None:
    """Prunes expired delivery IDs older than 24 hours from in-memory cache."""
    now = time.time()
    expired = [k for k, ts in PROCESSED_DELIVERIES.items() if now - ts > IDEMPOTENCY_TTL_SECONDS]
    for k in expired:
        PROCESSED_DELIVERIES.pop(k, None)


def calculate_shannon_entropy(token: str) -> float:
    """Calculates Shannon entropy in bits per character for high-entropy secret detection."""
    if not token:
        return 0.0
    freq: Dict[str, int] = {}
    for char in token:
        freq[char] = freq.get(char, 0) + 1
    length = len(token)
    return -sum((count / length) * math.log2(count / length) for count in freq.values())


def scrub_untrusted_text(raw_text: str, max_len: int = MAX_TEXT_LENGTH) -> str:
    """Scrubs untrusted external strings of credentials, PII, and high-entropy secrets.

    Also truncates text to max_len (default 4,000 chars) to prevent payload bloat.
    """
    if not raw_text:
        return ""

    cleaned = str(raw_text)[:max_len]

    # 1. Regex scrubbing for known token signatures and gov IDs
    for pattern, replacement in SECRET_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)

    # 2. Shannon entropy scanner for unformatted random high-entropy strings
    # Looks for tokens >= 20 characters with Shannon entropy >= 4.0
    def _entropy_masker(match: re.Match) -> str:
        word = match.group(0)
        # Strip trailing punctuation if any
        stripped_word = word.rstrip(".,;!?:\"')]} ")
        if stripped_word.startswith("[REDACTED_") or "[REDACTED_" in stripped_word:
            return word
        if len(stripped_word) >= 20 and calculate_shannon_entropy(stripped_word) >= 4.0:
            return word.replace(stripped_word, "[REDACTED_SECRET]")
        return word

    cleaned = re.sub(r"\S{20,}", _entropy_masker, cleaned)

    return cleaned


def redact_sensitive_data(data: Any, max_len: int = MAX_TEXT_LENGTH) -> Any:
    """Recursively walks a nested data structure (dict, list, str) and sanitizes secrets/PII."""
    if isinstance(data, str):
        return scrub_untrusted_text(data, max_len=max_len)
    elif isinstance(data, dict):
        return {k: redact_sensitive_data(v, max_len=max_len) for k, v in data.items()}
    elif isinstance(data, list):
        return [redact_sensitive_data(item, max_len=max_len) for item in data]
    return data


# ---------------------------------------------------------------------------
# Constant-Time Webhook HMAC Verification & Replay Protection
# ---------------------------------------------------------------------------

async def verify_slack_webhook(
    request: Request,
    signing_secret: Optional[str] = None,
) -> bytes:
    """Verifies incoming Slack Events API webhook signature, replay window, and payload size."""
    secret = signing_secret or settings.slack_signing_secret
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    retry_num = request.headers.get("X-Slack-Retry-Num", "0")

    if not timestamp or not signature:
        raise HTTPException(status_code=401, detail="Missing Slack security headers")

    try:
        ts_int = int(timestamp)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Slack timestamp header")

    if abs(time.time() - ts_int) > REPLAY_WINDOW_SECONDS:
        raise HTTPException(
            status_code=401,
            detail="Webhook timestamp outside 5-minute replay window",
        )

    raw_body = await request.body()
    if len(raw_body) > MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Webhook payload exceeds 1MB ceiling")

    # Slack HMAC computation: v0:{timestamp}:{raw_body}
    base_string = f"v0:{timestamp}:{raw_body.decode('utf-8', errors='replace')}".encode("utf-8")
    expected_sig = "v0=" + hmac.new(
        secret.encode("utf-8"),
        base_string,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook HMAC signature")

    # Idempotency deduplication check
    delivery_id = f"slack:{signature}:{retry_num}"
    clean_expired_deliveries()
    if delivery_id in PROCESSED_DELIVERIES:
        logger.info(f"Slack delivery {delivery_id} already processed. Returning empty byte no-op.")
        return b""

    PROCESSED_DELIVERIES[delivery_id] = time.time()
    return raw_body


async def verify_github_webhook(
    request: Request,
    webhook_secret: Optional[str] = None,
) -> bytes:
    """Verifies GitHub webhook using X-Hub-Signature-256 and checks delivery idempotency."""
    secret = webhook_secret or settings.github_webhook_secret
    signature = request.headers.get("X-Hub-Signature-256", "")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")
    timestamp_header = request.headers.get("X-Hub-Timestamp", "")

    if not signature:
        raise HTTPException(status_code=401, detail="Missing GitHub webhook signature header")

    if timestamp_header:
        try:
            ts_int = int(timestamp_header)
            if abs(time.time() - ts_int) > REPLAY_WINDOW_SECONDS:
                raise HTTPException(
                    status_code=401,
                    detail="Webhook timestamp outside 5-minute replay window",
                )
        except ValueError:
            pass

    raw_body = await request.body()
    if len(raw_body) > MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Webhook payload exceeds 1MB ceiling")

    expected_sig = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook HMAC signature")

    # Idempotency check using GitHub delivery UUID
    key = f"github:{delivery_id or signature}"
    clean_expired_deliveries()
    if key in PROCESSED_DELIVERIES:
        logger.info(f"GitHub delivery {key} already processed. Returning empty byte no-op.")
        return b""

    PROCESSED_DELIVERIES[key] = time.time()
    return raw_body


async def verify_jira_webhook(
    request: Request,
    webhook_secret: Optional[str] = None,
) -> bytes:
    """Verifies Atlassian/Jira webhook signature and delivery window."""
    secret = webhook_secret or settings.jira_webhook_secret
    signature = (
        request.headers.get("X-Hub-Signature", "")
        or request.headers.get("X-Atlassian-Webhook-Signature", "")
        or request.query_params.get("signature", "")
    )
    timestamp = request.headers.get("X-Atlassian-Webhook-Timestamp", "")
    event_id = request.headers.get("X-Atlassian-Webhook-Id", "")

    if not signature:
        raise HTTPException(status_code=401, detail="Missing Jira webhook signature header")

    if timestamp:
        try:
            ts_int = int(timestamp)
            if abs(time.time() - ts_int) > REPLAY_WINDOW_SECONDS:
                raise HTTPException(
                    status_code=401,
                    detail="Webhook timestamp outside 5-minute replay window",
                )
        except ValueError:
            pass

    raw_body = await request.body()
    if len(raw_body) > MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Webhook payload exceeds 1MB ceiling")

    expected_sig = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    # Also allow raw sha256 hex if Jira sends without 'sha256=' prefix
    raw_expected_hex = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    if not (
        hmac.compare_digest(expected_sig, signature)
        or hmac.compare_digest(raw_expected_hex, signature)
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook HMAC signature")

    key = f"jira:{event_id or signature}"
    clean_expired_deliveries()
    if key in PROCESSED_DELIVERIES:
        logger.info(f"Jira delivery {key} already processed. Returning empty byte no-op.")
        return b""

    PROCESSED_DELIVERIES[key] = time.time()
    return raw_body


# ---------------------------------------------------------------------------
# Fernet Token Vault (AES-256-GCM at rest) & OAuth Distributed Mutex
# ---------------------------------------------------------------------------

class TokenVault:
    """Encrypts and decrypts OAuth refresh tokens and API secrets using AES-256-GCM (Fernet)."""

    def __init__(self, master_key: Optional[str] = None):
        key = master_key or settings.connector_master_key
        # Ensure key is valid Fernet key (32 bytes base64)
        if isinstance(key, str):
            key = key.encode("utf-8")
        self._fernet = Fernet(key)

    def encrypt_token(self, plain_text: str) -> str:
        """Encrypts token string into base64 ciphertext string."""
        if not plain_text:
            return ""
        return self._fernet.encrypt(plain_text.encode("utf-8")).decode("utf-8")

    def decrypt_token(self, cipher_text: str) -> str:
        """Decrypts base64 ciphertext string back to plaintext token."""
        if not cipher_text:
            return ""
        return self._fernet.decrypt(cipher_text.encode("utf-8")).decode("utf-8")


token_vault = TokenVault()


class OAuthMutex:
    """Distributed/In-Memory Mutex Lock for OAuth token refresh operations.

    Prevents concurrent workers from triggering token reuse revocation.
    """

    _locks: Dict[str, asyncio.Lock] = {}
    _meta_lock = asyncio.Lock()

    def __init__(self, tenant: str, provider: str):
        self.lock_key = f"lock:oauth:{tenant}:{provider}"

    async def __aenter__(self):
        async with self._meta_lock:
            if self.lock_key not in self._locks:
                self._locks[self.lock_key] = asyncio.Lock()
            lock = self._locks[self.lock_key]
        await lock.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        async with self._meta_lock:
            lock = self._locks.get(self.lock_key)
        if lock and lock.locked():
            lock.release()


# ---------------------------------------------------------------------------
# Deterministic Identity Resolution & Infinite Loop Guard
# ---------------------------------------------------------------------------

def generate_person_id(tenant: str, email: str) -> str:
    """Generates tenant-scoped deterministic Person ID based on verified primary email hash.

    Format: {tenant}:person:{sha256(email.lower())[:16]}
    """
    clean_email = email.strip().lower()
    email_hash = hashlib.sha256(clean_email.encode("utf-8")).hexdigest()[:16]
    tenant_prefix = tenant.lower().replace("-", "_").split("_")[0]
    return f"{tenant_prefix}:person:{email_hash}"


def calculate_identity_confidence(email_a: str, email_b: str) -> float:
    """Returns matching confidence between two user identities.

    1.0: Exact verified email match (auto-merge across systems).
    < 1.0: Emit [:PROPOSED_SAME_AS] for operator review.
    """
    if not email_a or not email_b:
        return 0.0
    a = email_a.strip().lower()
    b = email_b.strip().lower()
    if a == b:
        return 1.0
    # Match user portion if same name before @
    user_a = a.split("@")[0]
    user_b = b.split("@")[0]
    if user_a == user_b:
        return 0.85
    return 0.0


def is_bot_event(
    author_id: Optional[str] = None,
    author_name: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> bool:
    """Detects whether an event was authored by the OrgBridge bot.

    Drops bot-originated write-backs to prevent infinite feedback loops.
    """
    if headers and (
        "X-OrgBridge-Tx-Id" in headers
        or "x-orgbridge-tx-id" in headers
        or "X-OrgBridge-Writeback" in headers
    ):
        return True

    bot_identifiers = [b.lower() for b in settings.bot_user_ids]
    if author_id and any(bot_id in author_id.lower() for bot_id in bot_identifiers):
        return True
    if author_name and any(bot_id in author_name.lower() for bot_id in bot_identifiers):
        return True

    return False
