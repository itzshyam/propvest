# Propvest — Changelog

> What changed and when. Update at the end of any session where code, config, or architecture changes.
> AI tools: read this to understand what has recently changed before acting.

---

## Format

```
## [Version] — YYYY-MM-DD
### Added
### Changed
### Fixed
### Removed
### Notes
```

---

## [0.1.0] — 2026-04-11

### Added
- Project scaffolded — full folder structure created
- `agents.md` — AI tool behaviour rules
- `PROJECT.md` — local project index (gitignored)
- `ARCHITECTURE.md` — full technical architecture locked
- `README.md` — public GitHub intro
- `TODO.md` — session state tracking
- `DECISIONS.md` — architecture decisions + rationale
- `CONTEXT.md` — investor profile + scoring weights
- `HEARTBEAT.md` — Hermes monitoring checklist
- `CHANGELOG.md` — this file

### Notes
- Session 1 complete — whiteboard + architecture locked, scaffold in progress
- No code written yet — foundation files only
- GitHub repo not yet created
- Hermes not yet pointed at workspace

---

## [0.2.0] — 2026-04-11
### Added
- Pivoted Orchestration from n8n to Windmill.
- Defined Tiered Scraping Funnel (Tier 1 vs Tier 2).
- Added Pydantic Schema layer for data digestibility.
- Integrated Camofox for enhanced anti-bot scraping.

## [0.2.1] — 2026-04-11
### Added
- Remote GitHub repository linked.
- Multi-branch strategy initialized (`main`, `dev`).
- Successful first push to origin.

*Versions follow semantic versioning — major.minor.patch*
*Major: breaking architecture change*
*Minor: new feature or plugin added*
*Patch: bug fix, config tweak, or doc update*