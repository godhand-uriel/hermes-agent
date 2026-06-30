# Hermes Dashboard Source Map

Purpose: map every Executive Command Center dashboard widget/section to its real source path and update/repair workflow.

Scope: documentation only. This file does not change UI behavior, API contracts, source selection, or data sources.

Verified repository root: `/home/yuu/.hermes/hermes-agent`

Primary dashboard frontend:

- Page: `web/src/pages/ReportsPage.tsx`
- Primary API client: `web/src/lib/api.ts`
- Primary endpoint: `GET /api/dashboard/v2`
- Backend endpoint implementation: `hermes_cli/web_server.py:get_dashboard_v2()`
- Legacy/fallback endpoint: `GET /api/reports`
- Fallback builder in frontend: `buildFallbackDashboard(createEmptyReports(project, query))`

Important runtime roots:

- Active profile Hermes home: `get_hermes_home()` -> usually `$HERMES_HOME`; in this verified session it resolved to `/home/yuu/.hermes/profiles/engineering_lab`.
- Shared Kanban home: `hermes_cli.kanban_db.kanban_home()` -> `HERMES_KANBAN_HOME` if set, otherwise default Hermes root; in this verified session it resolved to `/home/yuu/.hermes`.
- Default Kanban DB: `<kanban_home>/kanban.db`.
- Named board DB: `<kanban_home>/kanban/boards/<board-slug>/kanban.db`.
- Dashboard JSON registries: `<get_hermes_home()>/dashboard/*.json`, unless overridden by the specific `HERMES_*_REGISTRY_PATH` env var.
- Obsidian vault: `HERMES_DASHBOARD_OBSIDIAN_VAULT` or `/home/yuu/Sync/ObsidianVault`.

Source type legend:

- SQLite: values read from SQLite databases.
- JSON: values read from local JSON registry files.
- Kanban: values read from Kanban SQLite board tables.
- Obsidian: values parsed from Markdown files under the Obsidian vault.
- Generated API data: values computed at request time from one or more sources and returned by an API contract; may not have a single persisted file.

## End-to-end data flow

1. `ReportsPage.tsx` calls `api.getDashboardV2(...)`.
2. `api.getDashboardV2` builds `GET /api/dashboard/v2?...` in `web/src/lib/api.ts`.
3. `hermes_cli/web_server.py:get_dashboard_v2()` creates `_dashboard_empty_contract()`, overlays registry/note data, queries Kanban/session/finance/report sources, computes derived metrics, and returns the v2 contract.
4. If v2 loading fails, `ReportsPage.tsx` falls back to legacy `GET /api/reports` and builds an honest empty/fallback dashboard.

## Source map by dashboard widget / section

### Executive Command Center shell

- Widget/section name: Executive Command Center
- UI source: `web/src/pages/ReportsPage.tsx`; top-level dashboard section starts at `section id="dashboard-top"`; title text is rendered in the executive page body rather than the global header.
- API endpoint: `GET /api/dashboard/v2`; fallback `GET /api/reports`.
- Backend function/file: `hermes_cli/web_server.py:get_dashboard_v2()`; fallback `get_reports()`.
- Database/file path: none directly; shell state is generated API data from the v2 contract plus frontend local state.
- Source type: generated API data.
- How it updates: on page load/filter changes when the frontend fetches `/api/dashboard/v2`; no independent persisted source.
- Manual verify: open Reports dashboard and confirm loading/error/empty states; or inspect source for `Loading Hermes OS Executive Command Center`, `Dashboard data failed to load`, `No Activity Yet`, and `No Data Yet`.
- Seed/repair: repair underlying source sections below. If the shell fails, verify the dashboard server and `/api/dashboard/v2` first.

### Executive Brief / Good Morning Yuu

