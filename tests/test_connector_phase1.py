"""Phase 1 Security Core & Parameterized Schema Unit Tests.

Verifies:
1. HMAC signature validation (Slack, GitHub, Jira) and rejection of forged signatures (401).
2. 5-minute replay window tolerance and rejection of expired timestamps (401).
3. Payload DoS protection (1MB ceiling) rejection with 413.
4. Delivery idempotency deduplication (idempotent no-op for retries).
5. Secret & PII scrubber (GitHub tokens, Slack tokens, AWS keys, private keys, Gov IDs, Shannon entropy).
6. 4,000-character truncation ceiling.
7. Fernet Token Vault encryption/decryption at rest and OAuth distributed mutex.
8. Deterministic identity resolution via tenant email hashing.
9. Cypher injection immunity via parameterized $props queries.
"""

import hmac
import hashlib
import time
import asyncio
import pytest
from fastapi import Request, HTTPException
from starlette.datastructures import Headers

from src.config import settings
from src.connectors.security_pipeline import (
    verify_slack_webhook,
    verify_github_webhook,
    verify_jira_webhook,
    scrub_untrusted_text,
    redact_sensitive_data,
    calculate_shannon_entropy,
    TokenVault,
    OAuthMutex,
    generate_person_id,
    calculate_identity_confidence,
    is_bot_event,
    PROCESSED_DELIVERIES,
    REPLAY_WINDOW_SECONDS,
)
from src.schema.cypher_schema import (
    UPSERT_TICKET_CYPHER,
    UPSERT_SYSTEM_CYPHER,
    UPSERT_DECISION_CYPHER,
    TOMBSTONE_NODE_CYPHER,
    build_parameterized_node_merge,
    build_parameterized_relationship_merge,
    validate_readonly_cypher,
)


def make_mock_request(
    body: bytes,
    headers: dict,
    query_params: dict = None,
) -> Request:
    """Creates a mock FastAPI Request object for testing."""
    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()],
        "query_string": "&".join(f"{k}={v}" for k, v in (query_params or {}).items()).encode("latin-1"),
    }
    req = Request(scope)

    async def _body():
        return body

    req.body = _body
    return req


# ---------------------------------------------------------------------------
# 1. HMAC Verification & Replay Tolerance Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_slack_webhook_valid_and_forged_signatures():
    secret = "test-slack-secret"
    body = b'{"type":"event_callback","event":{"text":"hello"}}'
    ts = str(int(time.time()))

    # Compute valid signature
    base = f"v0:{ts}:{body.decode('utf-8')}".encode("utf-8")
    valid_sig = "v0=" + hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()

    # 1. Valid signature passes
    req_valid = make_mock_request(
        body=body,
        headers={
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": valid_sig,
            "X-Slack-Retry-Num": "0",
        },
    )
    result = await verify_slack_webhook(req_valid, signing_secret=secret)
    assert result == body

    # 2. Forged signature fails with 401
    req_forged = make_mock_request(
        body=body,
        headers={
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": "v0=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            "X-Slack-Retry-Num": "0",
        },
    )
    with pytest.raises(HTTPException) as exc_info:
        await verify_slack_webhook(req_forged, signing_secret=secret)
    assert exc_info.value.status_code == 401
    assert "Invalid webhook HMAC signature" in exc_info.value.detail


@pytest.mark.asyncio
async def test_slack_webhook_replay_tolerance_and_missing_headers():
    secret = "test-slack-secret"
    body = b'{"event":"test"}'

    # Expired timestamp (10 minutes ago, exceeds 300s window)
    expired_ts = str(int(time.time()) - 600)
    base = f"v0:{expired_ts}:{body.decode('utf-8')}".encode("utf-8")
    sig = "v0=" + hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()

    req_expired = make_mock_request(
        body=body,
        headers={
            "X-Slack-Request-Timestamp": expired_ts,
            "X-Slack-Signature": sig,
        },
    )
    with pytest.raises(HTTPException) as exc:
        await verify_slack_webhook(req_expired, signing_secret=secret)
    assert exc.value.status_code == 401
    assert "5-minute replay window" in exc.value.detail

    # Missing headers
    req_no_headers = make_mock_request(body=body, headers={})
    with pytest.raises(HTTPException) as exc_missing:
        await verify_slack_webhook(req_no_headers, signing_secret=secret)
    assert exc_missing.value.status_code == 401


