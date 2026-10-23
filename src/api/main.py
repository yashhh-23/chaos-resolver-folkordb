"""FastAPI Backend Server for OrgBridge AI (The M&A Chaos Resolver).

Serves the 6 deterministic graph algorithm tools, MCP schemas,
Groq Llama-3.3-70B agent with schema-constrained Cypher,
and live visual subgraph payloads for the Next.js War Room dashboard.
"""

import json
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Body, Depends, Query, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from src.config import settings
from src.utils.logger import logger
from src.db.client import db_client
from src.tools.graph_tools import agent_tools, GraphAgentTools, ToolResult, Subgraph, fetch_visualization_subgraph
from src.tools.mcp_server import MCP_TOOL_DEFINITIONS, execute_tool
from src.tools.llm_agent import llm_agent
from src.pipeline.mutations import get_mutation_engine
from src.api.auth import require_read, require_write, require_admin
from src.connectors import github_connector, jira_connector, slack_connector

VALID_GRAPHS = {settings.graph_finpay, settings.graph_vaultly, settings.graph_merged}


def validate_graph(graph_name: Optional[str]) -> str:
    """Validates the target multigraph tenant, defaulting to settings.graph_merged."""
    if not graph_name:
        return settings.graph_merged
    if graph_name not in VALID_GRAPHS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid graph tenant '{graph_name}'. Valid tenants: {sorted(list(VALID_GRAPHS))}",
        )
    return graph_name


def get_tools(graph_name: Optional[str] = None) -> GraphAgentTools:
    """Returns a GraphAgentTools instance bound to the requested tenant or default merged_brain."""
    target = validate_graph(graph_name)
    return GraphAgentTools(graph_name=target)


app = FastAPI(
    title="OrgBridge AI API",
    description="FalkorDB Multi-Tenant M&A Brain & Graph Agent Tools",
    version="0.4.0",
)

# Restrict CORS to known frontend origins (local dev & verified production)
_allowed_origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    # Restrict preview deployments strictly to this project's Vercel deployment naming pattern
    allow_origin_regex=r"^https://(?:falkordb-powered-resolver|frontend-[a-zA-Z0-9]+)-[a-zA-Z0-9_-]*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# Request Models
class ExpertRequest(BaseModel):
    topic: str = Field(..., description="Domain or topic to find expert for", examples=["Authentication"])
    company: str = Field(default="Vaultly", description="Target company", examples=["Vaultly"])
    graph: Optional[str] = Field(default=None, description="Optional target multigraph tenant", examples=["merged_brain"])


class ConflictRequest(BaseModel):
    domain: Optional[str] = Field(default=None, description="Domain to filter conflicts", examples=["Data Retention"])
    graph: Optional[str] = Field(default=None, description="Optional target multigraph tenant", examples=["merged_brain"])


class LineageRequest(BaseModel):
    system_name: str = Field(..., description="Name of the system to trace", examples=["Gatekeeper-Auth"])
    graph: Optional[str] = Field(default=None, description="Optional target multigraph tenant", examples=["merged_brain"])


class WarmIntroRequest(BaseModel):
    person_a: str = Field(..., description="Originating person", examples=["Aarav Mehta"])
    person_b: str = Field(..., description="Target counterpart person", examples=["Diya Nair"])
    graph: Optional[str] = Field(default=None, description="Optional target multigraph tenant", examples=["merged_brain"])


class RedundantRequest(BaseModel):
    graph: Optional[str] = Field(default=None, description="Optional target multigraph tenant", examples=["merged_brain"])


class SilosRequest(BaseModel):
    graph: Optional[str] = Field(default=None, description="Optional target multigraph tenant", examples=["merged_brain"])


class ResolveAuthRequest(BaseModel):
    compromise_ttl_minutes: int = Field(
        default=30,
        ge=5,
        le=10080,
        description="Compromise JWT TTL in minutes (bounds: 5m to 10,080m [7 days])",
        examples=[30],
    )
    confirm_compliance_override: bool = Field(
        default=False,
        description="Explicit confirmation flag required when configuring TTL > 120m due to PCI-DSS/session hijacking risk",
    )
    graph: Optional[str] = Field(default=None, description="Target multigraph tenant to mutate", examples=["merged_brain"])

    @model_validator(mode="after")
    def validate_ttl_compliance(self) -> "ResolveAuthRequest":
        if self.compromise_ttl_minutes > 120 and not self.confirm_compliance_override:
            raise ValueError(
                f"Compromise TTL of {self.compromise_ttl_minutes}m exceeds standard 120m security threshold. "
                f"Long-lived sessions introduce session hijacking and PCI-DSS compliance risks. "
                f"Set 'confirm_compliance_override=True' to confirm this compliance exception."
            )
        return self