- Widget/section name: Good Morning Yuu / Executive Brief
- UI source: `web/src/pages/ReportsPage.tsx`, `ExecutivePanel` with eyebrow `Executive Brief`, title `Good Morning Yuu`, source label `Kanban + Reports + Watchdog`.
- API endpoint: `GET /api/dashboard/v2`.
- Backend function/file: `hermes_cli/web_server.py:get_dashboard_v2()` populates `executive_briefing`; `_dashboard_executive_brief_source()` derives `changes_since_last_run`, `today_priorities`, `decisions_needed`, `blockers`, `risks`, `next_actions`, and `wins`.
- Database/file path:
  - Kanban task rows: default board `<kanban_home>/kanban.db` or named board `<kanban_home>/kanban/boards/<slug>/kanban.db`.
  - Report files: `HERMES_REPORTS_DIR`, `<kanban_home>/reports`, `<kanban_home>/kanban/reports`, `<get_hermes_home()>/reports`, and `<kanban_home>/kanban/boards/*/reports` when those directories exist.
  - Notification watchdog audit DB: `<kanban_home>/notification_watchdog/remediations.db`.
  - Venture registry: `<get_hermes_home()>/ventures/registry.json` unless `HERMES_VENTURE_REGISTRY_PATH` is set.
  - BureauOS application registry: `<get_hermes_home()>/ventures/bureauos_applications.json` unless `HERMES_BUREAUOS_APPLICATION_REGISTRY_PATH` is set.
- Source type: generated API data derived from Kanban + report files + notification watchdog SQLite + JSON registries.
- How it updates: Kanban task changes, report file writes, watchdog audits, and registry edits are reflected on next `/api/dashboard/v2` fetch.
- Manual verify: call `/api/dashboard/v2` and inspect `executive_briefing` and `executive_brief_source`; inspect source rows/files listed above.
- Seed/repair: create/update Kanban tasks, add report files under a searched report root, run the notification watchdog, and repair JSON registries described below.

### Empire Health / Overall Operating Score

- Widget/section name: Empire Health / Overall Operating Score
- UI source: `web/src/pages/ReportsPage.tsx`, `ExecutivePanel` eyebrow `Empire Health`, title `Overall Operating Score`.
- API endpoint: `GET /api/dashboard/v2`.
- Backend function/file: `hermes_cli/web_server.py:_dashboard_health_score(response)`.
- Database/file path: no separate file; combines finance registry, career registry, BureauOS application registry, generated reports, Obsidian vault, engineering brand registry, artist management registry, Kanban board/session metrics.
- Source type: generated API data.
- How it updates: recalculated on every `/api/dashboard/v2` response from current component metrics.
- Manual verify: inspect `/api/dashboard/v2.empire_health.components`; compare component values to their source sections.
- Seed/repair: repair the component source with the low score; this score has no direct seed path.

### Decisions Needed

- Widget/section name: Decisions Needed
- UI source: `web/src/pages/ReportsPage.tsx`, `ExecutivePanel` eyebrow `Decision Queue`, title `Decisions Needed`, source label `Kanban review queue`.
- API endpoint: `GET /api/dashboard/v2`.
- Backend function/file: `hermes_cli/web_server.py:get_dashboard_v2()` builds `review_required`; `_dashboard_executive_brief_source()` builds `decisions_needed` from review-required Kanban tasks and `decision_needed` fields in registered ventures.
- Database/file path:
  - Kanban task DB: `<kanban_home>/kanban.db` or `<kanban_home>/kanban/boards/<slug>/kanban.db`.
  - Venture registry: `<get_hermes_home()>/ventures/registry.json` unless overridden.
- Source type: Kanban + JSON + generated API data.
- How it updates: Kanban task status/comment/body/result changes to review-required states; venture registry edits with `decision_needed`.
- Manual verify: query `/api/dashboard/v2` and inspect `executive_briefing.review_required_tasks` plus `executive_briefing.decisions_needed`; inspect matching Kanban `tasks` rows and registry entries.
- Seed/repair: mark/create Kanban tasks with status `review` or text containing `review-required`; add `decision_needed` to a registered venture JSON entry.

### Current Blockers

- Widget/section name: Current Blockers
- UI source: `web/src/pages/ReportsPage.tsx`, `ExecutivePanel` eyebrow `Blockers`, title `Current Blockers`, source label `Kanban + Notifications`.
- API endpoint: `GET /api/dashboard/v2`.
- Backend function/file: `hermes_cli/web_server.py:get_dashboard_v2()` builds `blocked_tasks`; `_dashboard_executive_brief_source()` adds Kanban blocked tasks and `blocking_issue` fields from venture/BureauOS registries.
- Database/file path:
  - Kanban task DB: `<kanban_home>/kanban.db` or named board DB.
  - Venture registry: `<get_hermes_home()>/ventures/registry.json` unless overridden.
  - BureauOS application registry: `<get_hermes_home()>/ventures/bureauos_applications.json` unless overridden.
  - Notification watchdog audit DB: `<kanban_home>/notification_watchdog/remediations.db` for notification health.
