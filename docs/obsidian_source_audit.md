# Obsidian Source Audit

Audit timestamp: 2026-06-19T16:11:32Z
Repository: `/home/yuu/.hermes/hermes-agent`
Active Hermes home: `/home/yuu/.hermes/profiles/engineering_lab`

## Dashboard Obsidian resolver

- Default vault path: `/home/yuu/Sync/ObsidianVault`
- Override env var: `HERMES_DASHBOARD_OBSIDIAN_VAULT`
- Backend resolver: `hermes_cli/web_server.py:_dashboard_obsidian_vault()`
- Backend parser: `hermes_cli/web_server.py:_read_dashboard_operating_note()` and `_dashboard_knowledge_vault_contract()`
- Frontend consumer: `web/src/pages/ReportsPage.tsx`

## Vault status

- Vault exists: yes
- Markdown note count: 20
- Template folders checked:
  - `/home/yuu/Sync/ObsidianVault/Templates`: missing
  - `/home/yuu/Sync/ObsidianVault/.obsidian/templates`: missing
  - `/home/yuu/Sync/ObsidianVault/Templates/Dashboard`: missing
- Files with `dashboard_area` observed: command_center, finance, research, personal, health, career_development, business_ventures, engineering_brand, artist_management, integrum_exousia_holdings

## Knowledge Vault

### Dashboard mapping

- UI section: `Knowledge Vault`
- UI source label: `Obsidian Vault`
- Backend contract: `_dashboard_knowledge_vault_contract()`
- Source: all `*.md` files under `/home/yuu/Sync/ObsidianVault`
- Output fields used by UI:
  - `recent_notes`
  - `referenced_documents`
  - `recent_decisions`
  - `knowledge_health`
  - `vault_growth_trend`

### Current source status

- Vault path exists: yes
- Total markdown notes: 20
- Dedicated folder `/home/yuu/Sync/ObsidianVault/Knowledge Vault`: missing
- Recent notes source: file mtimes for all vault markdown files
- Most referenced notes source: `[[wikilink]]` reference counts across vault markdown files
- Recent decisions source: notes containing decision headings or `decision:` text
- Knowledge health method: computed score capped at 100 from note existence, recent note count, reference count, and decision count

### Tag requirements

Knowledge Vault aggregation does not currently require tags. It scans all markdown notes. Tags such as `dashboard_source: true` and `dashboard_area` are useful metadata, but not required for this widget.

### Missing folders, notes, templates

- Missing dedicated `Knowledge Vault` folder.
- Missing dashboard-specific templates.
- No explicit template contract is enforced by code.

### Why zero values may display

If the UI displays zero for Knowledge Vault while the vault exists, likely causes are:

1. `/api/dashboard/v2` did not return `knowledge_vault` data.
2. The frontend is rendering fallback/empty contract data.
3. `HERMES_DASHBOARD_OBSIDIAN_VAULT` points elsewhere in the running server process.
4. The current UI section is using `knowledgeVaultItems.length`, where `knowledgeVaultItems` falls back to generated report titles only if `recent_notes` is empty.

The source itself is not zero: the audited vault contains 20 markdown notes.

## Engineering Brand

### Dashboard mapping

- UI section: `Engineering Brand / Content Pipeline`
- UI source label: `Knowledge Vault`
- Actual backend source: JSON registry, not Obsidian note parsing
- Backend contract: `_dashboard_engineering_brand_contract()`
- Registry resolver: `_load_dashboard_json_registry("HERMES_ENGINEERING_BRAND_REGISTRY_PATH", "engineering_brand_registry.json", _DEFAULT_ENGINEERING_BRAND_REGISTRY)`
- Current source file: `/home/yuu/.hermes/profiles/engineering_lab/dashboard/engineering_brand_registry.json`
- Override env var: `HERMES_ENGINEERING_BRAND_REGISTRY_PATH`

### Current registry contents

- File exists: yes
- Last update field: `2026-06-19T09:34:17Z`
- Pipeline values:
  - Content Ideas: 0
  - Research: 0
  - Recording: 0
  - Editing: 0
  - Scheduled: 0
  - Published: 0
- `published_count`: 0
- `active_projects`: []
- `upcoming_videos`: []

### Obsidian source observations

