# The M&A Chaos Resolver (OrgBridge AI)

> **FalkorDB Hackathon (Track 03: Company Brain)**  
> Turning M&A chaos into deterministic knowledge using FalkorDB's multigraph tenancy, bounded graph path traversals, SME influence ranking, and hybrid vector entity resolution.

---

## 🚀 Live Deployments

- **Live War Room Dashboard**: [https://falkordb-powered-resolver.vercel.app](https://falkordb-powered-resolver.vercel.app)
- **Live Backend API**: [https://orgbridge-ai-backend.onrender.com](https://orgbridge-ai-backend.onrender.com)
- **Interactive Swagger Docs**: [https://orgbridge-ai-backend.onrender.com/docs](https://orgbridge-ai-backend.onrender.com/docs)
- **Backend Health Check**: [https://orgbridge-ai-backend.onrender.com/api/health](https://orgbridge-ai-backend.onrender.com/api/health)

---

## Architecture & System Highlights

During an M&A (e.g., FinPay acquiring Vaultly), organizations face duplicate microservices, conflicting compliance policies, fractured org structures, and tribal knowledge silos. Flat vector RAG fails here because it cannot reason across tenants, trace governance lineages, or evaluate bounded graph paths.

OrgBridge AI leverages **FalkorDB** as the central brain of the system across four core capabilities:
1. **Multigraph Tenancy**: Physical graph isolation (`finpay_graph` for Company A, `vaultly_graph` for Company B) and an integrated layer (`merged_brain`) for cross-company entity resolution.
2. **Hybrid Graph + Vector Entity Resolution**: Identifies redundant systems and policy contradictions with shared external dependencies (`ExternalAPI` like UIDAI Aadhaar, Stripe, AWS KMS).
3. **Graph-Powered Agent Tools**: SME influence ranking (evaluating stored PageRank centrality properties alongside authored RFCs & resolved incidents) and bounded path traversal (`[*1..4]`) for warm introductions across company borders.
4. **Decision & Policy Conflict Lineage**: Explicit `[:CONFLICTS_WITH]` and `[:DERIVED_FROM]` edges tracing rules directly back to source Slack threads, Jira tickets, and RFC documents.
5. **Real-Time Knowledge Currency (Track 03)**: Live transactional Cypher `MERGE`, `SET`, and edge relinking engine that dynamically mutates the graph as leadership and architects resolve conflicts.

---

## Project Structure

```
chaos-resolver-folkordb/
├── docker-compose.yml              # Complete 3-tier local stack orchestration (FalkorDB + FastAPI + Next.js)
├── Dockerfile                      # Production Dockerfile for FastAPI backend (Python 3.11-slim)
├── .dockerignore                   # Docker build context optimizations
├── .env.example                    # Environment variable template (local Docker or FalkorDB Cloud)
├── requirements.txt                # Python backend dependencies
├── artifacts/                      # Generated ingestion artifacts
│   ├── cypher/                     # Exported runnable Cypher scripts
│   │   ├── finpay_graph.cypher     # FinPay isolated graph (69 statements)
│   │   ├── vaultly_graph.cypher    # Vaultly isolated graph (70 statements)
│   │   └── merged_brain.cypher     # Unified brain with bridge edges (129 statements)
│   └── dataset.json                # Structured JSON representation
├── src/
│   ├── config.py                   # Centralized Pydantic settings & environment configuration
│   ├── db/
│   │   └── client.py               # FalkorDB client with index manager & query sanitizer
│   ├── schema/
│   │   ├── models.py               # Strict Pydantic models (Person, Team, System, Document, etc.)
│   │   └── cypher_schema.py        # Schema labels, relationships, indexing, & Cypher generators
│   ├── embeddings/
│   │   └── service.py              # Normalized 384-dim semantic embedding service (Local & OpenAI)
│   ├── pipeline/
│   │   ├── vector_index.py         # FalkorDB native vector indexing (db.idx.vector) & embedding population
│   │   ├── auto_linker.py          # Hybrid Vector + Graph Auto-Linker Engine (threshold >= 0.82)
│   │   └── mutations.py            # Live Graph Mutation Engine (Track 03 real-time knowledge currency)
│   ├── data/
│   │   ├── synthetic_data.py       # Realistic FinPay + Vaultly M&A dilemma dataset
│   │   ├── builder.py              # Multigraph Cypher statement compiler & exporter
│   │   └── seed.py                 # CLI seeder for FalkorDB & artifact generator
│   ├── tools/
│   │   ├── graph_tools.py          # 6 Deterministic agent tools returning text + visual Subgraph JSON
│   │   ├── llm_agent.py            # Groq Llama-3.3-70B agent + Schema-Constrained Cypher with offline fallback
│   │   └── mcp_server.py           # Model Context Protocol (MCP) tool schema & dispatcher
│   ├── api/
│   │   └── main.py                 # FastAPI backend server with CORS, visual subgraph, /api/chat & mutation endpoints
│   ├── cli.py                      # Interactive FalkorDB REPL, CLI tool runner, and uvicorn launcher
│   └── utils/
│       └── logger.py               # Standardized application logging
├── frontend/                       # Next.js 14 App Router War-Room Dashboard
│   ├── Dockerfile                  # Multi-stage production Dockerfile for Next.js (Node 20-alpine)
│   ├── .dockerignore               # Frontend Docker build exclusions
│   ├── app/page.tsx                # Split-screen agent chat & real-time canvas with draggable resizer splitter
│   ├── components/GraphCanvas.tsx  # Force-directed 2D graph with ResizeObserver, zoom/fit/fullscreen controls
│   ├── components/ChatPanel.tsx    # Agent chat, thinking drawer, crisis prompts & live mutation action bar
│   └── components/NodeInspectorModal.tsx # Node attribute inspector drawer
└── tests/
    ├── test_schema_and_dataset.py  # Schema, edge integrity, collision guards (9 tests)
    ├── test_auto_linker.py         # Vector embeddings & auto-linker resolution (5 tests)
    ├── test_agent_tools.py         # Agent tools, MCP schema, WCC, /api/chat & FastAPI endpoints (10 tests)
    └── test_live_mutations.py      # Live graph mutations, Cypher MERGE/SET updates (4 tests)
```

---

## Graph Schema Specification

### Node Labels
- `(:Person)`: `id`, `name`, `role`, `department`, `email`, `pagerank`, `company_origin`
- `(:Team)`: `id`, `name`, `charter`, `company_origin`
- `(:System)`: `id`, `name`, `tech`, `domain`, `description`, `tier`, `repo`, `company_origin`
- `(:Document)`: `id`, `title`, `doc_type` (RFC, Postmortem, Architecture), `url`, `excerpt`, `author_id`, `company_origin`
- `(:Ticket)`: `id`, `title`, `ticket_type`, `severity`, `status`, `resolved_by_id`, `affects_system_id`, `external_id`, `company_origin`
- `(:Decision)`: `id`, `summary`, `date`, `effective_date`, `authority_level`, `status` (ACTIVE/DEPRECATED/UNDER_REVIEW), `source`, `company_origin`
- `(:Policy)`: `id`, `name`, `domain`, `description`, `effective_date`, `authority_level`, `status`, `source`, `company_origin`
- `(:ExternalAPI)`: `id`, `name`, `category`, `provider`, `company_origin`

### Relationship Types
- **Internal Lineage:**
  - `(:Person)-[:MEMBER_OF]->(:Team)`
  - `(:Person|:Team)-[:OWNS]->(:System)`
  - `(:Person)-[:AUTHORED]->(:Document)`
  - `(:Person)-[:RESOLVED]->(:Ticket)`
  - `(:Ticket)-[:AFFECTS]->(:System)`
  - `(:System)-[:GOVERNED_BY]->(:Decision|:Policy)`
  - `(:System)-[:DEPENDS_ON]->(:System)`
  - `(:System)-[:CALLS]->(:ExternalAPI)`
  - `(:Decision)-[:DERIVED_FROM]->(:Document|:Ticket)`
  - `(:Policy)-[:DERIVED_FROM]->(:Document)`
- **M&A Bridge Relationships (`merged_brain`):**
  - `(:System)-[:REDUNDANT_WITH {similarity: float, reason: str}]->(:System)`
  - `(:Decision)-[:CONFLICTS_WITH {severity: str, domain: str, reason: str}]->(:Decision)`
  - `(:Policy)-[:CONFLICTS_WITH {severity: str, domain: str, reason: str}]->(:Policy)`

---

## Edge Cases Handled

1. **Entity Collision (Same Name, Different Person/Service):**
   - Namespaced node IDs (`finpay:person:rahul_s` vs `vaultly:person:rahul_s`) and mandatory `company_origin` property prevent `MERGE` statements from collapsing distinct people or services.
2. **Terminology Mismatch (Different Name, Same Concept):**
   - e.g. `Customer-KYC-Service` (FinPay) vs `User-Onboarding-Verification` (Vaultly). Connected through shared external dependency `(:ExternalAPI {id: 'ext:api:uidai_aadhaar'})` and tagged with `[:REDUNDANT_WITH {similarity: 0.99}]`.
3. **Policy Contradictions & Temporal Precedence:**
   - Evaluates `effective_date`, `authority_level`, and `status`. E.g., FinPay's 15-minute JWT expiration (`finpay:dec:jwt_15m`) directly conflicts with Vaultly's 7-day persistent mobile session tokens (`vaultly:dec:session_7d`).
4. **LLM Cypher Hallucination & Infinite Traversal Safeguard:**
   - Parameterized queries with a `sanitize_cypher_query` guard and `validate_readonly_cypher` that automatically rewrites unbounded variable paths `[*]` to `[*1..4]`, enforces read-only query clauses, and guarantees a `LIMIT 25` clause.
5. **Three-Layer Domain Guardrails (Out-of-Scope Protection):**
   - Strictly confines the conversational agent to the M&A enterprise graph domain (FalkorDB people, teams, systems, policies, decisions).
   - **Layer 1 (Pre-flight keyword gate)**: Zero-cost classification blocks off-topic queries (e.g. general code assistance like Java/Python, recipes, weather, general trivia) immediately with a canonical domain guidance response without incurring LLM inference costs or hallucination risks.
   - **Layer 2 (Hardened System Prompt)**: Explicit mandatory domain boundary instructions telling the LLM to refuse off-topic questions.
   - **Layer 3 (Post-flight Intercept)**: Validates direct ungrounded text answers to prevent jailbreaks or ungrounded responses.
   - **Fallback Gate**: Even when operating in offline deterministic mode, the scope check guarantees general out-of-scope prompts are safely rejected.
6. **Memory & Rate Limit Protection:**
   - Node payloads store concise 2–3 sentence excerpts instead of bloating graph memory with raw unstructured documents.

---

## Running the Project with Docker (Full Local Stack)

The project includes an executable `docker-compose.yml` that orchestrates all 3 tiers with a single command:
- **`falkordb`**: Official `falkordb/falkordb:latest` on port `6379` with health checks and persistent volume
- **`backend`**: FastAPI backend on port `8000` with automated health recovery and Groq agent support
- **`frontend`**: Next.js 14 War Room dashboard on port `3000` with real-time Force Graph canvas

### 1. Start All Services
```bash
docker compose up --build -d
```

### 2. Verify Container Health
```bash
docker ps
```
You will see 3 running containers:
- `orgbridge-frontend` (`0.0.0.0:3000->3000`)
- `orgbridge-backend` (`0.0.0.0:8000->8000`)
- `falkordb-m-and-a` (`0.0.0.0:6379->6379`, healthy)

### 3. Check Backend Health
```bash
curl http://localhost:8000/api/health
```
Response:
```json
{"status":"healthy","falkordb_connected":true,"environment":"development","active_graphs":["finpay_graph","vaultly_graph","merged_brain"]}
```

### 4. Access the War Room Dashboard
Open your browser at:
- **http://localhost:3000**

### 5. Stop All Services
```bash
docker compose down
```

---

## Local Development (Without Docker)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

### 2. Configure Environment
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Set your FalkorDB credentials (local `localhost:6379` or FalkorDB Cloud) and `GROQ_API_KEY`.

### 3. Generate Artifacts & Seed Database
Export Cypher scripts and JSON without requiring an active database:
```bash
python -m src.data.seed --export-only
```
Seed all 3 graphs (`finpay_graph`, `vaultly_graph`, `merged_brain`) to FalkorDB:
```bash
python -m src.data.seed --clear --verify
```

### 4. Run Phase 2 M&A Auto-Linker Engine
Embeds nodes using 384-dimensional dense vectors, indexes them in FalkorDB, and links cross-company redundancies (`[:REDUNDANT_WITH]`) and contradictions (`[:CONFLICTS_WITH]`) where similarity >= 0.82:
```bash
python -m src.pipeline.auto_linker --graph merged_brain --threshold 0.82
```
Or run interactively inside the CLI:
```bash
python -m src.cli auto-link --graph merged_brain
```

### 5. Run Phase 3 Deterministic Agent Tools (CLI / REST / MCP)
Execute any of the 6 core tools with human-readable evidence and visual Subgraph JSON:
```bash
# 1. SME Expert Discovery (PageRank property + authored RFCs)
python -m src.cli tool find-expert --topic "Authentication" --company Vaultly

# 2. Policy & Compliance Conflict Detection
python -m src.cli tool conflicts --domain "Data Retention"

# 3. Redundant Microservices Clusters
python -m src.cli tool redundant

# 4. Decision Lineage & Conflict Tracing
python -m src.cli tool lineage --system "Gatekeeper-Auth"

# 5. Warm Introduction Bounded Path Traversal ([*1..4])
python -m src.cli tool warm-intro --person-a "Aarav Mehta" --person-b "Diya Nair"

# 6. Organizational Silos & Island Discovery (Weakly Connected Components)
python -m src.cli tool silos

# Conversational Agent: Groq Llama-3.3-70B with Schema-Constrained Cypher & Offline Fallback
curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{"prompt": "Show me disconnected organizational silos"}'
```

### 6. Launch FastAPI REST Server
```bash
python -m src.cli serve --port 8000
```
Interactive Swagger API documentation will be available at:  
- **http://localhost:8000/docs**

### 7. Launch Next.js "War Room" Dashboard (Phase 4)
In a separate terminal:
```bash
npm run dev --prefix frontend
```
Open your browser at:  
- **http://localhost:3000**

#### Dashboard UI Features:
- **Tenant Selector Pill**: Switch live views between `FinPay (Isolated)`, `Vaultly (Isolated)`, and `Merged Brain` (paired with an SVG Brain icon).
- **Draggable Resizer Splitter**: Interactive draggable handle between the Chatbot panel and Graph canvas with mouse tracking (`280px` min up to `75%` viewport width) and fluid `ResizeObserver` re-rendering.
- **Floating Canvas Controls**:
  - **Zoom In (`+`)**: Smooth animated zoom scaling ($\times 1.35$)
  - **Zoom Out (`-`)**: Smooth animated zoom scaling ($\times 0.70$)
  - **Fit View (`RotateCcw`)**: Calculates the node bounding box and centers all entities
  - **Fullscreen Toggle (`Maximize2` / `Minimize2`)**: Expands the graph to full 100% canvas width with one-click restoration
  - **Subgraph Isolation (`Layers`)**: Toggle to isolate and focus only on tool-traversed paths
- **Autonomous Agent Chat**:
  - **Expandable "Thinking Process" Drawer**: Separates internal Cypher logic and synthesis steps from clean user-facing answers
  - **Severity Badges**: Color-coded badges for `[CRITICAL]`, `[HIGH]`, `[MEDIUM]`, and `[LOW]` conflict levels
  - **One-Click M&A Crisis Prompts**: Instant triggers for SME expert lookup, policy conflicts, redundant systems, and warm intros
  - **Live Mutation Action Bar**: Direct trigger for transactional graph updates
- **Right Panel Canvas**: Interactive `react-force-graph-2d` live canvas color-coded by company origin: FinPay (Blue), Vaultly (Orange), Unified Post-M&A (Emerald), Shared/External (Purple), with CONFLICTS_WITH (Red) and REDUNDANT_WITH (Green) edges.
- **Node Inspector Drawer**: Click any node on the canvas to inspect its full properties, architecture domain, and tenant provenance.

---

## Phase 5: Live Graph Mutations (Track 03 Hardening)

Satisfying Track 03's primary requirement — **"Keeping knowledge current as things change"**:  
When architects and leaders make decisions, they mutate the knowledge graph in real-time using transactional Cypher `MERGE`, `SET`, and edge relinking.

You can trigger live mutations from the **War-Room UI buttons** or directly via CLI:
```bash
# 1. Resolve Auth Conflict (Unifies 15-min FinPay JWT & 7-day Vaultly session into 30-min biometric policy)
python -m src.cli mutate resolve-auth

# 2. Resolve Data Retention Conflict (Deprecates conflicting policies; enacts 90-day tiered audit storage)
python -m src.cli mutate resolve-retention

# 3. Merge Cross-Company Teams (Merges FinPay SecArch & Vaultly Identity Growth into unified team)
python -m src.cli mutate merge-teams

# 4. Reset Demo Graph (Cleanly restores FalkorDB multigraph to initial state)
python -m src.cli mutate reset-demo
```

---

## Test Suite Verification

Run the full pytest suite locally:
```bash
pytest tests/ -v
```
All **55 unit & integration tests** pass across:
- **Multigraph schema integrity, node collisions, Cypher sanitization, read-only boundaries, and bridge relations** (`test_schema_and_dataset.py` - 14 tests)
- **Dense 384-dim normalized vector embeddings, native FalkorDB search, hybrid auto-linker, and stale bridge reconciliation** (`test_auto_linker.py` - 9 tests)
- **Deterministic M&A agent tools, WCC silo detection, warm intro path semantics, MCP schemas, visualization subgraphs, /api/chat & FastAPI endpoints** (`test_agent_tools.py` - 21 tests)
- **Live graph mutations, transactional Cypher updates, compliance validation, and multi-tenant baseline restoration** (`test_live_mutations.py` - 11 tests)