- Source type: Kanban + JSON + generated API data.
- How it updates: Kanban tasks move to `blocked`; JSON registry fields `blocking_issue` change; watchdog audit updates.
- Manual verify: inspect `/api/dashboard/v2.executive_briefing.blocked_tasks`, `.blockers`, and `.notification_watchdog`.
- Seed/repair: unblock or update Kanban tasks; edit registry `blocking_issue`; run watchdog in detect/repair mode if notification-related.

### Activity Feed / Live Stream

- Widget/section name: Activity Feed
- UI source: `web/src/pages/ReportsPage.tsx`, `ExecutivePanel` eyebrow `Live Stream`, title `Activity Feed`, source label `Reports + Kanban + Watchdog`.
- API endpoint: `GET /api/dashboard/v2`.
- Backend function/file: `hermes_cli/web_server.py:get_dashboard_v2()`, `_collect_report_files()`, `_dashboard_collect_kanban()`, `latest_watchdog_status()`.
- Database/file path: Kanban DB, report roots, watchdog audit DB.
- Source type: Kanban + generated API data + report files.
- How it updates: next API fetch after task/report/watchdog changes.
- Manual verify: inspect `executive_briefing.changes_since_last_run`, `completed_tasks`, and `notification_watchdog` in `/api/dashboard/v2`.
- Seed/repair: add/complete Kanban tasks, write report files into a searched report root, or run watchdog.

### Mission Control / P0-P1 Operating Flow

- Widget/section name: Mission Control / P0-P1 Operating Flow
- UI source: `web/src/pages/ReportsPage.tsx`, div `id="mission-control"`; metric tiles `P0/P1 Priorities`, `Due Today`, `Review Required`, `Blocked`; task list links use `kanbanTaskHref(task.id)`.
- API endpoint: `GET /api/dashboard/v2`; fallback `GET /api/reports`.
- Backend function/file: `hermes_cli/web_server.py:_dashboard_collect_kanban()`, `_dashboard_task_item()`, `get_dashboard_v2()`.
- Database/file path: Kanban SQLite `tasks`, `task_runs`, and `task_comments` tables in the resolved board DB.
- Source type: Kanban / SQLite.
- How it updates: any Kanban task creation/status/priority/assignee/run/comment update reflected on next dashboard fetch.
- Manual verify: inspect `/api/dashboard/v2.executive_briefing.top_priorities`, `.review_required_tasks`, `.blocked_tasks`, and `.board_health`; compare to SQL rows in the board DB.
- Seed/repair: use Kanban CLI/API to create tasks, assign, block/unblock, or move tasks to review/done. If DB missing, initialize Kanban board with Hermes Kanban commands.

### Board Health / sidebar task counters

- Widget/section name: Sidebar metrics `P0 Tasks`, `Blocked`, `Review`, `Agents`; board health counters.
- UI source: `web/src/pages/ReportsPage.tsx`, sidebar metric tiles near `dashboard-top`.
- API endpoint: `GET /api/dashboard/v2`.
- Backend function/file: `hermes_cli/web_server.py:get_dashboard_v2()` populates `board_health` from `_dashboard_collect_kanban()` and `agent_metrics` from `_dashboard_collect_session_metrics()`.
- Database/file path:
  - Kanban board DB for task counts.
  - Session store SQLite: `<get_hermes_home() or profile home>/state.db` via `hermes_state.SessionDB()`.
- Source type: Kanban SQLite + session SQLite + generated API data.
- How it updates: task and session writes update source DBs; dashboard recalculates on fetch.
- Manual verify: compare `/api/dashboard/v2.board_health` to Kanban task status counts; compare `/api/dashboard/v2.agent_metrics` to session DB aggregates.
- Seed/repair: repair Kanban board data or session store; no separate dashboard seed.

### Business Ventures / Registered Venture Command / Venture Portfolio

