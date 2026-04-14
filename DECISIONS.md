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

**Decision:** Use Crawl4AI as the primary scraper for SQM Research and infrastructure sources.

**Options considered:**

- Scrapy — battle-tested but poor JS support
- Playwright alone — requires manual wiring
- Firecrawl — purpose-built for RAG but paid at scale

**Rationale:** 58k+ GitHub stars, async-first, built-in 3-tier anti-bot detection with proxy escalation, Shadow DOM flattening, and consent popup removal. Outputs clean LLM-ready Markdown directly.

**Trade-offs:** Self-hosted means we manage proxies and retries ourselves at scale.

**Revisit when:** SQM bot detection defeats Crawl4AI consistently.

**Note (Session 4):** Crawl4AI is no longer used for Domain. curl-cffi handles Domain scraping. See Session 4 decisions below.

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

**Rationale:** Purpose-built for RAG. Less boilerplate than LangChain for index → retrieve → query workflows. Swappable via config.yaml if needed.

**Trade-offs:** Less flexibility than LangChain for non-RAG use cases.

**Revisit when:** We need agent orchestration features that LangChain/LangGraph handles better.

---

### Orchestration — Windmill

**Decision:** Use Windmill instead of n8n for workflow orchestration.

**Rationale:** Windmill supports workflow-as-code using typed Python with Pydantic validation. Ensures digestible data rigor.

**Revisit when:** System needs more visual, non-technical no-code logic.

---

### LLM — Claude API via MCP

**Decision:** Use Claude API as primary LLM, connected via MCP tools. OpenAI as fallback via config only.

**Rationale:** Claude's structured output mode enforces JSON schema — critical for reliability absolute. MCP tool protocol means adding new data sources = adding a new tool, not rewiring.

**Trade-offs:** API cost per call. Dependent on Anthropic availability.

**Revisit when:** Costs exceed budget, or a local model closes the reasoning quality gap.

---

### Scoring — Deterministic Only

**Decision:** Suburb scores are computed by deterministic weighted math only. LLM never computes a score.

**Rationale:** Reliability is Absolute #2. An LLM inventing suburb scores with false confidence would undermine the entire product. Deterministic math is auditable, versioned, and reproducible. LLM role is explain and converse only.

**Trade-offs:** Less adaptive than ML scoring. Weights require manual tuning.

**Revisit when:** Phase 3 productisation — ML model can run alongside as v2 scorer, validated against deterministic v1.

---

### Architecture — Plugin-based

**Decision:** All business logic lives in plugins. Core only orchestrates. Plugins communicate via event bus.

**Rationale:** Scalable absolute. Swap any component via config.yaml with zero code changes. Feature flags mean broken components can be disabled without deleting code.

**Trade-offs:** More upfront structure. Event bus adds indirection.

**Revisit when:** Never — this is the foundation. Expand it, don't replace it.

---

### Storage Format — Markdown Everywhere

**Decision:** All project files, skill files, knowledge drop content stored as Markdown.

**Rationale:** Markdown is simultaneously readable by humans, LLMs, and agents. Token efficient. Git-trackable line by line. LlamaIndex chunks it cleanly for RAG.

---

### Session Continuity — agents.md + PROJECT.md

**Decision:** agents.md (public) tells all AI tools to read PROJECT.md (gitignored) first every session.

**Rationale:** PROJECT.md stores local paths and private context without polluting the public repo. agents.md is the universal entry point all tools discover by convention.

---

## Session 2 Decisions

### Data Funnel — Tiered Strategy

**Decision:** Filter 15,000 suburbs down to Tier 1 candidates based on LGA metrics (pop > 20k, growth > 0.5%).

**Rationale:** Reduces bot-detection risk and focuses compute on high-alpha markets. Initial threshold of 1.5% produced only 83 LGAs — too restrictive. Lowered to 0.5% → 193 LGAs → 8,639 suburbs.

**Revisit when:** A user explicitly requests data for a Tier 2 suburb (triggers on-demand scrape).

---

## Session 3 Decisions

### Growth Funnel Threshold — 0.5%

**Decision:** `lga_min_growth_pct` set to 0.5% in config.yaml → 193 LGAs → 8,639 Tier 1 suburbs.

### ABS Data Source — SAL replaces SSC