- `/home/yuu/Sync/ObsidianVault/Business Ventures/Engineering Brand`: exists
- Markdown note count in folder: 2
- `dashboard_area: engineering_brand` notes observed: 2
- Dedicated `/home/yuu/Sync/ObsidianVault/Engineering`: missing
- Dashboard templates: missing

### Tag requirements

The current Engineering Brand dashboard widget does not parse Obsidian tags. It reads the JSON `pipeline` values. Obsidian note metadata exists, but the pipeline counts do not derive from those notes.

### Why zero values display

Zero values display because the configured JSON registry explicitly contains zeros for every pipeline bucket. This is not an Obsidian count failure. It is partially wired: the widget has a real source, but the source has no operational content counts and is mislabeled in the UI as `Knowledge Vault`.

## Artist Management

### Dashboard mapping

- UI section: `Artist Management / Collector + Gallery Pipeline`
- UI source label: `Artist CRM`
- Backend primary source: Obsidian operating note if present; JSON fallback if missing
- Backend operating-note mapping: `_DASHBOARD_OBSIDIAN_OPERATING_NOTES["artist_management"]`
- Expected operating note: `/home/yuu/Sync/ObsidianVault/Business Ventures/Artist Management/Artist Management.md`
- JSON fallback: `/home/yuu/.hermes/profiles/engineering_lab/dashboard/artist_management_registry.json`
- Override env var for fallback registry: `HERMES_ARTIST_MANAGEMENT_REGISTRY_PATH`

### Current source status

- Expected Obsidian operating note exists: yes
- Folder `/home/yuu/Sync/ObsidianVault/Business Ventures/Artist Management`: exists
- Markdown note count in folder: 3
- `dashboard_area: artist_management` notes observed: 3
- JSON fallback file exists: no
- Dedicated `/home/yuu/Sync/ObsidianVault/Artist`: missing
- Dashboard templates: missing

### Parser expectations

The operating note parser extracts these sections:

- Vision / Summary / Overview
- Current Phase / Phase
- Objectives / Goals
- Roadmap
- Current Priorities / Priorities / Top Priorities
- Completed / Done
- Blockers / Blocked
- Risks
- Next Actions / Next Steps / Actions
- KPIs / Metrics / Success Metrics

The backend then converts section counts into generic milestone rows: Current phase, Priorities, Blockers, Risks, Next actions, KPIs.

### UI mapping issue

The frontend looks for milestone labels containing:

- Collectors
- Outreach or Gallery Outreach
- Inventory
- Active Collection
- Upcoming Events
- Revenue

The backend Obsidian operating-note parser emits generic labels such as `Priorities`, `Blockers`, `Risks`, `Next actions`, and `KPIs`. Those labels do not match the frontend labels, so the UI falls back to `0` even when the operating note exists.

### Why zero values display

Artist Management is partially wired. The Obsidian operating note exists, but the UI expects CRM-specific metric labels that the operating-note parser does not emit. The fallback JSON registry is missing, so there is no typed CRM source for collector, outreach, inventory, event, or revenue counts.

## Summary of Obsidian-dependent sections

| Section | Actual source | Folder/note status | Current dashboard status | Reason for zeros |
|---|---|---|---|---|
| Knowledge Vault | Whole Obsidian vault scan | Vault exists, 20 markdown notes | REAL if API returns data | Zeros only if API/fallback/env mismatch; source is not empty |
| Engineering Brand | JSON registry; Obsidian notes exist but are not counted | Engineering Brand folder exists with 2 notes | PARTIALLY WIRED | Registry explicitly has zeros; UI source label says Knowledge Vault but code reads JSON |
| Artist Management | Obsidian operating note, JSON fallback missing | Artist Management folder exists with 3 notes | PARTIALLY WIRED | Parser emits generic operating-note labels; frontend expects CRM-specific labels |

## Repair recommendations

1. Do not change layout. Fix data contracts only.
2. For Engineering Brand, either wire the JSON registry to an actual content pipeline update path or explicitly derive counts from tagged Obsidian notes.
3. For Artist Management, create or connect a typed CRM source for collectors, outreach, inventory, events, and revenue; do not rely on generic operating-note section counts.
4. Add dashboard templates only after the source contract is defined; current code does not require them.
5. Ensure the running server process uses `/home/yuu/Sync/ObsidianVault` or an intentional override via `HERMES_DASHBOARD_OBSIDIAN_VAULT`.
