# Propvest — Decisions Log

> Why we chose what we chose. Update when any architectural decision is made or changed.
> AI tools: read this to understand the rationale behind the current stack before suggesting changes.

---

## Format

Each decision follows this structure:
- **Decision:** what was decided
- **Options considered:** what else was on the table
- **Rationale:** why this choice was made
- **Trade-offs:** what we gave up
- **Revisit when:** conditions that would trigger reconsideration

---

## Session 1 Decisions

---

### Agent Runtime — Hermes

**Decision:** Use Hermes (Nous Research) as the agent runtime and scheduler.

**Options considered:**
- OpenClaw — mature ecosystem, strong plugin breadth
- Custom agent loop (LangGraph / LangChain)

**Rationale:** Hermes is the only agent with a built-in self-improving learning loop. When it solves a task it writes a reusable SKILL.md file and improves it over time. This directly solves two hard problems: scraper maintenance as REA/SQM change their frontends, and infrastructure pipeline parsing getting better without manual prompt rewriting. Persistent cross-session memory also means project context is never lost between sessions.

**Trade-offs:** Newer and faster-moving than OpenClaw. API surface may be less stable. Smaller community.

**Revisit when:** Hermes introduces breaking changes that block progress, or OpenClaw closes the self-learning gap.

---

### Scraping — Crawl4AI

**Decision:** Use Crawl4AI as the primary scraper for REA, Domain, and SQM.

**Options considered:**
- Scrapy — battle-tested but poor JS support
- Playwright alone — requires manual wiring
- Firecrawl — purpose-built for RAG but paid at scale

**Rationale:** 58k+ GitHub stars, async-first, built-in 3-tier anti-bot detection with proxy escalation, Shadow DOM flattening, and consent popup removal. Outputs clean LLM-ready Markdown directly — no conversion step before RAG ingestion.

**Trade-offs:** Self-hosted means we manage proxies and retries ourselves at scale.

**Revisit when:** REA/Domain bot detection defeats Crawl4AI consistently, or Firecrawl drops to affordable pricing.

---

### Infrastructure Pipeline Parsing — ScrapeGraphAI

**Decision:** Use ScrapeGraphAI for parsing unstructured infrastructure sources (state gov portals, planning PDFs, news).

**Options considered:**
- Custom Playwright + regex — brittle, breaks constantly
- Crawl4AI with LLM extraction — possible but ScrapeGraphAI is purpose-built