**Decision:** ASGS suburb concordance uses SAL (Suburb and Locality) codes, not SSC. abs_ingestor.py detects both naming conventions automatically.

### scrape_log — File-based Until Supabase Is Wired

**Decision:** base_scraper.log_run() writes to data/raw/scrape_log.json rather than Supabase for now.

---

## Session 4 Decisions

---

### Domain Scraping — curl-cffi + **NEXT_DATA**

**Decision:** Use curl-cffi with TLS impersonation to scrape Domain suburb profile pages. Extract data from the `__NEXT_DATA__` JSON block embedded in the page source.

**Options considered:**

- Crawl4AI + Camoufox — Camoufox confirmed degraded in 2026 (year-long maintenance gap, experimental only)
- Paid scraping APIs (ScraperAPI, Zyte) — $50-100/mo, violates Absolute #1
- Plain requests — fails Akamai TLS fingerprint check immediately

**Rationale:** Akamai's primary detection vector in 2026 is JA3/JA4 TLS fingerprinting. curl-cffi impersonates real Chrome browser TLS handshakes at the library level — free, lightweight, no full browser required. `__NEXT_DATA__` is a structured JSON block already embedded in the page source, confirmed accessible without authentication on Domain suburb profile pages (verified manually April 2026). Targeting JSON directly avoids brittle CSS selector maintenance.

**Known risk:** curl-cffi addresses TLS fingerprinting but not behavioural analysis. Slow drip (50-80 requests/day) mitigates behavioural detection. Not bulletproof — monitor for blocks.

**Trade-offs:** If Domain changes their Next.js rendering approach, **NEXT_DATA** may move or disappear. Low probability given it's core to their frontend architecture.

**Revisit when:** Block rate exceeds 20% of requests, or Domain migrates away from Next.js.

---

### Domain Scraping — States Covered

**Decision:** Use Domain **NEXT_DATA** scraping ONLY for QLD, WA, NT, TAS, and ACT. Not for NSW, VIC, SA.

**Rationale:** NSW, VIC, and SA have free bulk Valuer General data — more reliable, no scraping risk, quarterly/weekly cadence. Domain scraping is the fallback for states with no equivalent bulk source.

**State source map:**

| State    | Source                | Method                      |
| -------- | --------------------- | --------------------------- |
| NSW      | NSW Valuer General    | Bulk .DAT download          |
| VIC      | Data.Vic VPSR         | Quarterly CSV               |
| SA       | SA Valuer General     | Quarterly Excel             |
| QLD      | Domain suburb profile | curl-cffi **NEXT_DATA**     |
| WA       | Domain suburb profile | curl-cffi **NEXT_DATA**     |
| TAS      | Domain suburb profile | curl-cffi **NEXT_DATA**     |
| NT       | Domain suburb profile | curl-cffi **NEXT_DATA**     |
| ACT      | Domain suburb profile | curl-cffi **NEXT_DATA**     |
| National | SQM Research          | curl-cffi (vacancy + stock) |

---

### PEXA — Ruled Out

**Decision:** Do not use PEXA Postcode Insights as a data source.

**Rationale:** Manual verification confirmed PEXA has no readily accessible structured data tool. Interactive tool does not expose scrapable data or API endpoints.

---

### Property Filter — Standalone Houses Only

**Decision:** Propvest scores standalone houses only. Units and townhouses are excluded from all scoring and signal computation.

**Rationale:** Investor profile (buy and hold, capital growth) is focused on standalone residential. Units and townhouses have fundamentally different supply dynamics and growth profiles.

**Implementation:** Filter Domain **NEXT_DATA** `propertyCategories` to `propertyCategory: "House"` only. Valuer General bulk data filtered to house sales only.

---

### Price Filter — Suburb Median ≤ $800k

**Decision:** Only score suburbs where the standalone house median is ≤ $800,000.

**Rationale:** Investor's maximum purchase price is $800k. Suburbs above this median have limited entry-level stock within budget. Applied post-scrape on first pass, then determines ongoing scrape eligibility.

**Trade-offs:** First pass must scrape all tier 1 suburbs in QLD/WA/NT/TAS before filter can be applied. Ongoing scrape list reduces significantly after first pass.

---

### Minimum Sales Volume — 12 House Sales Per Year

**Decision:** A suburb requires a minimum of 12 standalone house sales in the trailing 12 months to be scored. Below this threshold the suburb is flagged as `data_thin` and excluded from scoring.