@pytest.mark.asyncio
async def test_github_webhook_verification_and_replay_idempotency():
    secret = "test-github-secret"
    body = b'{"action":"opened","pull_request":{"id":123}}'
    delivery_id = "test-delivery-uuid-999"

    valid_sig = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    req_valid = make_mock_request(
        body=body,
        headers={
            "X-Hub-Signature-256": valid_sig,
            "X-GitHub-Delivery": delivery_id,
        },
    )
    # First delivery: processed
    res = await verify_github_webhook(req_valid, webhook_secret=secret)
    assert res == body

    # Second delivery with same delivery_id: returns b"" (idempotent no-op)
    res_duplicate = await verify_github_webhook(req_valid, webhook_secret=secret)
    assert res_duplicate == b""

    # Forged signature fails with 401
    req_forged = make_mock_request(
        body=body,
        headers={
            "X-Hub-Signature-256": "sha256=badf00dbadf00d",
            "X-GitHub-Delivery": "new-delivery",
        },
    )
    with pytest.raises(HTTPException) as exc:
        await verify_github_webhook(req_forged, webhook_secret=secret)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_jira_webhook_verification():
    secret = "test-jira-secret"
    body = b'{"issue":{"key":"FIN-1042","fields":{"summary":"Auth issue"}}}'

    sig = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    req = make_mock_request(
        body=body,
        headers={"X-Atlassian-Webhook-Signature": sig},
    )
    res = await verify_jira_webhook(req, webhook_secret=secret)
    assert res == body

    # Forged signature
    req_bad = make_mock_request(
        body=body,
        headers={"X-Atlassian-Webhook-Signature": "sha256=invalid"},
    )
    with pytest.raises(HTTPException) as exc:
        await verify_jira_webhook(req_bad, webhook_secret=secret)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_payload_ceiling_dos_protection():
    # 1MB ceiling check (> 1,048,576 bytes)
    huge_body = b"A" * (1_048_576 + 10)
    secret = "test-secret"
    ts = str(int(time.time()))
    sig = "v0=dummy"

    req_huge = make_mock_request(
        body=huge_body,
        headers={"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": sig},
    )
    with pytest.raises(HTTPException) as exc:
        await verify_slack_webhook(req_huge, signing_secret=secret)
    assert exc.value.status_code == 413
    assert "exceeds 1MB ceiling" in exc.value.detail


# ---------------------------------------------------------------------------
# 2. Pre-Ingestion Secret & PII Scrubber Tests
# ---------------------------------------------------------------------------

def test_secret_scrubber_known_patterns():
    # GitHub Personal Access Token (constructed dynamically so GitHub Push Protection is not triggered)
    gh_sample = "ghp_" + "A" * 36
    gh_text = f"Commit authored with {gh_sample} by dev"
    cleaned = scrub_untrusted_text(gh_text)
    assert "[REDACTED_GITHUB_TOKEN]" in cleaned
    assert "ghp_" not in cleaned

    # Slack Bot Token (constructed dynamically)
    slack_sample = "xoxb-" + "123456789012" + "-" + "1234567890123" + "-" + "abcdefghijklmnopqrstuv"
    slack_text = f"Use bot token {slack_sample} for channel"
    cleaned_slack = scrub_untrusted_text(slack_text)
    assert "[REDACTED_SLACK_TOKEN]" in cleaned_slack
    assert "xoxb-" not in cleaned_slack

    # AWS Key (standard AWS dummy docs example constructed dynamically)
    aws_sample = "AKIA" + "IOSFODNN7EXAMPLE"
    aws_text = f"Connecting S3 bucket with {aws_sample}"
    cleaned_aws = scrub_untrusted_text(aws_text)
    assert "[REDACTED_AWS_KEY]" in cleaned_aws
    assert "AKIA" not in cleaned_aws

    # Private Key
    priv_key_text = (
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0m4w1234567890...\n-----END RSA PRIVATE KEY-----"
    )
    cleaned_key = scrub_untrusted_text(priv_key_text)
    assert "[REDACTED_PRIVATE_KEY]" in cleaned_key

    # Gov IDs: Indian Aadhaar (12 digits) & Indian PAN
    id_text = "Customer aadhaar is 9876 5432 1098 and PAN is ABCDE1234F for verification"
    cleaned_ids = scrub_untrusted_text(id_text)
    assert cleaned_ids.count("[REDACTED_GOV_ID]") == 2
    assert "9876" not in cleaned_ids
    assert "ABCDE1234F" not in cleaned_ids


def test_shannon_entropy_detection():
    # High-entropy random secret string
    random_secret = "k8J#mN9$vP2!xL5&wQ0*zR4@"
    entropy = calculate_shannon_entropy(random_secret)
    assert entropy >= 4.0

    scrubbed = scrub_untrusted_text(f"Key is {random_secret}")
    assert "[REDACTED_SECRET]" in scrubbed

    # Low-entropy normal text should NOT be redacted
    normal_text = "The quick brown fox jumps over the lazy dog repeatedly"
    assert scrub_untrusted_text(normal_text) == normal_text


def test_scrubber_truncation_ceiling():
    long_text = "A" * 6000
    cleaned = scrub_untrusted_text(long_text, max_len=4000)
    assert len(cleaned) == 4000


