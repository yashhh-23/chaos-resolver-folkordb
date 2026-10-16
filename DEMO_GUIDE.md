# OrgBridge AI (The M&A Chaos Resolver) — Hackathon Demo Guide 🧠⚡

> **FalkorDB Hackathon (Track 03: Company Brain)**  
> **Repository:** https://github.com/yashhh-23/chaos-resolver-folkordb  
> **Live War-Room UI (Vercel):** https://frontend-blond-gamma-x5p8l19cp2.vercel.app  
> **Live Backend API (Render):** https://orgbridge-ai-backend.onrender.com  
> **Interactive Swagger Docs:** https://orgbridge-ai-backend.onrender.com/docs  

---

## 🎯 Executive Summary for Judges

When **FinPay** acquired **Vaultly**, engineering and architecture teams inherited massive organizational friction:
- **Duplicate Microservices:** Both companies built separate authentication, balance tracking, and ledger services.
- **Hidden Policy Contradictions:** FinPay strictly purges security logs after 30 days; Vaultly mandates a 180-day forensic audit retention rule.
- **Architectural Contradictions:** FinPay forces 15-minute expiring JWTs; Vaultly relies on 7-day mobile session continuity.
- **Tribal Knowledge Silos:** Engineers don't know who owns what or whom to contact across company borders.

**Flat Vector RAG fails** because it has no concept of company provenance, cannot detect contradictions between two equally valid documents, and cannot traverse multi-hop relationship paths.

**OrgBridge AI solves this with FalkorDB**:
1. **Multigraph Tenancy:** Physical graph isolation (`finpay_graph`, `vaultly_graph`) linked by a unified reasoning graph (`merged_brain`).
2. **Hybrid Vector + Graph Entity Resolution:** Identifies duplicate systems and policy clashes using dense 384-dim semantic embeddings augmented by shared external API dependencies (`ExternalAPI` UIDAI Aadhaar, Stripe, AWS KMS).
3. **Deterministic Agent Tools:** Built on native FalkorDB graph algorithms (PageRank for genuine SME influence, Bounded Path Traversal for warm introductions).
4. **Keeping Knowledge Current (Track 03 Hardening):** Transactional Cypher mutations (`MERGE`, `SET`) allow leadership to resolve conflicts and merge teams live on-screen.

---

## 🎬 3-Minute Video Recording / Demo Walkthrough Script

### **0:00 – 0:30 | The Problem & Architecture (The War Room)**
- **Visual:** Open the OrgBridge AI War Room Dashboard (`http://localhost:3000` or deployed Vercel link).
- **Voiceover:**
  > *"Welcome to OrgBridge AI — The M&A Chaos Resolver built on FalkorDB for Track 03: Company Brain. When FinPay acquired Vaultly, they faced architectural chaos: duplicate systems, conflicting security policies, and disconnected teams. Flat vector search fails here because documents contradict each other. OrgBridge uses a 3-tenant FalkorDB multigraph — FinPay's graph, Vaultly's graph, and a merged brain where cross-company relationships are discovered automatically."*