**Rationale:** Below 12 sales, median price and DOM figures are statistically unreliable. A single outlier sale can move the median by 10-15%. Scoring unreliable data would undermine Absolute #2 (Reliable).

**Implementation:** Check `numberSold` in Domain **NEXT_DATA** `propertyCategories` filtered to `propertyCategory: "House"`. Flag as `data_thin: true` in suburb record. Reassess quarterly.

**Revisit when:** Never change this threshold without running eval set first.

---

### Scrape Frequency — ABS Growth Rate Bootstrap

**Decision:** Classify QLD/WA/NT/TAS suburbs into scrape tiers using ABS population growth rate as bootstrap classifier until real DOM data is available.

| Tier | ABS Growth Rate       | Scrape Frequency |
| ---- | --------------------- | ---------------- |
| Hot  | >2%                   | Weekly           |
| Warm | 0.5-2%                | Monthly          |
| Cold | <0.5% (passed filter) | Quarterly        |

**Rationale:** ~80% correlation between high population growth and high housing turnover is sufficient for a bootstrap classifier. Edge cases (mining towns, new estates) self-correct after first real DOM data comes in from scraping. ABS growth data already exists in tier1_candidates.json — no additional data fetch required.

**Reclassification:** After first full scrape pass, reclassify tiers based on actual `daysOnMarket` from Domain:

- DOM <30 days → Hot
- DOM 30-60 days → Warm
- DOM >60 days → Cold

**Trade-offs:** ~20% of initial classifications will be wrong. Accepted — corrects automatically after first scrape cycle.

---

### Domain **NEXT_DATA** — Fields Extracted

**Decision:** Extract only these fields from Domain **NEXT_DATA** per suburb request:

From `propertyCategories` filtered to `propertyCategory: "House"`:

- `medianSoldPrice` → Relative Median Gap signal
- `numberSold` → Sales Volume Momentum signal + data_thin check
- `salesGrowthList` (year-on-year) → Sales Volume Momentum trend
- `daysOnMarket` → scrape tier reclassification
- `auctionClearanceRate` → context layer display only

From `statistics`:

- `ownerOccupierPercentage` → Red Flag alert (if <70%)
- `renterPercentage` → Red Flag alert (if >50%)
- `population` → context layer display only

Everything else (school data, listing cards, surrounding suburb links) is ignored.

---

### Income-to-Median Ratio — Context Layer Only

**Decision:** Do not include income-to-median affordability ratio as a scoring signal. Display as context layer only.

**Rationale:** ABS Census income data is 5 years stale (2021 census, next 2026). A 5-year-old affordability ratio is not a leading indicator. Leading signals already in the model (vacancy rate, MOI, sales volume momentum, population growth) are more current and more predictive.

**Implementation:** If income data is available, display alongside suburb card in UI. Weight = 0 in scoring.

---

### Scoring Model Update — Sales Volume Momentum Added

**Decision:** Add Sales Volume Momentum as a scored signal at 10% weight. Adjust Relative Median Gap from 15% to 5%.

**Rationale:** Sales volume trend (rising quarterly number of sales) is a leading demand indicator confirmed by Domain **NEXT_DATA** data availability. Relative Median Gap is a useful context signal but less predictive than volume momentum for buy-and-hold growth thesis.

**Revisit when:** Eval set shows relative median is outperforming volume momentum in backtesting.

---

## Session 5 Decisions

---

### Domain **NEXT_DATA** — Apollo GraphQL Structure

**Decision:** Extract suburb data from `__APOLLO_STATE__` inside `__NEXT_DATA__`, not from a top-level `suburbData` prop.

**Rationale:** Domain uses Apollo GraphQL client-side caching. Data lives under two Apollo keys:

- `LocationProfile:{id}` → `data.propertyCategories` (price/volume per bedroom count)
- `Suburb:{base64}` → `statistics` (owner-occupier %, population)

**Implementation detail:** `propertyCategories` has one entry per bedroom count — there is no aggregate "all bedrooms" entry. Aggregation strategy: `number_sold` = sum across all House entries; `median_sold_price` / `days_on_market` / `sales_growth_list` = taken from the entry with the highest `numberSold` (dominant bedroom count).

**Revisit when:** Domain migrates away from Apollo or restructures its GraphQL schema.