class ResolveRetentionRequest(BaseModel):
    retention_days: int = Field(
        default=90,
        ge=30,
        le=3650,
        description="Audit retention period in days (bounds: 30 days to 3,650 days [10 years])",
        examples=[90],
    )
    confirm_compliance_override: bool = Field(
        default=False,
        description="Explicit confirmation flag required when setting retention < 60 days (regulatory audit trail risk) or > 730 days (GDPR data minimization risk)",
    )
    graph: Optional[str] = Field(default=None, description="Target multigraph tenant to mutate", examples=["merged_brain"])

    @model_validator(mode="after")
    def validate_retention_compliance(self) -> "ResolveRetentionRequest":
        if (self.retention_days < 60 or self.retention_days > 730) and not self.confirm_compliance_override:
            risk_desc = "regulatory audit trail gap (< 60 days)" if self.retention_days < 60 else "GDPR data minimization / storage risk (> 730 days)"
            raise ValueError(
                f"Retention duration of {self.retention_days} days carries significant compliance implications ({risk_desc}). "
                f"Set 'confirm_compliance_override=True' to confirm this compliance exception."
            )
        return self


class MergeTeamsRequest(BaseModel):
    team_a_id: str = Field(default="finpay:team:secarch", description="First team to merge", examples=["finpay:team:secarch"])
    team_b_id: str = Field(default="vaultly:team:identity_growth", description="Second team to merge", examples=["vaultly:team:identity_growth"])
    unified_name: str = Field(default="Unified M&A Security & Identity Team", description="Unified joint team name", examples=["Unified M&A Security & Identity Team"])
    graph: Optional[str] = Field(default=None, description="Target multigraph tenant to mutate", examples=["merged_brain"])


class ResetDemoRequest(BaseModel):
    graph: Optional[str] = Field(default=None, description="Optional target multigraph tenant to reseed and link", examples=["merged_brain"])


class MCPExecuteRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    graph: Optional[str] = Field(default=None, description="Optional target multigraph tenant", examples=["merged_brain"])


class ChatRequest(BaseModel):
    prompt: str = Field(..., description="User query or command for the agent", examples=["Who are the experts on Authentication?"])
    graph: Optional[str] = Field(default=None, description="Optional target multigraph tenant", examples=["merged_brain"])



# Endpoints
@app.get("/")
def root():
    """Root endpoint providing service metadata, Swagger docs link, and frontend dashboard link."""
    return {
        "service": "OrgBridge AI Backend (FalkorDB Multi-Tenant Brain)",
        "status": "healthy",
        "documentation": "/docs",
        "health_check": "/api/health",
        "frontend_dashboard": "https://falkordb-powered-resolver.vercel.app",
    }


@app.get("/api/health")
def health_check():
    """System health check and FalkorDB connectivity status."""
    is_connected = db_client.is_connected()
    return {
        "status": "healthy" if is_connected else "degraded",
        "falkordb_connected": is_connected,
        "environment": settings.environment,
        "active_graphs": [settings.graph_finpay, settings.graph_vaultly, settings.graph_merged],
    }


@app.get("/api/mcp/tools")
def get_mcp_tools():
    """Returns available MCP tool definitions for autonomous LLM agents."""
    return {"tools": MCP_TOOL_DEFINITIONS}


@app.post("/api/mcp/execute", response_model=ToolResult, dependencies=[Depends(require_read)])
def run_mcp_tool(req: MCPExecuteRequest):
    """Executes an MCP tool dynamically. Protected by read authentication."""
    try:
        return execute_tool(req.tool_name, req.arguments, graph_name=req.graph)
    except Exception as e:
        logger.error(f"MCP execution error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/tools/find-counterpart-expert", response_model=ToolResult)
def find_counterpart_expert(req: ExpertRequest):
    """Tool 1: Identifies subject-matter expert counterpart using Cypher + PageRank."""
    try:
        tools = get_tools(req.graph)
        return tools.find_counterpart_expert(topic=req.topic, company=req.company)
    except Exception as e:
        logger.error(f"Error in find_counterpart_expert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tools/detect-policy-conflicts", response_model=ToolResult)
def detect_policy_conflicts(req: ConflictRequest):
    """Tool 2: Detects conflicting compliance policies and traces source lineage."""
    try:
        tools = get_tools(req.graph)
        return tools.detect_policy_conflicts(domain=req.domain)
    except Exception as e:
        logger.error(f"Error in detect_policy_conflicts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tools/find-redundant-systems", response_model=ToolResult)
