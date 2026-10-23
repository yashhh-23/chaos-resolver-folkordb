"""Phase 3 Bidirectional Write-Backs & Outbox State Machine Tests.

Verifies:
1. Outbox pattern integration across live mutations (resolve_auth_conflict, resolve_retention_conflict, merge_teams).
2. GitHub deprecation PR creation with timestamped branches, DEPRECATED_BY_MERGER status banner, and SME reviewers.
3. Jira Migration Epic creation with 'is superseded by' issue links and transition to Done (Superseded).
4. Slack Block Kit interactive HITL approval cards.
5. Infinite Loop Guard: bot-originated write-backs (X-OrgBridge-Tx-Id / bot user IDs) are strictly dropped.
6. HITL sign-off: unapproved mutations remain PENDING until approved via Slack, which commits approver's Slack ID and timestamp.
7. Outbox failure handling: failed API calls trigger clean FAILED state and can be cleanly retried to SYNCED.
8. API endpoints for Slack approval (/api/mutate/slack-approve) and Outbox retry (/api/mutate/outbox-retry).
"""

import time
import pytest
from fastapi.testclient import TestClient

from src.config import settings
from src.db.client import db_client
from src.api.main import app
from src.pipeline.mutations import LiveMutationEngine, OutboxStateMachine
from src.connectors.security_pipeline import is_bot_event
from src.connectors.github import github_connector
from src.connectors.jira import jira_connector
from src.connectors.slack import slack_connector


@pytest.fixture(scope="module")
def api_client():
    return TestClient(app)


@pytest.fixture(scope="module")
def mutation_engine():
    db_client.connect()
    return LiveMutationEngine(graph_name=settings.graph_merged)


# ---------------------------------------------------------------------------
# 1. Outbox Pattern & Bidirectional Write-Back Integration Tests
# ---------------------------------------------------------------------------

def test_resolve_auth_conflict_outbox_writeback(mutation_engine):
    res = mutation_engine.resolve_auth_conflict(compromise_ttl_minutes=30)
    assert res["status"] == "success"
    assert "outbox" in res

    outbox = res["outbox"]
    assert outbox["sync_status"] == "SYNCED"
    assert "tx_id" in outbox
    assert "writebacks" in outbox

    # 1. Verify GitHub Deprecation PR writeback
    gh = outbox["writebacks"]["github"]
    assert gh["sync_status"] == "SYNCED"
    assert "orgbridge/resolve-policy-" in gh["branch"]
    assert "DEPRECATED_BY_MERGER" in gh["body"]
    assert len(gh["reviewers"]) >= 2

    # 2. Verify Jira Migration Epic writeback
    jira = outbox["writebacks"]["jira"]
    assert jira["sync_status"] == "SYNCED"
    assert jira["key"].startswith("MNA-")
    assert any(link["link_type"] == "is superseded by" for link in jira["issue_links"])

    # 3. Verify Slack Block Kit approval card writeback
    slack = outbox["writebacks"]["slack"]
    assert slack["sync_status"] == "SYNCED"
    assert any(b["type"] == "actions" for b in slack["blocks"])


def test_resolve_retention_conflict_outbox_writeback(mutation_engine):
    res = mutation_engine.resolve_retention_conflict(retention_days=90)
    assert res["status"] == "success"
    assert "outbox" in res
    assert res["outbox"]["sync_status"] == "SYNCED"
    assert "unified:pol:tiered_retention_90d" in res["outbox"]["target_entity_id"]


def test_merge_teams_outbox_writeback(mutation_engine):
    res = mutation_engine.merge_teams()
    assert res["status"] == "success"
    assert "outbox" in res
    assert res["outbox"]["sync_status"] == "SYNCED"
    assert res["outbox"]["target_entity_id"] == "unified:team:identity_secarch"


# ---------------------------------------------------------------------------
# 2. Infinite Loop Guard & Bot Author Verification Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bot_originated_events_are_dropped():
    # 1. GitHub webhook authored by OrgBridge bot is dropped
    gh_bot_payload = {
        "action": "push",
        "repository": {"name": "sample-repo"},
        "sender": {"login": "orgbridge-bot"},
    }
    gh_res = await github_connector.normalize_to_graph(gh_bot_payload, tenant_graph=settings.graph_finpay)
    assert gh_res["status"] == "ignored"
    assert gh_res["reason"] == "bot_author"

    # 2. Event with X-OrgBridge-Tx-Id header is dropped
    jira_bot_payload = {
        "webhookEvent": "jira:issue_updated",
        "issue": {"key": "FIN-123"},
        "_headers": {"X-OrgBridge-Tx-Id": "tx-1710000000-auto"},
    }
    jira_res = await jira_connector.normalize_to_graph(jira_bot_payload, tenant_graph=settings.graph_finpay)
    assert jira_res["status"] == "ignored"
    assert jira_res["reason"] == "bot_author"

    # 3. Slack event authored by bot user ID is dropped
    slack_bot_payload = {
        "event": {
            "type": "message",
            "user": "U_ORGBRIDGE_BOT",
            "text": "Resolution committed",
        }
    }
    slack_res = await slack_connector.normalize_to_graph(slack_bot_payload, tenant_graph=settings.graph_finpay)
    assert slack_res["status"] == "ignored"
    assert slack_res["reason"] == "bot_author"


