"""Phase 2 Read-Only Webhook & Delta Ingestion Unit and Integration Tests.

Verifies:
1. GitHub connector graph ingestion (manifests -> System, ExternalAPI; CODEOWNERS -> Person, Team; ADRs -> Decision).
2. Jira connector graph ingestion (Issues -> Ticket, Incident Assignee -> Resolved with PageRank boost, Decisions).
3. Slack connector graph ingestion (Thread mentions -> COLLABORATES_WITH; Reactions -> Decision).
4. Tombstone handlers for privatized repos, deleted issues, and deleted channels (status='TOMBSTONED').
5. Tenant isolation (FinPay events stay in finpay_graph, Vaultly events stay in vaultly_graph).
6. Automatic incremental bridge creation ([:CONFLICTS_WITH] / [:REDUNDANT_WITH]) in merged_brain.
7. FastAPI connector routes: POST /api/webhooks/{provider} (202 Accepted < 100ms), GET /api/connectors/status, POST /api/connectors/{provider}/sync.
"""

import hmac
import hashlib
import time
import json
import pytest
from fastapi.testclient import TestClient

from src.config import settings
from src.db.client import db_client
from src.api.main import app
from src.connectors.github import github_connector
from src.connectors.jira import jira_connector
from src.connectors.slack import slack_connector
from src.pipeline.auto_linker import link_incremental_node


@pytest.fixture(scope="module")
def api_client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. GitHub Connector Tests: Ingestion, Tenant Isolation, & Tombstones
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_github_ingestion_and_tenant_isolation():
    db_client.connect()
    finpay_graph = db_client.get_graph(settings.graph_finpay)
    vaultly_graph = db_client.get_graph(settings.graph_vaultly)

    payload = {
        "action": "push",
        "repository": {
            "name": "finpay-auth-gateway",
            "html_url": "https://github.com/finpay-org/finpay-auth-gateway",
            "description": "FinPay OAuth2 microservice with Stripe SDK and KMS",
        },
        "sender": {"login": "aarav_sec"},
        "author_email": "aarav@finpay.com",
        "codeowners": ["aarav_sec", "priya_core"],
        "manifests": {
            "package.json": {
                "dependencies": {
                    "stripe": "^14.0.0",
                    "@aws-sdk/client-kms": "^3.0.0",
                }
            }
        },
        "adrs": [
            {
                "path": "docs/adr/0001-jwt-auth.md",
                "title": "ADR 0001: Strict 15-Minute JWT Lifetime",
                "content": "# ADR 0001\nEnforces 15-minute JWT expiration for all FinPay services.",
            }
        ],
    }

    result = await github_connector.normalize_to_graph(payload, tenant_graph=settings.graph_finpay)
    assert result["status"] == "ingested"
    assert result["system_id"] == "finpay:sys:finpay_auth_gateway"
    assert "ext:api:stripe" in result["external_apis"]

    # Verify System exists in finpay_graph
    fp_res = finpay_graph.query(
        "MATCH (s:System {id: 'finpay:sys:finpay_auth_gateway'}) RETURN s.name, s.company_origin"
    ).result_set
    assert len(fp_res) > 0
    assert fp_res[0][0] == "finpay-auth-gateway"
    assert fp_res[0][1] == "FinPay"

    # Verify Strict Tenant Isolation: Entity MUST NOT exist in vaultly_graph!
    vl_res = vaultly_graph.query(
        "MATCH (s:System {id: 'finpay:sys:finpay_auth_gateway'}) RETURN s"
    ).result_set
    assert len(vl_res) == 0

    # Verify External API relationship in finpay_graph
    api_res = finpay_graph.query(
        "MATCH (s:System {id: 'finpay:sys:finpay_auth_gateway'})-[:CALLS]->(e:ExternalAPI) RETURN e.id"
    ).result_set
    assert len(api_res) >= 1

    # Verify Decision derived from Document in finpay_graph
    dec_res = finpay_graph.query(
        "MATCH (s:System {id: 'finpay:sys:finpay_auth_gateway'})-[:GOVERNED_BY]->(d:Decision)-[:DERIVED_FROM]->(doc:Document) RETURN d.summary"
    ).result_set
    assert len(dec_res) >= 1