- Widget/section name: Business Ventures / Registered Venture Command / Venture Portfolio
- UI source: `web/src/pages/ReportsPage.tsx`, div `id="venture-portfolio"`, `VentureRows`.
- API endpoint: `GET /api/dashboard/v2`; generated detail also uses `GET /api/reports/generated/latest/venture_portfolio_rank`.
- Backend function/file: `hermes_cli/web_server.py:_load_venture_registry()`, `_dashboard_registered_ventures()`, `_dashboard_venture_pipeline()`, `_generated_venture_portfolio_rank_envelope()`.
- Database/file path:
  - Venture registry JSON: `HERMES_VENTURE_REGISTRY_PATH` or `<get_hermes_home()>/ventures/registry.json`.
  - Optional Kanban rollup: resolved board DB task rows only roll up when a task explicitly matches a registered venture id/name/alias.
- Source type: JSON + Kanban rollup + generated API data.
- How it updates: edit the venture registry JSON; add explicit venture references in Kanban task `tenant`, `session_id`, or body line `Venture: ...`; refetch dashboard.
- Manual verify: inspect `/api/dashboard/v2.venture_registry`, `.portfolio_ventures`, `.portfolio_health`, and `.dashboard_sources.venture_registry`.
- Seed/repair: create/fix `<get_hermes_home()>/ventures/registry.json` or set `HERMES_VENTURE_REGISTRY_PATH`; include a top-level `ventures` array. Current code only accepts canonical ids/aliases for `bureauos`, `parlay-analyzer`, and `trustbase` (`Trust Base Social Platform` alias is added for TrustBase). Non-canonical items are ignored by the current backend.

### BureauOS Overview

- Widget/section name: BureauOS Overview
- UI source: `web/src/pages/ReportsPage.tsx`, div `id="bureauos"`, `BureauOSRows`.
- API endpoint: `GET /api/dashboard/v2`.
- Backend function/file: `hermes_cli/web_server.py:_bureauos_application_registry_path()`, `_load_bureauos_application_registry()`.
- Database/file path: `HERMES_BUREAUOS_APPLICATION_REGISTRY_PATH` or `<get_hermes_home()>/ventures/bureauos_applications.json`.
- Source type: JSON.
- How it updates: edit the BureauOS application registry JSON and refetch dashboard. If no explicit env override is set, missing default applications are auto-created/backfilled by the backend.
- Manual verify: inspect `/api/dashboard/v2.bureauos_applications` and `.bureauos_application_registry.source`.
- Seed/repair: remove a bad non-explicit file and let the backend backfill defaults, or create JSON with an `applications` list. Current accepted applications are DMV Navigator, Veteran Benefits Navigator, Insurance Denial Navigator, Tenant Rights Navigator, and Small Business Compliance Navigator under parent venture BureauOS.

### Venture Pipeline / Stage Summary

- Widget/section name: Venture Pipeline / Stage Summary
- UI source: `web/src/pages/ReportsPage.tsx`, div `id="venture-pipeline"`, `CompactStageSummary`.
- API endpoint: `GET /api/dashboard/v2`.
- Backend function/file: `hermes_cli/web_server.py:_dashboard_venture_pipeline()`.
- Database/file path: BureauOS application registry JSON: `HERMES_BUREAUOS_APPLICATION_REGISTRY_PATH` or `<get_hermes_home()>/ventures/bureauos_applications.json`.
- Source type: JSON + generated API data.
- How it updates: stage changes in the BureauOS application registry recalculate stage counts on next fetch.
- Manual verify: inspect `/api/dashboard/v2.venture_pipeline.stages` and `.items`.
- Seed/repair: repair BureauOS application registry. Accepted stage buckets are Research, Validation, MVP, Build, Production, Paying Clients, and Scale.

### Engineering Brand / Content Pipeline

- Widget/section name: Engineering Brand / Content Pipeline
- UI source: `web/src/pages/ReportsPage.tsx`, div `id="engineering-brand"`, source label currently says `Knowledge Vault`; data comes from `dashboard.engineeringMetrics.metrics`.
- API endpoint: `GET /api/dashboard/v2`.
- Backend function/file: `hermes_cli/web_server.py:_dashboard_engineering_brand_contract()` and `get_dashboard_v2()` copying its `metrics` into `engineering_metrics`.
- Database/file path: `HERMES_ENGINEERING_BRAND_REGISTRY_PATH` or `<get_hermes_home()>/dashboard/engineering_brand_registry.json`.
- Source type: JSON registry, plus generated Kanban-derived engineering counters.
- How it updates: edit `engineering_brand_registry.json`; dashboard also recalculates completed/review/blocked/active/test counters from Kanban tasks on fetch.
- Manual verify: inspect `/api/dashboard/v2.engineering_brand`, `/api/dashboard/v2.engineering_metrics`, and `/api/dashboard/v2.dashboard_sources.engineering_brand_registry`.
- Seed/repair: create JSON with `pipeline`, `upcoming_videos`, `published_count`, and `active_projects`; if no explicit env override is set, backend seeds an empty default registry.

