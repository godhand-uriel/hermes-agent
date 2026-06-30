# Dashboard Data Truth Report

Audit timestamp: 2026-06-19T16:11:32Z
Repository: `/home/yuu/.hermes/hermes-agent`
Active Hermes home: `/home/yuu/.hermes/profiles/engineering_lab`

Classification legend:

- REAL: source-backed and currently reading real source data.
- PLACEHOLDER: generated/default/demo value or UI-only empty state.
- BROKEN: intended source/write path does not work.
- PARTIALLY WIRED: some real source exists, but mapping/calculation is incomplete or misleading.
- MISSING SOURCE: no source file/database exists for the intended widget.

## Widget classification

| Widget / section | Source | Status | Repair recommendation |
|---|---|---|---|
| Executive Command Center shell | `GET /api/dashboard/v2`; fallback `GET /api/reports` | PARTIALLY WIRED | Keep layout. Ensure v2 errors are visible and fallback mode is unmistakable. |
| Executive Brief / Good Morning Yuu | Generated from Kanban, reports, watchdog, venture registries | PARTIALLY WIRED | Add source paths/counts per brief item so generated summaries can be traced. |
| Empire Health / Overall Operating Score | `_dashboard_health_score()` derived from finance, career, BureauOS, reports, Obsidian, brand, artist, ops | PARTIALLY WIRED | Keep as derived rollup but display component freshness/coverage before trusting the score. |
| Decisions Needed | Kanban review-required tasks + venture `decision_needed` fields | REAL | Verify Kanban status conventions and add explicit decision fields where needed. |
| Current Blockers | Kanban blocked tasks + registry `blocking_issue` fields + watchdog | REAL | Keep source-backed; add link/path to blocker source rows. |
| Activity Feed / Live Stream | Reports + Kanban + watchdog | PARTIALLY WIRED | Activity is source-backed only when reports/tasks/watchdog rows exist; avoid implying full operational coverage. |
| Mission Control / Priority Tasks | Kanban board DB | REAL | Continue using Kanban as task source; surface board name/database in diagnostics. |
| Recently Completed Work | Kanban completed tasks | REAL | Keep source-backed; add completed timestamp/source id in drawer. |
| Operations Diagnostics | Dashboard backend diagnostics | REAL | Keep; include v2/fallback state prominently. |
| Hermes Health Strip | Hermes backend/session/board metrics | REAL | Keep; validate against `state.db` and Kanban DB during operational audits. |
| Finance Command Center | SQLite finance registry `/home/yuu/.hermes/profiles/engineering_lab/finance/registry.db` | PARTIALLY WIRED | Source exists, but values are seeded defaults. Replace only with approved real finance snapshots. |
| Finance: Net Worth | `finance_snapshots.net_worth` / calculated assets minus debt | PLACEHOLDER | Current value is seed 0.0; needs real balances to become operational. |
| Finance: Monthly Income | `finance_snapshots.monthly_income` / annual income divided by 12 | PLACEHOLDER | Current 4333.33 is seed/default; verify against payroll/source before treating as real. |
| Finance: Monthly Expenses | `finance_snapshots.monthly_expenses` / seeded expense accounts | PLACEHOLDER | Current 215.0 is seeded Electric/Internet/Phone only; needs real monthly expense source. |
| Finance: Savings Rate | Finance metrics payload | PLACEHOLDER | Calculated correctly from seed values but not real until income/expense sources are real. |
| Finance: Runway | Finance metrics payload | PLACEHOLDER | Current 0.0 from seeded liquid assets; needs real balances. |
| Finance: Emergency Fund | `finance_snapshots.emergency_fund` and target | PLACEHOLDER | Current 0.0/1000 seed; needs real fund source. |
| Finance: Car Fund | `finance_snapshots.car_fund` and target | PLACEHOLDER | Current 0.0/5000 seed; needs real fund source. |
| Finance: Brokerage | `finance_snapshots.brokerage_value` | PLACEHOLDER | Current 0.0 seed; needs brokerage source. |
| Finance: Debt | `finance_snapshots.debt_total` and `debt_accounts` | PLACEHOLDER | Current 0.0 with empty accounts; needs real debt source or explicit zero-debt verification. |
| Career Command roles | Career registry JSON `/home/yuu/.hermes/profiles/engineering_lab/dashboard/career_registry.json` | REAL | Roles match baseline; keep JSON authoritative. |
| Career certifications | Same career registry JSON | PARTIALLY WIRED | Add `status`, `completed_at`, `expires_at`; reconcile Security+, Linux+, AWS Cloud Practitioner baseline. |
| Career skill progress bars | `career_registry.json.skills[].current_proficiency_percent` via `career_progress.milestones` | REAL | If UI shows 0%, debug `/api/dashboard/v2`; current JSON contains non-zero skill values. |
| BureauOS Overview | BureauOS application registry JSON `/home/yuu/.hermes/profiles/engineering_lab/ventures/bureauos_applications.json` | PARTIALLY WIRED | Required apps exist, but all data appears seeded/default. Add evidence-backed research/stage updates. |
| BureauOS stage summary | Same BureauOS application registry, grouped by stage | PARTIALLY WIRED | Stage buckets are real, but all apps are in seeded Research. Update only with source evidence. |
| Venture Portfolio: BureauOS | Venture registry JSON `/home/yuu/.hermes/profiles/engineering_lab/ventures/registry.json` | PARTIALLY WIRED | Stage/confidence/milestone are source-backed; activity/status fields missing. |
| Venture Portfolio: Parlay Analyzer | Same venture registry JSON | PARTIALLY WIRED | Same: registry row exists, but no activity/status source. |
| Venture Portfolio: TrustBase / Trust Base Social Platform | Same venture registry JSON, canonicalized through alias | PARTIALLY WIRED | Same: source row exists, but activity/status fields missing. |
| Venture Portfolio: Frontend Streaming Platform | Registry row exists but backend allowlist excludes it | BROKEN | Data contract mismatch: memory says it belongs; current backend filters it out. Decide contract then repair. |
| Venture last activity fields | Venture `latest_activity`, `latest_research`, `updated_at`, or explicit Kanban rollup | PLACEHOLDER | Current audited registry lacks activity fields; `No Activity Yet` is generated empty state. |
| Research Center | Generated reports/research report file discovery | PARTIALLY WIRED | Confirm report roots and ensure research items have canonical report files. |
| Knowledge Vault | Obsidian vault scan of `/home/yuu/Sync/ObsidianVault` | REAL | Vault exists with 20 markdown notes. If UI shows zeros, debug env/API fallback. |
| Knowledge Vault: Recent Notes | Obsidian file mtimes | REAL | No repair needed besides freshness/visibility. |
| Knowledge Vault: Most Referenced Notes | Obsidian `[[wikilink]]` counts | REAL | Add more links only through normal note-taking, not dashboard hacks. |
| Knowledge Vault: Recent Decisions | Decision headings or `decision:` text in notes | REAL | Standardize decision note format if decisions are missed. |
| Engineering Brand Content Pipeline | JSON registry `/home/yuu/.hermes/profiles/engineering_lab/dashboard/engineering_brand_registry.json` | PARTIALLY WIRED | Registry exists but all buckets are zero and UI source label says Knowledge Vault. Connect to real content workflow. |
| Artist Management / Collector + Gallery Pipeline | Obsidian operating note; JSON fallback missing | PARTIALLY WIRED | Existing note parses generic operating metrics, but UI expects CRM labels. Add typed CRM source or mapper. |
| Artist Management JSON fallback | `/home/yuu/.hermes/profiles/engineering_lab/dashboard/artist_management_registry.json` | MISSING SOURCE | Create only if approved; otherwise wire existing Obsidian note to typed metrics. |
| Quick Capture: New Task | Frontend local React state only | BROKEN | Wire to Kanban create endpoint and return task id/source path. |
| Quick Capture: New Research | Frontend local React state only | BROKEN | Wire to research note/report source. |
| Quick Capture: New Venture | Frontend local React state only | BROKEN | Wire to approved venture registry path only with governance; do not create unapproved ventures. |
| Quick Capture: New Note | Frontend local React state only | BROKEN | Wire to Obsidian note creation path/template. |
| Quick Capture: Capture Idea | Frontend local React state only | BROKEN | Wire to explicit inbox/idea source. |

## Cross-cutting truth findings

1. The dashboard is not purely fake. It has real source contracts for finance, career, BureauOS, ventures, Kanban, reports, Obsidian, and operations.
2. The most dangerous values are source-backed defaults. They look real because they come from files/databases, but several were seeded rather than operationally verified.
3. The quick-capture bar is not operational. It does not write anywhere.
4. `No Metrics Yet`, `Not Started`, and `No Activity Yet` are frontend empty states. They often mean missing API data or missing registry fields, not necessarily missing source files.
5. Obsidian exists and contains notes. Engineering Brand and Artist Management zeroes are primarily mapping/source-contract issues, not an absent vault.

## First repair priorities

1. Make `/api/dashboard/v2` source/fallback status visible in diagnostics.
2. Replace seeded finance values with approved real finance snapshots or mark seed data as seed in the UI contract.
3. Fix career certification status schema so completed/expired certifications are modeled accurately.
4. Add explicit venture activity/status fields or attached task rollups.
5. Wire quick capture to real write endpoints, starting with New Task -> Kanban.
6. Fix Engineering Brand and Artist Management data contracts without redesigning their panels.
