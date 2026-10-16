"""FastAPI Backend Server for OrgBridge AI (The M&A Chaos Resolver).

Serves the 6 deterministic graph algorithm tools, MCP schemas,
Groq Llama-3.3-70B agent with schema-constrained Cypher,
and live visual subgraph payloads for the Next.js War Room dashboard.
"""

from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.config import settings
from src.utils.logger import logger
from src.db.client import db_client
from src.tools.graph_tools import agent_tools, ToolResult, Subgraph
from src.tools.mcp_server import MCP_TOOL_DEFINITIONS, execute_tool
from src.tools.llm_agent import llm_agent


app = FastAPI(
    title="OrgBridge AI API",
    description="FalkorDB Multi-Tenant M&A Brain & Graph Agent Tools",
    version="0.3.0",
)

# Enable CORS for Next.js frontend (local dev & production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request Models
class ExpertRequest(BaseModel):
    topic: str = Field(..., description="Domain or topic to find expert for", examples=["Authentication"])
    company: str = Field(default="Vaultly", description="Target company", examples=["Vaultly"])


class ConflictRequest(BaseModel):
    domain: Optional[str] = Field(default=None, description="Domain to filter conflicts", examples=["Data Retention"])


class LineageRequest(BaseModel):
    system_name: str = Field(..., description="Name of the system to trace", examples=["Gatekeeper-Auth"])


class WarmIntroRequest(BaseModel):
    person_a: str = Field(..., description="Originating person", examples=["Aarav Mehta"])
    person_b: str = Field(..., description="Target counterpart person", examples=["Diya Nair"])


class ResolveAuthRequest(BaseModel):
    compromise_ttl_minutes: int = Field(default=30, description="Compromise JWT TTL in minutes", examples=[30])


class ResolveRetentionRequest(BaseModel):
    retention_days: int = Field(default=90, description="Audit retention period in days", examples=[90])


class MergeTeamsRequest(BaseModel):
    team_a_id: str = Field(default="finpay:team:secarch", description="First team to merge", examples=["finpay:team:secarch"])
    team_b_id: str = Field(default="vaultly:team:identity_growth", description="Second team to merge", examples=["vaultly:team:identity_growth"])
    unified_name: str = Field(default="Unified M&A Security & Identity Team", description="Unified joint team name", examples=["Unified M&A Security & Identity Team"])


class MCPExecuteRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    prompt: str = Field(..., description="User query or command for the agent", examples=["Who are the experts on Authentication?"])
    graph: Optional[str] = Field(default=None, description="Optional target multigraph tenant", examples=["merged_brain"])



# Endpoints
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


@app.post("/api/mcp/execute", response_model=ToolResult)
def run_mcp_tool(req: MCPExecuteRequest):
    """Executes an MCP tool dynamically."""
    try:
        return execute_tool(req.tool_name, req.arguments)
    except Exception as e:
        logger.error(f"MCP execution error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/tools/find-counterpart-expert", response_model=ToolResult)
def find_counterpart_expert(req: ExpertRequest):
    """Tool 1: Identifies subject-matter expert counterpart using Cypher + PageRank."""
    try:
        return agent_tools.find_counterpart_expert(topic=req.topic, company=req.company)
    except Exception as e:
        logger.error(f"Error in find_counterpart_expert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tools/detect-policy-conflicts", response_model=ToolResult)
def detect_policy_conflicts(req: ConflictRequest):
    """Tool 2: Detects conflicting compliance policies and traces source lineage."""
    try:
        return agent_tools.detect_policy_conflicts(domain=req.domain)
    except Exception as e:
        logger.error(f"Error in detect_policy_conflicts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tools/find-redundant-systems", response_model=ToolResult)
def find_redundant_systems():
    """Tool 3: Finds overlapping microservices via hybrid vector + graph similarity."""
    try:
        return agent_tools.find_redundant_systems()
    except Exception as e:
        logger.error(f"Error in find_redundant_systems: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tools/trace-decision-lineage", response_model=ToolResult)
def trace_decision_lineage(req: LineageRequest):
    """Tool 4: Traces governing decisions, counterpart conflicts, and documentation lineage."""
    try:
        return agent_tools.trace_decision_lineage(system_name=req.system_name)
    except Exception as e:
        logger.error(f"Error in trace_decision_lineage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tools/warm-intro-path", response_model=ToolResult)
