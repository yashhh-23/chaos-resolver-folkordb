# The M&A Chaos Resolver (OrgBridge AI) 🧠⚡

> **FalkorDB Hackathon (Track 03: Company Brain)**  
> Turning M&A chaos into deterministic knowledge using FalkorDB's multigraph tenancy, native graph algorithms, and hybrid vector entity resolution.

---

## 📌 Architecture & Phase 1 Highlights

During an M&A (e.g., FinPay acquiring Vaultly), organizations face duplicate microservices, conflicting compliance policies, fractured org structures, and tribal knowledge silos. Flat vector RAG fails here because it cannot reason across tenants or evaluate graph paths.

OrgBridge AI leverages **FalkorDB** as the heart of the system across four core capabilities:
1. **Multigraph Tenancy**: Physical graph isolation (`finpay_graph` for Company A, `vaultly_graph` for Company B) and an integrated layer (`merged_brain`) for cross-company entity resolution.
2. **Hybrid Graph + Vector Entity Resolution**: Identifies redundant systems and policy contradictions with shared external dependencies (`ExternalAPI` like UIDAI Aadhaar, Stripe, AWS KMS).
3. **Graph Algorithms as Agent Tools**: PageRank for real expert discovery (based on authored RFCs & resolved incidents) and Shortest Path for warm introductions across company borders.
4. **Decision & Policy Conflict Lineage**: Explicit `[:CONFLICTS_WITH]` and `[:DERIVED_FROM]` edges tracing rules directly back to source Slack threads, Jira tickets, and RFC documents.

---

## 🗂️ Project Structure

```
chaos-resolver-folkordb/
├── docker-compose.yml              # FalkorDB local container configuration
├── .env.example                    # Environment variable template (local or FalkorDB Cloud)
├── requirements.txt                # Python dependencies
├── artifacts/                      # Generated ingestion artifacts
│   ├── cypher/                     # Exported runnable Cypher scripts
│   │   ├── finpay_graph.cypher     # FinPay isolated graph (69 statements)
│   │   ├── vaultly_graph.cypher    # Vaultly isolated graph (70 statements)
│   │   └── merged_brain.cypher     # Unified brain with bridge edges (129 statements)
│   └── dataset.json                # Structured JSON representation
├── src/
│   ├── config.py                   # Centralized Pydantic settings
│   ├── db/
│   │   └── client.py               # FalkorDB client with index manager & query sanitizer
│   ├── schema/
│   │   ├── models.py               # Strict Pydantic models (Person, Team, System, etc.)
│   │   └── cypher_schema.py        # Schema labels, relationships, indexing, & Cypher generators
│   ├── embeddings/
│   │   └── service.py              # Normalized 384-dim semantic embedding service (Local & OpenAI)
│   ├── pipeline/
│   │   ├── vector_index.py         # FalkorDB native vector indexing (db.idx.vector) & embedding population
│   │   └── auto_linker.py          # Hybrid Vector + Graph Auto-Linker Engine (threshold >= 0.82)
│   ├── data/
│   │   ├── synthetic_data.py       # Realistic FinPay + Vaultly M&A dilemma dataset
│   │   ├── builder.py              # Multigraph Cypher statement compiler & exporter
│   │   └── seed.py                 # CLI seeder for FalkorDB & artifact generator
│   ├── cli.py                      # Interactive FalkorDB REPL & CLI tool
│   └── utils/
│       └── logger.py               # Standardized application logging
└── tests/
    ├── test_schema_and_dataset.py  # Schema, edge integrity, collision guards (9 tests)
    └── test_auto_linker.py         # Vector embeddings & auto-linker resolution (4 tests)

```

---

## 🧬 Graph Schema Specification

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

## 🛡️ Edge Cases Handled

1. **Entity Collision (Same Name, Different Person/Service):**
   - Namespaced node IDs (`finpay:person:rahul_s` vs `vaultly:person:rahul_s`) and mandatory `company_origin` property prevent `MERGE` statements from collapsing distinct people or services.
2. **Terminology Mismatch (Different Name, Same Concept):**
   - e.g. `Customer-KYC-Service` (FinPay) vs `User-Onboarding-Verification` (Vaultly). Connected through shared external dependency `(:ExternalAPI {id: 'ext:api:uidai_aadhaar'})` and tagged with `[:REDUNDANT_WITH {similarity: 0.95}]`.
3. **Policy Contradictions & Temporal Precedence:**
   - Evaluates `effective_date`, `authority_level`, and `status`. E.g., FinPay's 15-minute JWT expiration (`finpay:dec:jwt_15m`) directly conflicts with Vaultly's 7-day persistent mobile session tokens (`vaultly:dec:session_7d`).
4. **LLM Cypher Hallucination & Infinite Traversal Safeguard:**
   - Parameterized queries with a `sanitize_cypher_query` guard that automatically rewrites unbounded variable paths `[*]` to `[*1..4]` and guarantees a `LIMIT 25` clause.
5. **Memory & Rate Limit Protection:**
   - Node payloads store concise 2–3 sentence excerpts instead of bloating graph memory with raw unstructured documents.

---

## 🚀 Quickstart & Seeding

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
For local Docker:
```bash
docker-compose up -d
```
Or set `FALKORDB_URL` in `.env` for FalkorDB Cloud.

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

### 5. Run Test Suite
```bash
pytest tests/ -v
```
All **13 unit tests** pass verifying schema constraints, edge referential integrity, collision protection, query bounding, vector embeddings, and hybrid resolution.