---

### Domain Suburb Profile URL Format

**Decision:** Domain suburb profile slugs follow the format `{suburb-kebab}-{state-lower}-{postcode}`.
Example: `paddington-qld-4064` → `https://www.domain.com.au/suburb-profile/paddington-qld-4064`

**Rationale:** Verified by live HTTP test (April 2026). The reverse order (`suburb-postcode-state`) returns 404.

---

### Postcode Source — Decision Deferred

**Decision:** Postcode enrichment for geography_trinity.json deferred to Session 6. ABS does not publish cross-geography concordances (SAL→POA) as downloadable tabular files — only as shapefiles (unsuitable) or same-geography edition-change CSVs.

**Options under consideration for Session 6:**

- data.gov.au "Australian Postcodes" dataset (government open data)
- Derive postcodes from Domain slug after first scrape pass

**Revisit when:** Session 6 begins. Postcodes are a blocker for SQM scraper (postcode-keyed) and for generating complete Domain slugs.

---

### SA2 — Deprioritised

**Decision:** SA2 enrichment deferred indefinitely. No scored signal uses SA2 directly. ABS cross-geography concordance (SAL→SA2) unavailable as a tabular file.

**Revisit when:** A Phase 2 signal explicitly requires SA2 joins.

---

## Session 6 Decisions

---

### Postcode Source — data.gov.au Australian Postcodes CSV

**Decision:** Use the data.gov.au "Australian Postcodes" CSV dataset (mirrored at GitHub: matthewproctor/australianpostcodes) to enrich geography_trinity.json with postcodes. Match on (suburb_name_upper, state) → postcode.

**Options considered:**

- ABS SAL→POA concordance ZIPs — all URLs 404 (ABS no longer hosts tabular concordances)
- Derive from Domain slug after scrape — circular dependency (need postcode to build slug)
- Manual entry — infeasible at 8,639 rows

**Rationale:** The data.gov.au dataset has 18,559 rows covering all Australian localities. After joining 8,629/8,639 suburbs matched (99.9%). The 10 remaining are national parks and territories with no postal addresses (Blue Mountains National Park, Moreton Bay area, etc.) — these will never appear on Domain and are data_thin by definition.

**Implementation notes:**

- Suburb names with ABS disambiguation parens (e.g., "Paddington (Qld)") have parens stripped before matching
- 704 suburbs map to multiple postcodes — dominant (first/lowest) postcode chosen; all logged to data/raw/abs/multi_postcode_suburbs.json
- Postcodes zero-padded to 4 digits (e.g., ACT 200 → "0200")
- `_domain_slug()` updated to strip parens from suburb name before slugifying — fixes "paddington-qld-qld-4064" → "paddington-qld-4064"
- python-dotenv added to requirements.txt for .env loading

**Revisit when:** ABS restores SAL→POA concordance tabular files (would give higher-quality match using official area codes).

---

### Domain Block Detection — False Positive Fix

**Decision:** Distinguish true WAF blocks (HTTP 403/429/network errors) from "no house data" responses (200 OK, page loaded, no house sales for suburb). Only WAF blocks count toward the 20% block rate alert threshold.

**Rationale:** Initial scrape of 50 QLD suburbs showed 34% "block rate" — but zero actual 403/429 responses. All 17 "blocks" were legitimate empty results for small rural hamlets with no house sales on Domain. False alert at 34% would have halted scraping unnecessarily.

**Implementation:** `_scrape_batch()` returns `(results, true_blocks, no_data_count)` as separate counts. `_scrape_suburb()` returns `None` for WAF blocks, `_NO_DATA_SENTINEL` for legitimate empty pages. Only `None` triggers `_log_block()` and increments `true_blocks`.

**Revisit when:** Domain adds a different empty-page response format that needs separate handling.

---

### Supabase Schema — Unique Constraint on (suburb_name, state)

**Decision:** Change `UNIQUE (state, suburb_name, postcode)` to `UNIQUE (suburb_name, state)` in the suburbs table DDL.

**Rationale:** 10 suburbs have NULL postcodes (national parks, territories). PostgreSQL NULL values do not satisfy UNIQUE constraints — two rows with NULL postcode and the same (state, suburb_name) would not conflict and could be duplicated on re-upsert. The natural key for suburb identity is (suburb_name, state) without postcode.