### Finance / Finance Command Center

- Widget/section name: Finance Command Center
- UI source: `web/src/pages/ReportsPage.tsx`, div `id="finance-command"`; visible cards are Net Worth, Emergency Fund, Monthly Burn, Runway, AI Cost, Revenue.
- API endpoint: `GET /api/dashboard/v2`; finance-specific endpoints are `GET /api/finance`, `GET /api/finance/widgets`, `GET /api/finance/trends/{metric}`, `POST /api/finance/snapshots`, and `POST /api/finance/seed-defaults`.
- Backend function/file: `hermes_cli/web_server.py:get_dashboard_v2()` calls `hermes_cli.finance_registry.dashboard_financial_metrics()`; finance endpoints call `finance_command_center_contract()`, `finance_history()`, `insert_finance_snapshot()`, and `seed_default_finance_registry()` in `hermes_cli/finance_registry.py`.
- Database/file path: `HERMES_FINANCE_REGISTRY_PATH` or `<get_hermes_home()>/finance/registry.db`, table `finance_snapshots`.
- Source type: SQLite; AI usage cost is generated from session SQLite metrics.
- How it updates: `POST /api/finance/snapshots` inserts a snapshot; `POST /api/finance/seed-defaults` inserts approved defaults; dashboard v2 currently calls `dashboard_financial_metrics()`, which seeds defaults automatically if the finance registry is uninitialized.
- Manual verify: inspect `/api/dashboard/v2.financial_metrics`, `/api/finance`, `/api/finance/widgets`, and `finance_snapshots` in the registry DB.
- Seed/repair: call `POST /api/finance/seed-defaults`; repair schema by running finance registry code path, which creates/alters the `finance_snapshots` table; insert a corrected snapshot through `POST /api/finance/snapshots`.

### Career / Career Command

- Widget/section name: Career Command / Career Development
- UI source: `web/src/pages/ReportsPage.tsx`, div `id="career-development"`; progress bars are driven by `dashboard.careerProgress.milestones`, while three role tiles are currently static literals in the UI.
- API endpoint: `GET /api/dashboard/v2`.
- Backend function/file: `hermes_cli/web_server.py:_dashboard_career_registry_contract()`, `_dashboard_collect_obsidian_operating_notes()`, `_read_dashboard_operating_note()`.
- Database/file path:
  - Career registry JSON: `HERMES_CAREER_REGISTRY_PATH` or `<get_hermes_home()>/dashboard/career_registry.json`.
  - Optional Obsidian operating note: `<obsidian_vault>/Career Development/Career Development.md`.
- Source type: JSON primary; Obsidian note can enrich/override narrative fields when present.
- How it updates: edit career registry JSON and/or the Obsidian operating note; refetch dashboard.
- Manual verify: inspect `/api/dashboard/v2.career_progress` and `/api/dashboard/v2.dashboard_sources.career_registry`.
- Seed/repair: if no explicit env override is set, backend creates a default career registry. Ensure JSON contains `current_role`, `target_role`, `future_role`, `certifications`, `skills`, and `roadmap_progress_percent`.

### Research / Research Center

- Widget/section name: Research Center
- UI source: `web/src/pages/ReportsPage.tsx`, div `id="research-center"`; tiles are Market Intelligence, Competitive Intelligence, Open Questions, Recent Findings, and Opportunities.
- API endpoint: `GET /api/dashboard/v2`; generated report detail endpoints under `/api/reports/generated/*`.
- Backend function/file: `hermes_cli/web_server.py:_generated_reports_contract()`, `_collect_generated_report_files()`, `_extract_generated_report_file()`, `_dashboard_knowledge_vault_contract()`.
- Database/file path:
  - Generated/report files in report roots searched by `_iter_report_roots()`.
  - Obsidian vault Markdown under `HERMES_DASHBOARD_OBSIDIAN_VAULT` or `/home/yuu/Sync/ObsidianVault`; research count is derived from Markdown paths containing `research`.
