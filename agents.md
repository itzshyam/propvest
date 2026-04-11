# Agent Rules — Propvest

## Session Start (ALWAYS DO FIRST)
1. Read PROJECT.md — it is the index to this project
2. Read TODO.md — understand current state before acting
3. Never assume context from previous sessions without reading these first

## Always
- Read ARCHITECTURE.md before writing any code
- Check config.yaml before adding dependencies
- Log scrape runs to scrape_log table
- Log API calls to api_cost_log table
- Score suburbs deterministically — never use LLM to compute scores
- Update TODO.md at end of every session

## Ask First
- Changing scoring weights
- Adding new plugins or data sources
- Modifying database schema
- Switching RAG or LLM provider

## Never
- Hardcode API keys (use .env)
- Import between plugins directly (use event bus)
- Let LLM compute a suburb score
- Commit .env file
- Use LLM when a deterministic answer exists
- Modify plugin interfaces without updating base class