def test_recursive_payload_redaction():
    aws_sample = "AKIA" + "IOSFODNN7EXAMPLE"
    slack_sample = "xoxb-" + "123456789012" + "-" + "abcdefghijklmnopqrstuv"
    payload = {
        "commit": {
            "message": f"Update AWS config {aws_sample} in service",
            "author": "dev@finpay.com",
            "meta": [f"token={slack_sample}"],
        }
    }
    redacted = redact_sensitive_data(payload)
    assert "[REDACTED_AWS_KEY]" in redacted["commit"]["message"]
    assert "[REDACTED_SLACK_TOKEN]" in redacted["commit"]["meta"][0]
    assert redacted["commit"]["author"] == "dev@finpay.com"


# ---------------------------------------------------------------------------
# 3. Token Vault & Distributed Mutex Tests
# ---------------------------------------------------------------------------

def test_token_vault_encryption_decryption():
    vault = TokenVault(settings.connector_master_key)
    plain_token = "ghp_super_secret_github_app_token_99999"

    encrypted = vault.encrypt_token(plain_token)
    assert encrypted != plain_token
    assert len(encrypted) > 20

    decrypted = vault.decrypt_token(encrypted)
    assert decrypted == plain_token


@pytest.mark.asyncio
async def test_oauth_mutex_concurrency():
    lock_records = []

    async def worker(worker_id: int):
        async with OAuthMutex(tenant="finpay", provider="jira"):
            lock_records.append(f"start_{worker_id}")
            await asyncio.sleep(0.02)
            lock_records.append(f"end_{worker_id}")

    # Run two concurrent workers competing for the same OAuth mutex
    await asyncio.gather(worker(1), worker(2))

    # Verification: workers must execute sequentially, not interleaved
    assert lock_records == ["start_1", "end_1", "start_2", "end_2"] or \
           lock_records == ["start_2", "end_2", "start_1", "end_1"]


# ---------------------------------------------------------------------------
# 4. Identity Resolution & Loop Prevention Tests
# ---------------------------------------------------------------------------

def test_deterministic_person_id():
    id_1 = generate_person_id("FinPay", "aarav@finpay.com")
    id_2 = generate_person_id("finpay-org", "AARAV@finpay.com ")
    assert id_1 == id_2
    assert id_1.startswith("finpay:person:")

    id_vaultly = generate_person_id("Vaultly", "aarav@vaultly.com")
    assert id_vaultly.startswith("vaultly:person:")
    assert id_1 != id_vaultly  # Scoped to tenant to prevent collision


def test_calculate_identity_confidence():
    assert calculate_identity_confidence("diya@vaultly.com", "DIYA@vaultly.com") == 1.0
    assert calculate_identity_confidence("aarav@finpay.com", "aarav@vaultly.com") == 0.85
    assert calculate_identity_confidence("alice@finpay.com", "bob@vaultly.com") == 0.0


def test_bot_event_detection():
    assert is_bot_event(author_id="orgbridge-bot") is True
    assert is_bot_event(author_id="U_ORGBRIDGE_BOT") is True
    assert is_bot_event(headers={"X-OrgBridge-Tx-Id": "tx-12345"}) is True
    assert is_bot_event(author_id="regular-developer") is False


# ---------------------------------------------------------------------------
# 5. Parameterized Cypher & Injection Immunity Tests
# ---------------------------------------------------------------------------

def test_parameterized_node_merge_injection_immunity():
    # Attempt Cypher injection payload in name
    malicious_name = "Auth Service'}) DETACH DELETE n //"
    props = {
        "id": "finpay:sys:auth_injected",
        "name": malicious_name,
        "tech": "Python/FastAPI",
        "domain": "Authentication",
    }
    query, params = build_parameterized_node_merge("System", props)

    assert "$props" in query
    assert malicious_name not in query  # Never interpolated into the query string!
    assert params["props"]["name"] == malicious_name
    assert params["node_id"] == "finpay:sys:auth_injected"


def test_parameterized_relationship_merge():
    query, params = build_parameterized_relationship_merge(
        source_id="finpay:sys:auth",
        target_id="vaultly:sys:pulse",
        rel_type="CONFLICTS_WITH",
        properties={"reason": "Incompatible JWT TTL', DETACH DELETE r //"},
    )
    assert "$src_id" in query
    assert "$tgt_id" in query
    assert "CONFLICTS_WITH" in query
    assert "DETACH DELETE" not in query
    assert "props" in params


def test_readonly_cypher_validator_blocks_mutations():
    # Verify that dangerous mutation commands are blocked
    blocked_commands = [
        "MATCH (n) DETACH DELETE n",
        "MERGE (p:Policy {id: 'hack'}) RETURN p",
        "CREATE (p:Person {id: 'bad'}) RETURN p",
        "DROP INDEX ON :Person(id)",
    ]
    for cmd in blocked_commands:
        res = validate_readonly_cypher(cmd)
        assert res["valid"] is False
        assert res["error_code"] == "MUTATING_OPERATION_PROHIBITED"