def find_redundant_systems(req: Optional[RedundantRequest] = None):
    """Tool 3: Finds overlapping microservices via hybrid vector + graph similarity."""
    try:
        tools = get_tools(req.graph if req else None)
        return tools.find_redundant_systems()
    except Exception as e:
        logger.error(f"Error in find_redundant_systems: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tools/trace-decision-lineage", response_model=ToolResult)
def trace_decision_lineage(req: LineageRequest):
    """Tool 4: Traces governing decisions, counterpart conflicts, and documentation lineage."""
    try:
        tools = get_tools(req.graph)
        return tools.trace_decision_lineage(system_name=req.system_name)
    except Exception as e:
        logger.error(f"Error in trace_decision_lineage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tools/warm-intro-path", response_model=ToolResult)
def get_warm_intro_path(req: WarmIntroRequest):
    """Tool 5: Computes shortest warm introduction path between engineers across companies."""
    try:
        tools = get_tools(req.graph)
        return tools.get_warm_intro_path(person_a=req.person_a, person_b=req.person_b)
    except Exception as e:
        logger.error(f"Error in get_warm_intro_path: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tools/detect-silos", response_model=ToolResult)
def detect_organizational_silos(req: Optional[SilosRequest] = None):
    """Tool 6: Discovers isolated organizational islands and silos across FinPay and Vaultly (WCC)."""
    try:
        tools = get_tools(req.graph if req else None)
        return tools.detect_organizational_silos()
    except Exception as e:
        logger.error(f"Error in detect_organizational_silos: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat", response_model=ToolResult, dependencies=[Depends(require_read)])
def chat_with_agent(req: ChatRequest):
    """Conversational endpoint powered by Groq Llama-3.3-70B with schema-constrained Cypher and tool fallback."""
    try:
        target_graph = validate_graph(req.graph)
        return llm_agent.chat(user_prompt=req.prompt, graph_name=target_graph)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/graph/subgraph", response_model=Subgraph)
def get_graph_visualization(
    graph: Optional[str] = Query(default=None),
    node_limit: int = Query(default=150, ge=1, le=1000),
    rel_limit: int = Query(default=250, ge=1, le=1000),
    focus_node_id: Optional[str] = Query(default=None),
    focus_hops: int = Query(default=1, ge=1, le=3),
):
    """Returns nodes and edges for visual rendering in Next.js react-force-graph-2d.

    Prioritizes cross-company bridge and conflict relationships, ensuring endpoints
    are always included. Supports focus_node_id and focus_hops for neighborhood exploration.
    """
    target_graph = validate_graph(graph)
    return fetch_visualization_subgraph(
        graph_name=target_graph,
        node_limit=node_limit,
        rel_limit=rel_limit,
        focus_node_id=focus_node_id,
        focus_hops=focus_hops,
    )


@app.get("/api/graph/neighborhood/{node_id:path}", response_model=Subgraph)
def get_node_neighborhood(
    node_id: str,
    graph: Optional[str] = Query(default=None),
    hops: int = Query(default=1, ge=1, le=3),
    rel_limit: int = Query(default=100, ge=1, le=500),
):
    """Returns the subgraph neighborhood around a specific node (by ID) up to the specified hops."""
    target_graph = validate_graph(graph)
    return fetch_visualization_subgraph(
        graph_name=target_graph,
        node_limit=200,
        rel_limit=rel_limit,
        focus_node_id=node_id,
        focus_hops=hops,
    )


# Live Mutation Endpoints (Phase 5 - Track 03: Keeping Knowledge Current)
@app.post("/api/mutate/resolve-auth-conflict", dependencies=[Depends(require_write)])
def resolve_auth_conflict(req: Optional[ResolveAuthRequest] = Body(default=None)):
    """Live Mutation: Resolves 15-min vs 7-day token conflict on the targeted graph tenant. Requires 'write' role."""
    try:
        target_graph = validate_graph(req.graph if req else None)
        engine = get_mutation_engine(target_graph)
        ttl = req.compromise_ttl_minutes if req else 30
        override = req.confirm_compliance_override if req else False
        return engine.resolve_auth_conflict(compromise_ttl_minutes=ttl, confirm_compliance_override=override)
    except ValueError as ve:
        logger.warning(f"Validation error in resolve_auth_conflict: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in resolve_auth_conflict: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mutate/resolve-retention-conflict", dependencies=[Depends(require_write)])