### **0:30 – 1:00 | Prompt 1: SME Discovery via PageRank**
- **Action:** Click **"Auth SME Discovery"** under Judge Evaluation Prompts.
- **Visual:** The agent immediately replies with **Diya Nair** (PageRank influence 0.92, #1 for Authentication). The canvas isolates Diya Nair, her authored RFCs, and resolved Jira tickets in bright cyan.
- **Voiceover:**
  > *"Who actually knows the authentication stack at Vaultly? Instead of asking Slack, our agent runs PageRank over authored RFCs, resolved high-severity incidents, and system ownership. It identifies Diya Nair as the authoritative counterpart, citing her exact RFC-104 and postmortem."*

### **1:00 – 1:30 | Prompt 2: Policy & Retention Conflicts**
- **Action:** Click **"Policy Conflicts"**.
- **Visual:** The agent exposes the critical clash: FinPay's 30-Day Purge vs. Vaultly's 180-Day Forensic Audit rule. The canvas highlights the red `[:CONFLICTS_WITH]` edge connecting both systems.
- **Voiceover:**
  > *"Next, compliance. The agent traverses FalkorDB's `[:CONFLICTS_WITH]` bridge edges to detect an active regulatory clash: FinPay automatically purges session telemetry in 30 days, while Vaultly's policy mandates 180 days for financial audits. The lineage traces back to FinPay's RFC-088 and Vaultly's audit standard."*

### **1:30 – 2:00 | Prompt 3: Duplicate Microservices & Shared APIs**
- **Action:** Click **"Redundant Systems"**.
- **Visual:** The canvas isolates clusters of redundant services (Gatekeeper-Auth vs. Pulse-Identity, FinPay-Ledger-Core vs. Vault-Balance-Service) connected via green `[:REDUNDANT_WITH]` edges and their shared calls to UIDAI Aadhaar and Stripe.
- **Voiceover:**
  > *"Where can we save infrastructure costs? FalkorDB's hybrid auto-linker compares 384-dimensional dense vectors and matches shared external dependencies. Here, Gatekeeper-Auth and Pulse-Identity both call UIDAI Aadhaar with an 89% semantic overlap — an immediate consolidation candidate."*

### **2:00 – 2:30 | Prompt 4: Cross-Company Warm Introduction**
- **Action:** Click **"Cross-Border Warm Intro"**.
- **Visual:** The shortest path between Aarav Mehta (FinPay) and Diya Nair (Vaultly) lights up with glowing particles traversing their shared team leads.
- **Voiceover:**
  > *"How do these engineers connect without cold emails? FalkorDB evaluates bounded path traversal to find the shortest warm introduction path — connecting Aarav Mehta to Diya Nair in 4 hops through their respective team leads."*

### **2:30 – 3:00 | Track 03 Live Mutation: Keeping Knowledge Current**
- **Action:** In the **Live Brain Mutations** bar, click **"Resolve Auth Conflict"**, then **"Merge Sec & Auth"**.
- **Visual:** The chat logs the transactional execution of Cypher `MERGE`/`SET`. The canvas dynamically updates: the conflicting policies are marked `DEPRECATED`, the new `Unified M&A Adaptive Session Policy` is born, and a joint engineering team is created live in FalkorDB.
- **Voiceover:**
  > *"Most importantly for Track 03: keeping knowledge current as things change. Leadership decides on a compromise: a 30-minute token with biometric refresh. With one click, OrgBridge executes a transactional Cypher MERGE, deprecates the old rules, and merges both teams into a unified engineering org live in FalkorDB Cloud. Knowledge is always current, deterministic, and verifiable."*

---

## 🚀 Live Cloud Deployment Verification

### 1. Backend (FastAPI on Render)
- **Status:** 🟢 **LIVE & HEALTHY**
- **Endpoint:** `https://orgbridge-ai-backend.onrender.com/api/health`
- **Verification Response:**
  ```json
  {
    "status": "healthy",
    "falkordb_connected": true,
    "environment": "production",
    "active_graphs": [
      "finpay_graph",
      "vaultly_graph",
      "merged_brain"
    ]
  }
  ```

### 2. Frontend (Next.js 14 on Vercel)
To deploy the frontend to Vercel in 60 seconds:
1. Go to [vercel.com/new](https://vercel.com/new) and import `https://github.com/yashhh-23/chaos-resolver-folkordb`.
2. Under **Root Directory**, click edit and select **`frontend`**.
3. Under **Environment Variables**, add:
   - `NEXT_PUBLIC_API_URL` = `https://orgbridge-ai-backend.onrender.com`
4. Click **Deploy**.

---

## 🏆 Track 03 Rubric Checklist

| Hackathon Requirement | How OrgBridge AI Implements It |
| :--- | :--- |
| **Multitenant Knowledge Base** | Isolated `finpay_graph` and `vaultly_graph` + unified `merged_brain` in FalkorDB Cloud. |
| **Entity Resolution** | Dense 384-dim semantic embeddings combined with shared external dependency overlap (`ExternalAPI`). |
| **Graph Algorithms as Agent Tools** | PageRank for SME discovery, Bounded Shortest Path for warm introductions, conflict cycle detection. |
| **Decision Lineage & Citations** | Clickable RFC documents, Jira tickets, and Slack postmortems tracing every policy back to ground truth. |
| **Keeping Knowledge Current** | Real-time transactional Cypher `MERGE`/`SET` mutations updating graph state live without re-indexing. |
| **Full-Stack War Room** | Interactive Next.js 14 split-screen with force-directed 2D canvas, pulsing active subgraphs, and node inspector. |