**Rationale:** Natural language prompts instead of CSS selectors. No selector maintenance. Handles multi-page and PDF sources. Infrastructure pipeline is the highest alpha signal (market hasn't priced it yet) but the messiest data — ScrapeGraphAI is designed exactly for this.

**Trade-offs:** Every page burns LLM tokens. Debugging is harder when LLM decisions aren't transparent.

**Revisit when:** Token costs become significant at scale, or a selector-free OSS alternative emerges.

---

### RAG Layer — LlamaIndex

**Decision:** Use LlamaIndex as the RAG layer for suburb retrieval and knowledge drop ingestion.

**Options considered:**
- LangChain — broader but more boilerplate
- Custom vector store — too much overhead for v1

**Rationale:** Purpose-built for RAG. Less boilerplate than LangChain for index → retrieve → query workflows. Swappable via config.yaml if needed. Plugin interface (base_rag.py) means LangChain can replace it with zero code changes elsewhere.

**Trade-offs:** Less flexibility than LangChain for non-RAG use cases. Smaller ecosystem.

**Revisit when:** We need agent orchestration features that LangChain/LangGraph handles better.

---

### Orchestration — n8n

**Decision:** Use n8n for workflow orchestration, scrape job scheduling, and alerting.

**Options considered:**
- GitHub Actions cron — free but limited, no visual debugging
- Prefect / Airflow — overkill for current scale
- Custom scheduler — unnecessary build

**Rationale:** Self-hostable, free, visual workflow builder, native Hermes integration, Telegram/email alerting built in. Triggers scrape jobs, routes data to Supabase, and alerts on score changes without custom code.

**Trade-offs:** Another self-hosted service to maintain.

**Revisit when:** n8n overhead outweighs benefit, or GitHub Actions becomes sufficient.

---

### LLM — Claude API via MCP

**Decision:** Use Claude API as primary LLM, connected via MCP tools. OpenAI as fallback via config only.

**Options considered:**
- OpenAI GPT-4o — strong but Claude better for structured output + long context
- Local models via Ollama — free but quality gap for reasoning tasks

**Rationale:** Claude's structured output mode enforces JSON schema — critical for our reliability absolute. MCP tool protocol means adding new data sources = adding a new tool, not rewiring. Swappable via config.yaml.

**Trade-offs:** API cost per call. Dependent on Anthropic availability.

**Revisit when:** Costs exceed budget, or a local model closes the reasoning quality gap.

---

### Scoring — Deterministic Only

**Decision:** Suburb scores are computed by deterministic weighted math only. LLM never computes a score.

**Options considered:**
- LLM-assisted scoring — flexible but hallucination risk
- ML model — future consideration, not v1

**Rationale:** Reliability is Absolute #2. An LLM inventing suburb scores with false confidence would undermine the entire product. Deterministic math is auditable, versioned, and reproducible. LLM role is explain and converse only.

**Trade-offs:** Less adaptive than ML scoring. Weights require manual tuning.

**Revisit when:** Phase 3 productisation — ML model can run alongside as v2 scorer, validated against deterministic v1.

---

### Architecture — Plugin-based

**Decision:** All business logic lives in plugins. Core only orchestrates. Plugins communicate via event bus.

**Options considered:**
- Monolithic — faster to start, harder to scale
- Microservices — too complex for current stage

**Rationale:** Scalable absolute. Swap any component (RAG, LLM, scraper, scorer) via config.yaml with zero code changes. Feature flags mean broken components can be disabled without deleting code. Plugin interfaces mean new data sources slot in cleanly.

**Trade-offs:** More upfront structure. Event bus adds indirection.

**Revisit when:** Never — this is the foundation. Expand it, don't replace it.

---

### Storage Format — Markdown Everywhere

**Decision:** All project files, skill files, knowledge drop content stored as Markdown.

**Options considered:**
- JSON — machine readable but not human or agent friendly
- Plain text — no structure
- Word/PDF — not git-trackable or token efficient

**Rationale:** Markdown is simultaneously readable by humans, LLMs, and agents. LLMs were trained on vast amounts of it. Token efficient. Git-trackable line by line. LlamaIndex chunks it cleanly for RAG.

**Trade-offs:** None significant for this use case.

---

### Session Continuity — agents.md + PROJECT.md

**Decision:** agents.md (public) tells all AI tools to read PROJECT.md (gitignored) first every session.

**Options considered:**
- Paste context manually each session — tedious and error-prone
- Single context file — mixes public and private

**Rationale:** PROJECT.md stores local paths and private context without polluting the public repo. agents.md is the universal entry point all tools discover by convention. Together they give every tool full project context from session start with no manual steps.

**Trade-offs:** PROJECT.md must be manually updated when local paths change.

---

## Scoring Weights History

| Version | Date | vacancy | stock | population | infra | relative_median | Notes |
|---------|------|---------|-------|------------|-------|-----------------|-------|
| v1.0 | Session 1 | 0.25 | 0.20 | 0.20 | 0.20 | 0.15 | Initial weights — validate against eval set before changing |

## Session 2 Decisions

### Orchestration — Windmill.dev
**Decision:** Use Windmill instead of n8n.
**Rationale:** Windmill supports "Workflow-as-code" using typed Python. This allows us to use Pydantic schemas to ensure the "digestible data" requirement is met with high engineering rigor.
**Revisit when:** System needs more visual, non-technical "no-code" logic.

### Data Funnel — Tiered Strategy
**Decision:** Filter 15,000 suburbs down to ~3,000 "Tier 1" candidates based on LGA metrics (20k pop / 1.5% growth).
**Rationale:** Reduces bot-detection risk on REA/Domain by 80% and focuses compute on high-alpha markets.
**Revisit when:** A user explicitly requests data for a "Tier 2" suburb (triggers on-demand scrape).

### Agent Logic — Hermes Profiles
**Decision:** Use a single Hermes brain with three specific profiles: Coordinator (Routing), Researcher (Skills), and Auditor (Veto/Review).
**Rationale:** Avoids "Agent Sprawl" and multi-agent latency while providing high-quality review for the Top 10% suburbs.

### Version Control — Branching Strategy
**Decision:** Use a `main` and `dev` branch structure.
**Rationale:** Standard practice to protect `main` for stable releases while using `dev` for active feature work and agent testing.
**Trade-offs:** Requires manual merges/PRs, but provides a safety buffer for agent-generated code.

> Always run 30-suburb eval set before changing weights. Log changes here with rationale.