- Source type: generated report files + Obsidian Markdown + generated API data.
- How it updates: write generated reports or research Markdown notes; dashboard recalculates on fetch.
- Manual verify: inspect `/api/dashboard/v2.generated_reports`, `/api/dashboard/v2.knowledge_vault.research_reports`, and report files in searched roots.
- Seed/repair: add generated report files with recognized type aliases, or add Markdown notes under the Obsidian vault. Generated report types currently recognized are `morning_brief`, `evening_report`, `weekly_executive_review`, `monthly_executive_review`, `venture_portfolio_rank`, and `blocked_tasks_review`.

### Knowledge Vault

- Widget/section name: Knowledge Vault
- UI source: `web/src/pages/ReportsPage.tsx`, div `id="knowledge-vault"`; tiles include Recently Modified Notes, Most Referenced Notes, Recent Decisions, and Knowledge Health.
- API endpoint: `GET /api/dashboard/v2`.
- Backend function/file: `hermes_cli/web_server.py:_dashboard_knowledge_vault_contract()`.
- Database/file path: Obsidian vault from `HERMES_DASHBOARD_OBSIDIAN_VAULT` or `/home/yuu/Sync/ObsidianVault`; all `*.md` files are scanned.
- Source type: Obsidian Markdown.
- How it updates: create/edit Markdown files in the vault; dashboard scans the vault on each v2 fetch.
- Manual verify: inspect `/api/dashboard/v2.knowledge_vault.source`, `.total_notes`, `.recent_notes`, `.recent_decisions`, `.referenced_documents`, `.knowledge_health`, and `.vault_growth_trend`.
- Seed/repair: set `HERMES_DASHBOARD_OBSIDIAN_VAULT` to an existing vault; add Markdown notes; add headings like `# Decisions` or text `decision:` for decision detection; use Obsidian wiki links `[[Target]]` for reference counts.

### Artist Management / Collector + Gallery Pipeline

- Widget/section name: Artist Management / Collector + Gallery Pipeline
- UI source: `web/src/pages/ReportsPage.tsx`, div `id="artist-management"`; cards read `dashboard.artistManagement.milestones`.
- API endpoint: `GET /api/dashboard/v2`.
- Backend function/file: `hermes_cli/web_server.py:_dashboard_artist_management_contract()`, `_dashboard_collect_obsidian_operating_notes()`, `_read_dashboard_operating_note()`.
- Database/file path:
  - Artist registry JSON: `HERMES_ARTIST_MANAGEMENT_REGISTRY_PATH` or `<get_hermes_home()>/dashboard/artist_management_registry.json`.
  - Optional Obsidian operating note: `<obsidian_vault>/Business Ventures/Artist Management/Artist Management.md`.
- Source type: JSON primary; Obsidian operating note when present.
- How it updates: edit artist management registry JSON and/or Obsidian note; refetch dashboard.
- Manual verify: inspect `/api/dashboard/v2.artist_management` and `/api/dashboard/v2.dashboard_sources.artist_management_registry`.
- Seed/repair: if no explicit env override is set, backend creates an empty default registry. Ensure JSON fields include `collectors`, `gallery_outreach`, `inventory`, `active_collections`, `upcoming_exhibitions`, and `revenue`.

### Hermes Operations / Hermes Health Strip

- Widget/section name: Hermes Operations / Hermes Health Strip
- UI source: `web/src/pages/ReportsPage.tsx`, div `id="hermes-operations"`, `OperationsHealthStrip`.
- API endpoint: `GET /api/dashboard/v2`; related analytics endpoints include `GET /api/analytics/usage` and `GET /api/analytics/models`.
- Backend function/file: `hermes_cli/web_server.py:_dashboard_collect_session_metrics()`, `get_dashboard_v2()`, `get_usage_analytics()`, `get_models_analytics()`.
- Database/file path: Hermes session SQLite via `hermes_state.SessionDB()`, typically `<get_hermes_home()>/state.db` for the active profile; Kanban board DB contributes board health diagnostics.
- Source type: SQLite + generated API data.
- How it updates: new Hermes sessions/messages/tool calls/cost fields are persisted by the session store; task board changes update Kanban diagnostics; dashboard recalculates on fetch.
- Manual verify: inspect `/api/dashboard/v2.provider_model_health`, `.agent_metrics`, `.board_health`, `/api/analytics/usage`, and `/api/analytics/models`.
- Seed/repair: no dashboard seed. Repair the session DB or run Hermes activity to generate session rows; repair Kanban board if board diagnostics are empty or incorrect.

