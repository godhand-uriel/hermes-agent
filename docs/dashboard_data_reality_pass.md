# Dashboard Data Reality Pass

Audit timestamp: 2026-06-19T16:11:32Z
Repository: `/home/yuu/.hermes/hermes-agent`
Active Hermes home: `/home/yuu/.hermes/profiles/engineering_lab`

## Executive summary

Dashboard redesign work should remain stopped. The layout is sufficiently usable for the next phase. The current problem is data truth: some widgets are real, some are seeded, some are partially mapped, and quick capture is not operational.

This pass created source audits for finance, career, BureauOS, venture portfolio, Obsidian-dependent widgets, quick capture, and whole-dashboard widget truth classification.

## Documents produced

- `docs/finance_source_audit.md`
- `docs/career_registry_audit.md`
- `docs/bureauos_registry_audit.md`
- `docs/venture_portfolio_audit.md`
- `docs/obsidian_source_audit.md`
- `docs/quick_capture_audit.md`
- `docs/dashboard_truth_report.md`

## What is real

The dashboard has real source contracts and real files/databases behind several sections:

- Finance registry exists at `/home/yuu/.hermes/profiles/engineering_lab/finance/registry.db`.
- Career registry exists at `/home/yuu/.hermes/profiles/engineering_lab/dashboard/career_registry.json`.
- BureauOS application registry exists at `/home/yuu/.hermes/profiles/engineering_lab/ventures/bureauos_applications.json`.
- Venture registry exists at `/home/yuu/.hermes/profiles/engineering_lab/ventures/registry.json`.
- Obsidian vault exists at `/home/yuu/Sync/ObsidianVault` and contains 20 markdown notes.
- Engineering Brand registry exists at `/home/yuu/.hermes/profiles/engineering_lab/dashboard/engineering_brand_registry.json`.
- Kanban/task-backed sections are source-backed when `/api/dashboard/v2` is healthy.
- Knowledge Vault is source-backed by the Obsidian vault scan.

## What is fake or placeholder

The most important fake/placeholder areas are not always UI-only. Some are persisted seed/default data:

- Finance values are stored in SQLite but match the default seed pattern, not verified bank/payroll/brokerage/debt sources.
- Finance Net Worth, Emergency Fund, Car Fund, Brokerage, Debt, and Runway are all 0.0 from seed/default balances.
- Monthly Income, Monthly Expenses, and Savings Rate calculate correctly from stored values, but the stored values are seed/default values.
- BureauOS applications all exist, but current stage/progress/confidence values appear seeded/backfilled rather than evidence-backed operational status.
- Venture activity values are missing. `No Activity Yet` is an empty-state placeholder for absent activity fields.
- `Not Started` is a frontend fallback when venture data/stage/status is absent, not a reliable source value.
- Quick-capture success text is local React state only and does not mean a file/database write succeeded.

## What is missing

Missing or absent source pieces:

- Artist Management JSON fallback registry is missing at `/home/yuu/.hermes/profiles/engineering_lab/dashboard/artist_management_registry.json`.
- Dedicated Obsidian folders checked as missing:
  - `/home/yuu/Sync/ObsidianVault/Engineering`
  - `/home/yuu/Sync/ObsidianVault/Artist`
  - `/home/yuu/Sync/ObsidianVault/Knowledge Vault`
- Dashboard template folders checked as missing:
  - `/home/yuu/Sync/ObsidianVault/Templates`
  - `/home/yuu/Sync/ObsidianVault/.obsidian/templates`
  - `/home/yuu/Sync/ObsidianVault/Templates/Dashboard`
- Career registry lacks explicit certification status fields for Complete/Expired state.
- AWS Cloud Practitioner baseline is missing from the career registry.
- Venture registry lacks `latest_activity`, `latest_research`, `updated_at`, and explicit operational status fields for audited ventures.
- Quick-capture write endpoints are missing/not connected.

## What is operational

Operational, source-backed areas:

- Finance registry read/write API exists, including snapshot insertion and seed-default endpoints.
- Career roles and skill progress are readable from JSON and should display non-zero skill progress if `/api/dashboard/v2` is active.
- BureauOS application registry loads and feeds the BureauOS Overview and stage summary.
- Venture registry loads BureauOS, Parlay Analyzer, and TrustBase/Trust Base Social Platform.
- Knowledge Vault scans actual Obsidian markdown notes.
- Kanban-backed task, blockers, review, and completed-work widgets are operational if the board source is healthy.
- Operations/Hermes health widgets are generated from backend state and dashboard diagnostics.

Not operational:

- Quick Capture buttons do not write to any source.
- Engineering Brand pipeline is source-backed but operationally empty.
- Artist Management has an operating note but does not produce the CRM-specific metric labels the UI expects.
- Frontend Streaming Platform exists in the venture registry but is filtered out by the backend canonical allowlist.

## What should be fixed first

1. Verify dashboard API health and fallback status.
   - Many visible zeros or empty states are explained by `/api/dashboard/v2` failure or fallback data. Add a clear contract-level source health signal before changing widgets.

2. Mark or replace seeded finance data.
   - Current finance data is persisted but seed-derived. Do not treat it as actual net worth, balances, or debt truth until replaced with approved real snapshots.

3. Fix career certification truth.
   - Add structured certification status fields and reconcile the known baseline: Security+ Complete, Linux+ Complete, AWS Cloud Practitioner Expired.

4. Wire venture activity truth.
   - Add explicit activity/status/freshness fields or attached Kanban task rollups for BureauOS, Parlay Analyzer, and TrustBase.

5. Resolve the Frontend Streaming Platform contract mismatch.
   - It is registered in JSON, and persistent memory says it belongs in the portfolio, but current backend allowlist filters it out.

6. Wire quick capture to real write endpoints.
   - Start with New Task -> Kanban because that is the least ambiguous operational destination.
   - Do not wire New Venture to create unapproved ventures silently.

7. Fix Engineering Brand and Artist Management data contracts.
   - Engineering Brand should either derive counts from a real content pipeline or explicitly from tagged Obsidian notes.
   - Artist Management needs typed CRM metrics or a mapper from operating-note content to collector/outreach/inventory/event/revenue fields.

## Non-goals respected

- No UI redesign was performed.
- No colors, spacing, typography, themes, or layout were changed.
- No new ventures were created.
- No new registries were created.
- Existing source files/databases were audited and documented only.