def resolve_retention_conflict(req: Optional[ResolveRetentionRequest] = Body(default=None)):
    """Live Mutation: Resolves 30-day vs 180-day retention conflict on the targeted graph tenant. Requires 'write' role."""
    try:
        target_graph = validate_graph(req.graph if req else None)
        engine = get_mutation_engine(target_graph)
        days = req.retention_days if req else 90
        override = req.confirm_compliance_override if req else False
        return engine.resolve_retention_conflict(retention_days=days, confirm_compliance_override=override)
    except ValueError as ve:
        logger.warning(f"Validation error in resolve_retention_conflict: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in resolve_retention_conflict: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mutate/merge-teams", dependencies=[Depends(require_write)])
def merge_teams(req: Optional[MergeTeamsRequest] = Body(default=None)):
    """Live Mutation: Merges SecArch and Identity Growth on targeted tenant. Requires 'write' role."""
    try:
        target_graph = validate_graph(req.graph if req else None)
        engine = get_mutation_engine(target_graph)
        if req:
            return engine.merge_teams(
                team_a_id=req.team_a_id,
                team_b_id=req.team_b_id,
                unified_name=req.unified_name,
            )
        return engine.merge_teams()
    except ValueError as ve:
        logger.warning(f"Validation error in merge_teams: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in merge_teams: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mutate/reset-demo", dependencies=[Depends(require_admin)])
def reset_demo_graph(req: Optional[ResetDemoRequest] = Body(default=None)):
    """Resets FalkorDB multigraphs to pristine initial Phase 1/2 state. Protected separately by 'admin' role."""
    try:
        target_graph = validate_graph(req.graph if req else None)
        engine = get_mutation_engine(target_graph)
        return engine.reset_demo(include_subgraph=True)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in reset_demo_graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SlackApproveRequest(BaseModel):
    tx_id: str = Field(..., description="Transaction ID of pending Outbox mutation", examples=["tx_1710000000_abc123"])
    target_policy_id: str = Field(..., description="Policy ID to sign off", examples=["unified:pol:hybrid_session_auth"])
    approver_slack_id: str = Field(default="U_STAFF_LEAD_01", description="Slack user ID of approving engineer")
    approver_name: Optional[str] = Field(default="Aarav Mehta (Staff SecArch)", description="Name of approver")
    graph: Optional[str] = Field(default=None, description="Target graph tenant")


class OutboxRetryRequest(BaseModel):
    tx_id: str = Field(..., description="Transaction ID to retry")
    action: str = Field(..., description="Mutation action name")
    details: Dict[str, Any] = Field(default_factory=dict, description="Writeback payload details")
    graph: Optional[str] = Field(default=None, description="Target graph tenant")


@app.post("/api/mutate/slack-approve", dependencies=[Depends(require_write)])
def approve_slack_mutation(req: SlackApproveRequest):
    """Processes interactive Slack Block Kit HITL approval and commits approver to Policy node."""
    try:
        target_graph = validate_graph(req.graph)
        engine = get_mutation_engine(target_graph)
        return engine.approve_slack_resolution(
            tx_id=req.tx_id,
            target_policy_id=req.target_policy_id,
            approver_slack_id=req.approver_slack_id,
            approver_name=req.approver_name or "Aarav Mehta (Staff SecArch)",
        )
    except Exception as e:
        logger.error(f"Error in approve_slack_mutation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mutate/outbox-retry", dependencies=[Depends(require_write)])