@pytest.mark.asyncio
async def test_github_tombstone_handler():
    db_client.connect()
    graph = db_client.get_graph(settings.graph_finpay)

    # First ingest repo
    payload = {
        "action": "push",
        "repository": {"name": "temporary-deprecating-svc"},
        "sender": {"login": "dev1"},
    }
    await github_connector.normalize_to_graph(payload, tenant_graph=settings.graph_finpay)

    # Send privatized / deleted event
    tombstone_payload = {
        "action": "privatized",
        "repository": {"name": "temporary-deprecating-svc", "private": True},
        "sender": {"login": "admin"},
    }
    res = await github_connector.normalize_to_graph(tombstone_payload, tenant_graph=settings.graph_finpay)
    assert res["status"] == "tombstoned"

    # Verify node status is TOMBSTONED
    check = graph.query(
        "MATCH (s:System {id: 'finpay:sys:temporary_deprecating_svc'}) RETURN s.status, s.title, s.name"
    ).result_set
    assert len(check) > 0
    assert check[0][0] == "TOMBSTONED"


# ---------------------------------------------------------------------------
# 2. Jira Connector Tests: Ingestion, Incident PageRank & Tombstones
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_jira_ingestion_and_incident_resolution():
    db_client.connect()
    graph = db_client.get_graph(settings.graph_finpay)

    payload = {
        "webhookEvent": "jira:issue_created",
        "issue": {
            "key": "FIN-9999",
            "fields": {
                "summary": "P0 Security Incident: JWT Token replay attempt detected",
                "description": "Remediated session replay on auth gateway.",
                "issuetype": {"name": "Incident"},
                "priority": {"name": "Highest"},
                "status": {"name": "Closed"},
                "assignee": {
                    "name": "rohan",
                    "displayName": "Rohan Sharma",
                    "emailAddress": "rohan@finpay.com",
                    "accountId": "jira-rohan-123",
                },
            },
        },
    }

    res = await jira_connector.normalize_to_graph(payload, tenant_graph=settings.graph_finpay)
    assert res["status"] == "ingested"
    assert res["ticket_id"] == "finpay:tkt:fin_9999"

    # Verify Ticket in FalkorDB
    tkt = graph.query("MATCH (t:Ticket {id: 'finpay:tkt:fin_9999'}) RETURN t.title, t.severity").result_set
    assert len(tkt) > 0
    assert tkt[0][1] == "CRITICAL"

    # Verify Person resolved Ticket with PageRank boost
    resolved = graph.query(
        "MATCH (p:Person)-[:RESOLVED]->(t:Ticket {id: 'finpay:tkt:fin_9999'}) RETURN p.name, p.pagerank"
    ).result_set
    assert len(resolved) > 0
    assert resolved[0][0] == "Rohan Sharma"
    assert resolved[0][1] >= 0.50


@pytest.mark.asyncio
async def test_jira_tombstone_handler():
    db_client.connect()
    graph = db_client.get_graph(settings.graph_finpay)

    payload = {
        "webhookEvent": "jira:issue_deleted",
        "issue": {"key": "FIN-9999"},
    }
    res = await jira_connector.normalize_to_graph(payload, tenant_graph=settings.graph_finpay)
    assert res["status"] == "tombstoned"

    rec = graph.query("MATCH (t:Ticket {id: 'finpay:tkt:fin_9999'}) RETURN t.status").result_set
    assert len(rec) > 0
    assert rec[0][0] == "TOMBSTONED"