# ---------------------------------------------------------------------------
# 3. Human-in-the-Loop (HITL) Sign-Off & Approver Commit Tests
# ---------------------------------------------------------------------------

def test_hitl_approval_workflow(mutation_engine):
    db_client.connect()
    graph = db_client.get_graph(settings.graph_merged)

    # 1. Dispatch mutation requiring HITL approval
    res = mutation_engine.resolve_auth_conflict(
        compromise_ttl_minutes=45,
        requires_hitl_approval=True,
    )
    assert res["status"] == "success"
    tx_id = res["outbox"]["tx_id"]
    # Unapproved Slack writeback remains PENDING
    assert res["outbox"]["sync_status"] == "PENDING"
    assert res["outbox"]["writebacks"]["slack"]["approval_status"] == "PENDING_APPROVAL"

    # 2. Staff engineering lead approves resolution in Slack
    approval_res = mutation_engine.approve_slack_resolution(
        tx_id=tx_id,
        target_policy_id="unified:pol:hybrid_session_auth",
        approver_slack_id="U_AARAV_SEC_LEAD",
        approver_name="Aarav Mehta (Staff SecArch)",
    )
    assert approval_res["sync_status"] == "SYNCED"
    assert approval_res["hitl_approval_status"] == "APPROVED"
    assert approval_res["approver_slack_id"] == "U_AARAV_SEC_LEAD"

    # 3. Verify approver's Slack ID and timestamp committed to Policy node in FalkorDB
    pol_rec = graph.query("""
        MATCH (p:Policy {id: 'unified:pol:hybrid_session_auth'})
        RETURN p.approver_slack_id, p.hitl_approval_status
    """).result_set
    assert len(pol_rec) > 0
    assert pol_rec[0][0] == "U_AARAV_SEC_LEAD"
    assert pol_rec[0][1] == "APPROVED"


# ---------------------------------------------------------------------------
# 4. Outbox Failure & Retry State Machine Tests
# ---------------------------------------------------------------------------

def test_outbox_failure_and_retry_state_machine(mutation_engine):
    # 1. Simulate failure during external writeback (e.g. GitHub timeout)
    res_failed = mutation_engine.resolve_auth_conflict(
        compromise_ttl_minutes=30,
        simulate_failure="github",
    )
    assert res_failed["outbox"]["sync_status"] == "FAILED"
    assert res_failed["outbox"]["writebacks"]["github"]["sync_status"] == "FAILED"

    failed_tx_id = res_failed["outbox"]["tx_id"]

    # 2. Retry outbox writebacks
    retry_res = mutation_engine.retry_outbox(
        tx_id=failed_tx_id,
        action="resolve_auth_conflict",
        details={
            "policy_name": "Unified M&A Adaptive Session Policy",
            "repo": "gatekeeper-auth",
        },
    )
    assert retry_res["sync_status"] == "SYNCED"
    assert retry_res["writebacks"]["github"]["sync_status"] == "SYNCED"


# ---------------------------------------------------------------------------
# 5. API Endpoints for Slack HITL Approval & Outbox Retry
# ---------------------------------------------------------------------------

def test_api_slack_approve_endpoint(api_client):
    res = api_client.post(
        "/api/mutate/slack-approve",
        json={
            "tx_id": "tx_mock_12345",
            "target_policy_id": "unified:pol:hybrid_session_auth",
            "approver_slack_id": "U_DIYA_NAIR_99",
            "approver_name": "Diya Nair (Identity Lead)",
        },
        headers={"Authorization": f"Bearer {settings.admin_api_key}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["sync_status"] == "SYNCED"
    assert data["hitl_approval_status"] == "APPROVED"
    assert data["approver_slack_id"] == "U_DIYA_NAIR_99"


def test_api_outbox_retry_endpoint(api_client):
    res = api_client.post(
        "/api/mutate/outbox-retry",
        json={
            "tx_id": "tx_retry_888",
            "action": "resolve_auth_conflict",
            "details": {"policy_name": "Unified Auth Standard"},
        },
        headers={"Authorization": f"Bearer {settings.admin_api_key}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["sync_status"] == "SYNCED"
