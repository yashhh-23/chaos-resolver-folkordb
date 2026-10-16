"""FastAPI Backend Server for OrgBridge AI (The M&A Chaos Resolver).

Serves the 5 deterministic graph algorithm tools, MCP schemas,
and live visual subgraph payloads for the Next.js War Room dashboard.
"""

from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.config import settings
from src.utils.logger import logger
from src.db.client import db_client
from src.tools.graph_tools import agent_tools, ToolResult, Subgraph
from src.tools.mcp_server import MCP_TOOL_DEFINITIONS, execute_tool

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



class MCPExecuteRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


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

    # Query relationships
    rel_query = """
        MATCH (a)-[r]->(b)
        RETURN a.id, b.id, type(r), properties(r)
        LIMIT 150
    """
    rel_res = g.query(rel_query)
    for row in rel_res.result_set:
        subgraph.add_edge(
            source=row[0],
            target=row[1],
            rel_type=row[2],
            props=row[3] if isinstance(row[3], dict) else {},
        )

    return subgraph


# Live Mutation Endpoints (Phase 5 - Track 03: Keeping Knowledge Current)
@app.post("/api/mutate/resolve-auth-conflict")
def resolve_auth_conflict():
    """Live Mutation: Resolves 15-min vs 7-day token conflict by creating Unified Adaptive Policy."""
    from src.pipeline.mutations import live_mutations
    try:
        return live_mutations.resolve_auth_conflict()
    except Exception as e:
        logger.error(f"Error in resolve_auth_conflict: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mutate/resolve-retention-conflict")
def resolve_retention_conflict():
    """Live Mutation: Resolves 30-day vs 180-day retention conflict via tiered storage standard."""
    from src.pipeline.mutations import live_mutations
    try:
        return live_mutations.resolve_retention_conflict()
    except Exception as e:
        logger.error(f"Error in resolve_retention_conflict: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mutate/merge-teams")
def merge_teams():
    """Live Mutation: Merges SecArch and Identity Growth into Unified Engineering Org."""
    from src.pipeline.mutations import live_mutations
    try:
        return live_mutations.merge_teams()
    except Exception as e:
        logger.error(f"Error in merge_teams: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mutate/reset-demo")
def reset_demo_graph():
    """Resets FalkorDB multigraphs to pristine initial Phase 1/2 state."""
    from src.data.seed import seed_all_graphs
    from src.pipeline.auto_linker import auto_linker_engine
    try:
        logger.info("Resetting demo multigraphs in FalkorDB...")
        seed_all_graphs(clear_first=True)
        auto_linker_engine.run_pipeline(settings.graph_merged)
        return {"status": "success", "message": "FalkorDB multigraphs reset and auto-linked successfully."}
    except Exception as e:
        logger.error(f"Error in reset_demo_graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))