def retry_outbox_transaction(req: OutboxRetryRequest):
    """Retries a failed Outbox transaction across GitHub, Jira, or Slack."""
    try:
        target_graph = validate_graph(req.graph)
        engine = get_mutation_engine(target_graph)
        return engine.retry_outbox(
            tx_id=req.tx_id,
            action=req.action,
            details=req.details,
        )
    except Exception as e:
        logger.error(f"Error in retry_outbox_transaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Live Enterprise Connectors & Webhook Routes (GitHub, Jira, Slack)
# ---------------------------------------------------------------------------

CONNECTORS: Dict[str, Any] = {
    "github": github_connector,
    "jira": jira_connector,
    "slack": slack_connector,
}


def resolve_tenant_graph(
    provider: str,
    payload: Dict[str, Any],
    query_tenant: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> str:
    """Resolves target isolated tenant graph (finpay_graph or vaultly_graph)."""
    if query_tenant:
        return settings.graph_vaultly if "vault" in query_tenant.lower() else settings.graph_finpay

    if headers:
        normalized_headers = {k.lower(): v for k, v in headers.items()}
        tenant_header = normalized_headers.get("x-tenant-id") or normalized_headers.get("x-company")
        if tenant_header:
            return settings.graph_vaultly if "vault" in tenant_header.lower() else settings.graph_finpay

    # Check payload identifiers
    payload_str = json.dumps(payload).lower()
    if "vaultly" in payload_str or "vaultly-io" in payload_str:
        return settings.graph_vaultly

    return settings.graph_finpay


class SyncRequest(BaseModel):
    tenant: Optional[str] = Field(default="finpay", description="Target tenant: finpay or vaultly")
    cursor: Optional[str] = Field(default=None, description="Optional checkpoint cursor")


@app.post("/api/webhooks/{provider}", status_code=202)
async def handle_provider_webhook(
    provider: str,
    request: Request,
    background_tasks: BackgroundTasks,
    tenant: Optional[str] = Query(default=None),
):
    """Zero-trust ingestion endpoint for live GitHub, Jira, and Slack events.

    Enforces constant-time cryptographic HMAC verification and 5-minute replay tolerance,
    acknowledging with 202 Accepted in <100ms before processing normalization in background.
    """
    prov = provider.lower()
    if prov not in CONNECTORS:
        raise HTTPException(
            status_code=404,
            detail=f"Unsupported provider '{provider}'. Supported providers: {list(CONNECTORS.keys())}",
        )

    connector = CONNECTORS[prov]

    # 1. Constant-time cryptographic HMAC & replay window check
    raw_body = await connector.verify_signature(request)
    if not raw_body:
        return {"status": "duplicate_ignored", "provider": prov}

    # 2. Parse payload
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Malformed JSON payload: {e}")

    # Slack Events API URL verification challenge handshake (returns HTTP 200)
    if prov == "slack" and payload.get("type") == "url_verification":
        return JSONResponse(content={"challenge": payload.get("challenge")}, status_code=200)

    # Attach raw headers for bot loop detection
    payload["_headers"] = dict(request.headers)

    # 3. Resolve target isolated tenant graph
    target_graph = resolve_tenant_graph(
        provider=prov,
        payload=payload,
        query_tenant=tenant,
        headers=dict(request.headers),
    )

    # 4. Enqueue to async background worker (<100ms response time)
    background_tasks.add_task(connector.normalize_to_graph, payload, target_graph)

    return {
        "status": "accepted",
        "provider": prov,
        "tenant_graph": target_graph,
        "message": "Webhook authenticated and enqueued for async ingestion.",
    }


@app.get("/api/connectors/status", dependencies=[Depends(require_read)])
def get_connectors_status():
    """Returns real-time connection status and tenant mappings for all enterprise connectors."""
    return {
        "status": "healthy",
        "tenants": settings.tenant_org_mappings,
        "connectors": {
            "github": {
                "name": "GitHub App",
                "configured": True,
                "auth_model": "GitHub App RS256 JWT / Installation Token",
                "webhook_secret_set": bool(settings.github_webhook_secret),
                "target_orgs": list(settings.tenant_org_mappings.keys()),
            },
            "jira": {
                "name": "Atlassian Jira",
                "configured": True,
                "auth_model": "Atlassian OAuth 2.0 (3LO)",
                "webhook_secret_set": bool(settings.jira_webhook_secret),
                "jql_checkpoint": 'updated >= "-15m" ORDER BY updated ASC',
            },
            "slack": {
                "name": "Slack Events API",
                "configured": True,
                "auth_model": "Slack OAuth v2 (granular bot scopes)",
                "signing_secret_set": bool(settings.slack_signing_secret),
                "decision_reactions": [":memo:", ":white_check_mark:"],
            },
        },
    }


@app.post("/api/connectors/{provider}/sync", dependencies=[Depends(require_write)])
async def trigger_connector_sync(
    provider: str,
    req: Optional[SyncRequest] = Body(default=None),
):
    """Triggers delta polling / backfill for a connector provider."""
    prov = provider.lower()
    if prov not in CONNECTORS:
        raise HTTPException(
            status_code=404,
            detail=f"Unsupported provider '{provider}'. Supported providers: {list(CONNECTORS.keys())}",
        )

    connector = CONNECTORS[prov]
    tenant_req = req.tenant if req else "finpay"
    target_graph = settings.graph_vaultly if "vault" in tenant_req.lower() else settings.graph_finpay
    cursor = req.cursor if req else None

    result = await connector.poll_delta(tenant_graph=target_graph, cursor=cursor)
    return {
        "status": "sync_completed",
        "provider": prov,
        "tenant_graph": target_graph,
        "result": result,
    }