**Impact:** Migration SQL updated before first run — no data loss, no rollback needed.

---

### SQM Research — URL and Data Format Changes

**Decision:** Update SQM scraper to use correct 2026 URL and data format.

**Old (broken):**

- Listings: `https://sqmresearch.com.au/graph_listings.php?postcode={pc}&t=1` → 404
- Parser: regex looking for `[[new Date(...), value]]` style arrays → never matched

**New (working):**

- Vacancy: `graph_vacancy.php` still works — but data is `var data = [{year,month,listings,properties,vr}...]` JSON format
- Listings: `https://sqmresearch.com.au/property/total-property-listings?postcode={pc}&t=1` → `var data = [{year,month,r30,r60,r90,r180,r180p}...]`
- Stock on market = r30 + r60 + r90 + r180 + r180p from most recent month

**Verified:** Paddington (4064) → vacancy_rate=0.57%, stock_on_market=81. Batch of 50 QLD postcodes: 50/50 success, both signals present.

---

### base_scraper.log_run() — Dual-Write (Supabase + File)

**Decision:** Update `log_run()` to write to both Supabase `scrape_log` table AND `data/raw/scrape_log.json`. Supabase write attempted first; file write always runs as fallback.

**Rationale:** Supabase is the production log store. File log provides offline capability and disaster recovery. Supabase failures are logged as warnings and do not raise exceptions.

**Status:** Code complete. Supabase writes currently failing because 001_create_core_tables.sql has not been run yet. File fallback active.

---

## Session 7 Decisions

---

### Supabase Loader — Deduplication Before Batch Upsert

**Decision:** Deduplicate geography_trinity.json by (suburb_name, state) before batching for Supabase upsert. Keep the row with the highest population per duplicate pair.

**Options considered:**

- Deduplicate in the database using ON CONFLICT — not possible; PostgreSQL error 21000 fires when the same conflict key appears multiple times within a single batch, before the conflict clause is evaluated
- Deduplicate after batching, per-batch — fragile; a duplicate straddling a batch boundary could still pass
- Deduplicate at source (geography_builder) — deferred; the M:N SAL→LGA join is intentional and useful for LGA attribution; dedup belongs at the loader layer

**Rationale:** The ABS SAL→LGA concordance is a many-to-many join. Suburbs that straddle two LGA boundaries appear twice with different `lga_name` but the same `sal_code`. This is correct in the geography file (both LGAs are relevant) but must be collapsed to a single row before database upsert because (suburb_name, state) is the primary unique key. Choosing the row with the highest population selects the dominant/primary LGA, which is the most useful single value for administrative lookup.

**Result:** 385 duplicate pairs dropped; 8,254 unique suburbs loaded (not 8,639 as originally expected).

**Trade-offs:** Suburbs at LGA boundaries lose their secondary LGA attribution in the suburbs table. This is acceptable — the full M:N data remains in geography_trinity.json for any future multi-LGA queries.

**Revisit when:** A scoring signal requires the secondary LGA attribution — at that point, add a `lga_name_secondary` column to suburbs.

---

### geography_trinity.json — Must Be Rebuilt If Postcodes Are Zero

**Decision:** If geography_trinity.json shows zero or near-zero postcodes populated, the Australian Postcodes CSV was not downloaded correctly in the prior geography_builder run. The fix is to delete `data/raw/abs/australian_postcodes.csv` and re-run geography_builder.

**Rationale:** Session 7 discovered that the Session 6 geography_builder run silently produced a trinity file with all postcodes missing (the CSV download error was caught and swallowed, leaving `postcode: null` for all suburbs). This caused 100% Domain 404 blocks because slugs were malformed (e.g., `adare-qld` instead of `adare-qld-4343`).

**Detection:** After geography_builder finishes, check: `jq '[.[] | select(.postcode != null)] | length' data/raw/geography_trinity.json` — should be ≥ 8,620.

**Revisit when:** ABS publishes an official SAL→POA concordance as a tabular file — replace the data.gov.au CSV with that.

---

### Deterministic Scorer — Normalisation Ranges v1.1

**Decision:** Use these normalisation ranges for the v1.1 scoring engine. All ranges are linear with hard clamp at [0, 100].