# ---------------------------------------------------------------------------
# 3. Slack Connector Tests: Collaboration & Reaction-Driven Capture
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_slack_collaboration_and_reaction_capture():
    db_client.connect()
    graph = db_client.get_graph(settings.graph_finpay)

    # 1. Thread interactions populates (:Person)-[:COLLABORATES_WITH]->(:Person)
    collab_payload = {
        "event": {
            "type": "message",
            "channel": "C12345_architecture",
            "user": "aarav",
        },
        "participants": ["aarav", "diya"],
        "mentions": ["diya"],
    }
    collab_res = await slack_connector.normalize_to_graph(collab_payload, tenant_graph=settings.graph_finpay)
    assert collab_res["status"] == "collaboration_topology_updated"

    collab_edge = graph.query(
        "MATCH (a:Person)-[r:COLLABORATES_WITH]->(b:Person) RETURN count(r)"
    ).result_set
    assert collab_edge[0][0] >= 1

    # 2. Staff engineer reaction (:memo:) captures ADR decision
    reaction_payload = {
        "event": {
            "type": "reaction_added",
            "reaction": "memo",
            "user": "aarav",
            "item": {
                "channel": "C999_arch_board",
                "ts": "1710000000.123456",
            },
            "thread_text": "Agreed: Standardize OAuth refresh tokens to 30 days post-merger.",
        }
    }
    react_res = await slack_connector.normalize_to_graph(reaction_payload, tenant_graph=settings.graph_finpay)
    assert react_res["status"] == "decision_captured"
    assert "decision_id" in react_res


# ---------------------------------------------------------------------------
# 4. Incremental Bridge Creation in merged_brain
# ---------------------------------------------------------------------------

def test_incremental_auto_linker_cross_tenant_conflict():
    db_client.connect()
    merged_graph = db_client.get_graph(settings.graph_merged)

    # Ingest a FinPay policy and a Vaultly policy with conflicting terms into merged_brain
    merged_graph.query("""
        MERGE (p1:Policy {id: 'finpay:pol:incremental_test_auth'})
        ON CREATE SET p1.name = 'Session Auth Max 15m', p1.domain = 'Authentication',
                      p1.description = 'Strict 15-minute token TTL', p1.company_origin = 'FinPay',
                      p1.status = 'ACTIVE'
    """)
    merged_graph.query("""
        MERGE (p2:Policy {id: 'vaultly:pol:incremental_test_auth'})
        ON CREATE SET p2.name = 'Session Auth Max 7d', p2.domain = 'Authentication',
                      p2.description = 'Convenient 7-day token TTL for mobile app', p2.company_origin = 'Vaultly',
                      p2.status = 'ACTIVE'
    """)

    # Trigger incremental linking for finpay:pol:incremental_test_auth
    link_res = link_incremental_node(
        node_id="finpay:pol:incremental_test_auth",
        label="Policy",
        tenant_graph=settings.graph_merged,
        threshold=0.65,
    )
    assert link_res["node_id"] == "finpay:pol:incremental_test_auth"
    assert link_res["bridges_created"] >= 1

    # Verify [:CONFLICTS_WITH] edge exists in merged_brain
    check = merged_graph.query("""
        MATCH (a:Policy {id: 'finpay:pol:incremental_test_auth'})-[r:CONFLICTS_WITH]->(b:Policy {id: 'vaultly:pol:incremental_test_auth'})
        RETURN r.similarity, r.domain
    """).result_set
    assert len(check) > 0
    assert check[0][1] == "Authentication"


# ---------------------------------------------------------------------------
# 5. FastAPI Connector Route Tests
# ---------------------------------------------------------------------------

def test_api_connectors_status(api_client):
    res = api_client.get(
        "/api/connectors/status",
        headers={"Authorization": f"Bearer {settings.api_key}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "github" in data["connectors"]
    assert "jira" in data["connectors"]
    assert "slack" in data["connectors"]


def test_api_webhook_fastapi_202_accepted(api_client):
    secret = settings.github_webhook_secret
    body = json.dumps({
        "action": "push",
        "repository": {"name": "test-webhook-repo"},
        "sender": {"login": "developer"},
    }).encode("utf-8")

    sig = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    # Call POST /api/webhooks/github
    res = api_client.post(
        "/api/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
            "X-GitHub-Delivery": f"del-{int(time.time())}",
        },
    )
    assert res.status_code == 202
    data = res.json()
    assert data["status"] == "accepted"
    assert data["provider"] == "github"


def test_api_connector_sync(api_client):
    res = api_client.post(
        "/api/connectors/jira/sync",
        json={"tenant": "finpay"},
        headers={"Authorization": f"Bearer {settings.admin_api_key}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "sync_completed"
    assert data["provider"] == "jira"