def get_warm_intro_path(req: WarmIntroRequest):
    """Tool 5: Computes shortest warm introduction path between engineers across companies."""
    try:
        return agent_tools.get_warm_intro_path(person_a=req.person_a, person_b=req.person_b)
    except Exception as e:
        logger.error(f"Error in get_warm_intro_path: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tools/detect-silos", response_model=ToolResult)
def detect_organizational_silos():
    """Tool 6: Discovers isolated organizational islands and silos across FinPay and Vaultly (WCC)."""
    try:
        return agent_tools.detect_organizational_silos()
    except Exception as e:
        logger.error(f"Error in detect_organizational_silos: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat", response_model=ToolResult)
def chat_with_agent(req: ChatRequest):
    """Conversational endpoint powered by Groq Llama-3.3-70B with schema-constrained Cypher and tool fallback."""
    try:
        return llm_agent.chat(user_prompt=req.prompt, graph_name=req.graph)
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/graph/subgraph", response_model=Subgraph)
def get_graph_visualization(graph: Optional[str] = None):
    """Returns nodes and edges for visual rendering in Next.js react-force-graph-2d."""
    target_graph = graph or settings.graph_merged
    g = db_client.get_graph(target_graph)
    subgraph = Subgraph()

    # Query nodes
    node_query = """
        MATCH (n)
        RETURN n.id as id,
               coalesce(n.name, n.title, n.summary, n.id) as display_name,
               labels(n)[0] as label,
               coalesce(n.company_origin, 'External') as company,
               properties(n) as props
        LIMIT 100
    """
    node_res = g.query(node_query)
    for row in node_res.result_set:
        subgraph.add_node(
            node_id=row[0],
            name=row[1],
            label=row[2],
            company=row[3],
            props=row[4] if isinstance(row[4], dict) else {},
        )

    # Query relationships (guaranteeing both source and target exist in node set)
    valid_node_ids = {n.id for n in subgraph.nodes}
    rel_query = """
        MATCH (a)-[r]->(b)
        RETURN a.id, b.id, type(r), properties(r)
        LIMIT 150
    """
    rel_res = g.query(rel_query)
    for row in rel_res.result_set:
        if row[0] in valid_node_ids and row[1] in valid_node_ids:
            subgraph.add_edge(
                source=row[0],
                target=row[1],
                rel_type=row[2],
                props=row[3] if isinstance(row[3], dict) else {},
            )

    return subgraph


# Live Mutation Endpoints (Phase 5 - Track 03: Keeping Knowledge Current)
@app.post("/api/mutate/resolve-auth-conflict")
def resolve_auth_conflict(req: Optional[ResolveAuthRequest] = Body(default=None)):
    """Live Mutation: Resolves 15-min vs 7-day token conflict by creating Unified Adaptive Policy."""
    from src.pipeline.mutations import live_mutations
    try:
        ttl = req.compromise_ttl_minutes if req else 30
        return live_mutations.resolve_auth_conflict(compromise_ttl_minutes=ttl)
    except Exception as e:
        logger.error(f"Error in resolve_auth_conflict: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mutate/resolve-retention-conflict")
def resolve_retention_conflict(req: Optional[ResolveRetentionRequest] = Body(default=None)):
    """Live Mutation: Resolves 30-day vs 180-day retention conflict via tiered storage standard."""
    from src.pipeline.mutations import live_mutations
    try:
        days = req.retention_days if req else 90
        return live_mutations.resolve_retention_conflict(retention_days=days)
    except Exception as e:
        logger.error(f"Error in resolve_retention_conflict: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mutate/merge-teams")
def merge_teams(req: Optional[MergeTeamsRequest] = Body(default=None)):
    """Live Mutation: Merges SecArch and Identity Growth into Unified Engineering Org."""
    from src.pipeline.mutations import live_mutations
    try:
        if req:
            return live_mutations.merge_teams(
                team_a_id=req.team_a_id,
                team_b_id=req.team_b_id,
                unified_name=req.unified_name,
            )
        return live_mutations.merge_teams()
    except Exception as e:
        logger.error(f"Error in merge_teams: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mutate/reset-demo")
def reset_demo_graph():
    """Resets FalkorDB multigraphs to pristine initial Phase 1/2 state."""
    from src.pipeline.mutations import live_mutations
    try:
        return live_mutations.reset_demo(include_subgraph=True)
    except Exception as e:
        logger.error(f"Error in reset_demo_graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))