| Signal                | 0 pts (worst)   | 100 pts (best) | Rationale                                                                       |
| --------------------- | --------------- | -------------- | ------------------------------------------------------------------------------- |
| vacancy_rate          | 5% vacancy      | 0% vacancy     | SQM national avg ~1%; >5% = distressed; linear across the healthy range         |
| stock_on_market       | 500 listings    | 0 listings     | 500 = very oversupplied suburb; absolute count (v1.2: normalise per dwelling)   |
| population_growth     | 0% annual       | 3% annual      | ABS Tier 1 filter floor is 0.5%; 3% is ~top-decile national growth              |
| sales_volume_momentum | −40% YoY        | +40% YoY       | Midpoint 0% → 50pts; ±40% spans observed real-world range                       |
| relative_median       | $800k (ceiling) | $0             | Investor budget ceiling; any suburb at or above $800k scores 0 (v1.2: vs peers) |
| infra_pipeline        | 0.0 confidence  | 1.0 confidence | LLM confidence score; always None in v1.1 (scraper not built yet)               |

**Trade-offs flagged for v1.2:**

- `stock_on_market` uses absolute listing count, not per-dwelling. A large suburb with 500 listings is different from a hamlet with 500. Needs dwelling count from ABS.
- `relative_median` scores against a fixed $800k ceiling, not against neighbourhood peers. This means a $750k suburb in a $1.5M area scores the same as a $750k suburb in a $500k area. Per-suburb percentile ranking of medians would be more predictive.

**Revisit when:** Formal 30-suburb eval set run — adjust ranges based on score distribution.

---

### Deterministic Scorer — Dynamic Re-weighting

**Decision:** When a signal is missing (None), redistribute its weight proportionally across the remaining available signals. Weight sum always = 1.0.

**Implementation:** `_apply_reweighting(base_weights, missing)` computes `scale = (available_weight + missing_weight) / available_weight` and multiplies each available signal's weight by `scale`. Missing signals get effective weight 0.0. Re-weighting is logged per suburb for auditability.

**Rationale:** Missing signals are structurally expected in v1.1 — `infra_pipeline` has no scraper yet and is always None. Rural hamlets with <12 sales will have `number_sold` and `sales_volume_momentum` missing. Rather than refusing to score these suburbs or silently downscaling the total, proportional redistribution keeps the score on a 0-100 scale and reflects all available information.

**Test confirmed:** A suburb with vacancy_rate, stock_on_market, population_growth only (3 of 6 signals) produces weight sum = 1.0000 exactly.

**Revisit when:** Infra pipeline scraper is built — re-weighting will then only fire for data_thin suburbs.

---

### Signals Table — Normalised One-Row-Per-Signal Design

**Decision:** Store each signal value as a separate row in the `signals` table with columns: (suburb_name, state, postcode, signal_name, value, source, unit, scraped_at). Upsert key: (suburb_name, state, signal_name, source).

**Options considered:**

- Wide table (one column per signal per suburb) — easier to query, harder to evolve; adding a new signal requires a schema change
- Normalised row-per-signal — flexible, source-tagged, easy to add new signals without schema changes

**Rationale:** The signal set will grow (infra_pipeline, school catchments, transport access, etc.). A row-per-signal design means adding a new signal is a new data row, not a new column. The `source` column allows multiple sources to provide the same signal type independently (e.g., ABS vacancy vs SQM vacancy) for cross-validation in future.

**SQM postcode → suburb fan-out:** SQM data is postcode-level. The loader fans out one SQM record to all suburbs sharing that postcode. This is intentional — vacancy_rate for postcode 4064 applies to all suburbs in 4064 (Paddington, Milton, etc.).

**Revisit when:** Querying signals becomes slow at scale — add a materialised view or pivot for the scorer to read from.

---

## Scoring Weights History

| Version | Date      | Vacancy | Stock | Population | Infra | Sales Volume | Relative Median | Notes                                                |
| ------- | --------- | ------- | ----- | ---------- | ----- | ------------ | --------------- | ---------------------------------------------------- |
| v1.0    | Session 1 | 0.25    | 0.20  | 0.20       | 0.20  | —            | 0.15            | Initial weights                                      |
| v1.1    | Session 4 | 0.25    | 0.20  | 0.20       | 0.20  | 0.10         | 0.05            | Sales Volume Momentum added, Relative Median reduced |

> Always run 30-suburb eval set before changing weights. Log all changes here with rationale.