### Weekly Reports / Report Library

- Widget/section name: Weekly reports / report library entries used by Activity/Reports views
- UI source: `web/src/pages/ReportsPage.tsx`; report links use `reportDetailHref(report)`.
- API endpoint: `GET /api/dashboard/v2` (`weekly_reports`) and fallback `GET /api/reports`.
- Backend function/file: `hermes_cli/web_server.py:_iter_report_roots()`, `_collect_report_files()`, `_extract_report_file()`, `get_reports()`.
- Database/file path: report roots searched in this order when they exist:
  - `HERMES_REPORTS_DIR`
  - `<kanban_home>/reports`
  - `<kanban_home>/kanban/reports`
  - `<get_hermes_home()>/reports`
  - `<kanban_home>/kanban/boards/*/reports`
- Source type: Markdown/text/JSON report files exposed as generated API data.
- How it updates: add/edit `.md`, `.txt`, or `.json` files in a searched report root. Generic library excludes files under `reports/generated/**`.
- Manual verify: inspect `/api/dashboard/v2.weekly_reports.latest` and `/api/reports`.
- Seed/repair: create a report file whose filename includes `report`, `qa`, `deploy`, or `github`, or whose contents classify it through `_extract_report_file()`.

### Generated Reports / readable detail views

- Widget/section name: Generated reports and generated report detail views
- UI source: `web/src/pages/ReportsPage.tsx`; generated report links use `generatedReportDetailHref(entry.type)` and readable detail uses `buildReadableReport(report)`.
- API endpoint: `GET /api/reports/generated`, `GET /api/reports/generated/status`, `GET /api/reports/generated/latest/{report_type}`, `GET /api/reports/generated/history/{report_type}`; latest generated reports are also embedded in `GET /api/dashboard/v2.generated_reports`.
- Backend function/file: `hermes_cli/web_server.py:_GENERATED_REPORT_TYPES`, `_collect_generated_report_files()`, `_extract_generated_report_file()`, `_build_readable_generated_report_content()`, `_generated_reports_contract()`.
- Database/file path: generated report files under the same report roots as the report library, usually under a `generated` subdirectory but not required by the collector.
- Source type: Markdown/text/JSON files + generated API data.
- How it updates: write a report file with a recognized report type/alias or JSON payload `type`, `report_type`, or `slug`.
- Manual verify: call `/api/reports/generated/status` and `/api/reports/generated/latest/<type>`; inspect readable content for `Key wins`, `Risks / blockers`, `Recommendations`, `Next actions`, `Related missions / tasks`, and `Developer raw JSON` in frontend detail.
- Seed/repair: add a valid generated report JSON/Markdown file in a searched report root; for venture portfolio rank, `_generated_venture_portfolio_rank_envelope()` can synthesize the latest report from the venture registry without a persisted report file.

### Notification Watchdog

- Widget/section name: Notification watchdog status / diagnostics used by Executive Brief, Current Blockers, Activity Feed, and Hermes Operations.
- UI source: `web/src/pages/ReportsPage.tsx`; operations diagnostics drawer and activity/feed cards consume watchdog fields.
- API endpoint: `GET /api/dashboard/v2`.
- Backend function/file: `hermes_cli/web_server.py:get_dashboard_v2()` calls `hermes_cli.kanban_notification_watchdog.latest_watchdog_status()`; watchdog implementation is `hermes_cli/kanban_notification_watchdog.py`.
- Database/file path:
  - Audit DB: `<kanban_home>/notification_watchdog/remediations.db` unless `WatchdogConfig.audit_db_path` is supplied.
  - Scanned board DBs: `<kanban_home>/kanban/boards/{command-center-board,career-development-board,engineering-brand-board,artist-management-board,venture-portfolio-board,research-office-board}/kanban.db` by default.
- Source type: SQLite + Kanban.
- How it updates: run watchdog CLI/function in `detect`, `dry-run`, `repair-safe`, or `repair-cleanup` mode; audit tables update status/history.
- Manual verify: inspect `/api/dashboard/v2.notification_watchdog` and audit tables `notification_watchdog_runs`, `notification_watchdog_findings`, `notification_watchdog_remediations`, and `notification_watchdog_state`.
- Seed/repair: run `hermes_cli.kanban_notification_watchdog` CLI with an explicit target/config; repair-safe mode can create missing notification subscriptions when configured.

## Manual verification commands

Run from repository root with the same environment/profile as the dashboard server:

```bash
# Confirm primary frontend/API/backend files exist.
test -f web/src/pages/ReportsPage.tsx
test -f web/src/lib/api.ts
test -f hermes_cli/web_server.py
test -f hermes_cli/finance_registry.py
test -f hermes_cli/kanban_db.py
test -f hermes_cli/kanban_notification_watchdog.py

# Confirm primary endpoint and API client references.
grep -n 'getDashboardV2' web/src/lib/api.ts
grep -n '@app.get("/api/dashboard/v2")' hermes_cli/web_server.py
grep -n 'def get_dashboard_v2' hermes_cli/web_server.py

# Confirm dashboard section labels are still present in the React page.
grep -n 'Mission Control\|Empire Health\|Decisions Needed\|Current Blockers\|Career Command\|BureauOS Overview\|Registered Venture Command\|Stage Summary\|Content Pipeline\|Finance Command Center\|Research Center\|Knowledge Vault\|Collector + Gallery Pipeline\|Hermes Health Strip' web/src/pages/ReportsPage.tsx

# Confirm source path resolution in a profile-aware way.
PYTHONPATH=. python3 - <<'PY'
from hermes_cli.config import get_hermes_home
from hermes_constants import get_default_hermes_root
from hermes_cli.finance_registry import finance_registry_path
from hermes_cli import kanban_db
import os
print('hermes_home=', get_hermes_home())
print('default_root=', get_default_hermes_root())
print('kanban_home=', kanban_db.kanban_home())
print('default_kanban_db=', kanban_db.kanban_db_path(board='default'))
print('command_center_kanban_db=', kanban_db.kanban_db_path(board='command-center-board'))
print('finance_registry=', finance_registry_path())
print('obsidian_vault=', os.environ.get('HERMES_DASHBOARD_OBSIDIAN_VAULT', '/home/yuu/Sync/ObsidianVault'))
PY
```

## Existing tests that protect this map

- `tests/hermes_cli/test_reports_dashboard_smoke_contract.py`: required executive dashboard section labels, loading/error/empty states, route helper expectations, generated report readability expectations, hidden header contract.
- `tests/hermes_cli/test_reports_page_executive_homepage.py`: executive homepage/dashboard rendering contract.
- `tests/hermes_cli/test_monthly_executive_report_contract.py`: generated/monthly report contract.
- `tests/hermes_cli/test_finance_registry.py`: finance registry schema/contract behavior.
- `tests/hermes_cli/test_web_server.py`: web server/API behavior, including dashboard-related contracts where present.
- `tests/hermes_cli/test_dashboard_navigation_contract.py`: dashboard navigation contract.

## Repair checklist by source type

- SQLite / Kanban: initialize or repair the Kanban board with Hermes Kanban commands; inspect the resolved board DB path; verify required tables `tasks`, `task_runs`, `task_comments`, `task_events`, and `kanban_notify_subs` where relevant.
- SQLite / Finance: call `POST /api/finance/seed-defaults` or insert a corrected snapshot with `POST /api/finance/snapshots`; verify `<get_hermes_home()>/finance/registry.db` table `finance_snapshots`.
- SQLite / Session metrics: verify active profile `state.db` and session rows; generate real Hermes activity if the dashboard is empty.
- JSON registries: repair valid JSON and expected top-level fields; remove bad auto-seeded files only when no explicit env override is set so backend can recreate defaults.
- Obsidian: set `HERMES_DASHBOARD_OBSIDIAN_VAULT` to an existing vault; repair Markdown filenames/sections/links.
- Report files: put `.md`, `.txt`, or `.json` files into one of the searched report roots; use recognized generated report type aliases for generated reports.
- Generated API data: repair the upstream source, then refetch `/api/dashboard/v2`; generated values do not have direct persisted files.
