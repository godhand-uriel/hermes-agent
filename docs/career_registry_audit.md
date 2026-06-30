# Career Registry Audit & Expansion

Audit timestamp: 2026-06-29T21:42:53Z
Repository: `/home/yuu/.hermes/hermes-agent`
Active Hermes home: `/home/yuu/.hermes/profiles/engineering_lab`

## Executive summary

There is exactly one implemented Career Registry in the current Hermes OS dashboard stack:

`/home/yuu/.hermes/profiles/engineering_lab/dashboard/career_registry.json`

The registry is JSON, not SQLite. Career Command must remain a presentation layer over `GET /api/dashboard/v2.career_progress`; it must not introduce a second career file, frontend fixture, or parallel schema. This pass extended the existing JSON shape in place with null/empty placeholders for missing Career Command fields and updated the dashboard contract to serialize registry fields through the existing API.

No career facts were fabricated. Newly added unknown values are `null` or `[]`, causing the UI to render `Needs input: <field>`.

## Architecture diagram

```text
                   optional narrative only
/home/yuu/Sync/ObsidianVault/Career Development/Career Development.md
                   │
                   │ parsed by _read_dashboard_operating_note()
                   ▼
┌──────────────────────────────────────────────────────────────────┐
│ Single source of truth for structured career facts                 │
│ /home/yuu/.hermes/profiles/engineering_lab/dashboard/career_registry.json │
└──────────────────────────────────────────────────────────────────┘
                   │
                   │ HERMES_CAREER_REGISTRY_PATH may override path
                   ▼
hermes_cli/web_server.py
  _load_dashboard_json_registry(..., "career_registry.json", _DEFAULT_CAREER_REGISTRY)
  _dashboard_career_registry_contract()
  _dashboard_collect_obsidian_operating_notes()
                   │
                   ▼
GET /api/dashboard/v2
  career_progress
  dashboard_sources.career_registry
                   │
                   ▼
web/src/pages/ReportsPage.tsx
  operatingNoteFromApi(data.career_progress)
  CareerCommandConsole({ career: dashboard.careerProgress })
```

## Registry inventory

| Item | Current state |
|---|---|
| Registry location | `/home/yuu/.hermes/profiles/engineering_lab/dashboard/career_registry.json` |
| Storage format | JSON object with top-level career fields plus `certifications[]` and `skills[]` arrays |
| Resolver | `hermes_cli/web_server.py:_dashboard_registry_path()` |
| Loader | `hermes_cli/web_server.py:_load_dashboard_json_registry()` |
| Env override | `HERMES_CAREER_REGISTRY_PATH` |
| Default seed | `hermes_cli/web_server.py:_DEFAULT_CAREER_REGISTRY` |
| Backend API contract | `hermes_cli/web_server.py:_dashboard_career_registry_contract()` |
| API endpoint | `GET /api/dashboard/v2` |
| API fields | `career_progress`, `dashboard_sources.career_registry` |
| Frontend consumer | `web/src/pages/ReportsPage.tsx:CareerCommandConsole` |
| Optional enrichment | Obsidian operating note for summary/phase/priorities/blockers/risks/narrative only |
| Current registry version | `schema_version: 2` |
| Current registry counts | 5 certifications, 8 skills |

## Existing schema before extension

Top-level fields found before this pass:

- `current_role`
- `target_role`
- `future_role`
- `next_milestone`
- `current_priority`
- `current_blockers`
- `roadmap_progress_percent`
- `last_updated`
- `certifications[]`
  - `name`
  - `progress_percent`
  - `target_completion_date`
- `skills[]`
  - `name`
  - `current_proficiency_percent`
  - `target_proficiency_percent`

## Current schema after extension

Top-level fields now present:

- `schema_version`
- `current_role`
- `employer`
- `client`
- `employment_type`
- `hourly_rate`
- `annual_salary`
- `contract_to_perm_status`
- `start_date`
- `department`
- `target_role`
- `future_role`
- `target_salary`
- `target_timeline`
- `next_milestone`
- `current_priority`
- `current_blockers`
- `roadmap_progress_percent`
- `today_tasks`
- `study_streak_days`
- `study_progress_percent`
- `resume_status`
- `linkedin_status`
- `portfolio_status`
- `interview_readiness`
- `applications_sent`
- `job_search_status`
- `compensation_notes`
- `next_income_lever`
- `last_updated`
- `certifications[]`
  - `name`
  - `provider`
  - `priority`
  - `status`
  - `progress_percent`
  - `exam_date`
  - `expiration_date`
  - `target_completion_date` (legacy-compatible scheduling field)
- `skills[]`
  - `name`
  - `current_proficiency_percent`
  - `target_proficiency_percent`
  - `last_practiced`
  - `next_task`

## Existing tables

None. The Career Registry is not SQLite and owns no database tables. The only SQLite dashboard-adjacent registry audited separately is the Finance Registry at `/home/yuu/.hermes/profiles/engineering_lab/finance/registry.db`.

## Existing APIs

| API | Role |
|---|---|
| `GET /api/dashboard/v2` | Primary dashboard endpoint. Returns `career_progress` and `dashboard_sources.career_registry`. |
| `_dashboard_career_registry_contract()` | Internal API contract builder that normalizes skills/certifications into `items` and `milestones`. |
| `_dashboard_collect_obsidian_operating_notes()` | Merges optional Obsidian narrative with registry-owned structured career facts. |

There is no separate `/api/career/*` endpoint and no separate Career Command persistence API.

## Existing automation

- If no explicit `HERMES_CAREER_REGISTRY_PATH` is set and the default registry file is missing, `_load_dashboard_json_registry()` seeds `<get_hermes_home()>/dashboard/career_registry.json` from `_DEFAULT_CAREER_REGISTRY`.
- No scheduled cron, webhook, sync daemon, or external automation currently updates career facts.
- The dashboard refetches `GET /api/dashboard/v2`; edits to the JSON registry become visible after the next fetch.

## Existing dashboard dependencies

| Dashboard card/section | Source mapping | Status |
|---|---|---|
| Current Position | `career_progress.current_role`, `employer`, `client`, `employment_type`, `hourly_rate`, `annual_salary`, `contract_to_perm_status`, `start_date`, `department` | Registry-backed; unknowns show `Needs input`. |
| Target Role | `career_progress.target_role`, `target_salary`, `target_timeline`, `skill_gaps` if present | Registry-backed; unknowns show `Needs input`. |
| Certification Roadmap | `career_progress.certifications[]` plus `current_priority` | Registry-backed. Existing `progress_percent` retained; status/provider/exam/expiration added. |
| Skill Matrix | `career_progress.skills[]` | Registry-backed. Existing proficiency percentages retained; `last_practiced`/`next_task` added. |
| Today’s Study Plan | `career_progress.today_tasks` then legacy study aliases / next actions | Registry-backed. |
| Career Risk | `behind_schedule`, certification progress, `interview_readiness`, `resume_status`, `study_consistency` if present | Partially backed; missing values show input prompts. |
| Income Strategy | `hourly_rate`, `annual_salary`, `target_salary`, `next_income_lever` | Registry-backed; no synthetic pay data. |
| Job Readiness | `resume_status`, `linkedin_status`, `portfolio_status`, `interview_readiness`, `applications_sent` | Registry-backed; unknowns show input prompts. |

## Existing tests

| Test | Coverage |
|---|---|
| `tests/hermes_cli/test_web_server.py::test_dashboard_v2_returns_operational_summary` | Confirms dashboard returns `career_progress` role baseline and skill items. |
| `tests/hermes_cli/test_web_server.py::test_dashboard_v2_reads_obsidian_operating_notes` | Confirms Obsidian narrative can merge without replacing registry milestones. |
| `tests/hermes_cli/test_web_server.py::test_dashboard_v2_reads_extended_career_registry_as_single_source` | Added in this pass. Proves extended registry fields serialize through `/api/dashboard/v2` and `dashboard_sources.career_registry` points at the same object. |
| `tests/hermes_cli/test_web_server.py::test_dashboard_v2_career_registry_missing_fields_serialize_as_null_not_fabricated` | Added in this pass. Proves sparse registries do not fabricate defaults. |
| `tests/hermes_cli/test_reports_page_executive_homepage.py::test_career_command_is_career_advancement_console_not_generic_progress_card` | Confirms Career Command console component is rendered instead of generic progress cards. |
| `tests/hermes_cli/test_reports_page_executive_homepage.py::test_career_command_surfaces_missing_inputs_and_next_actions` | Confirms source contains missing-field prompts and next actions. |

## Existing documentation

- `docs/dashboard_source_map.md` maps Career Command to `career_progress` and the Career Registry path.
- `docs/dashboard_truth_report.md` classifies Career Command roles as real registry data and certification status as previously incomplete.
- `docs/dashboard_data_reality_pass.md` records the earlier finding that certification status fields were missing.
- This file is now the authoritative audit and expansion record for the Career Registry.

## Source-of-truth analysis

Career Command has one structured source of truth: `career_registry.json`.

The Obsidian career operating note is not a second registry. It may contribute narrative fields such as summary, phase, priorities, blockers, risks, next actions, and KPIs, but it must not overwrite registry-owned facts: role, employment, target salary, certifications, skills, study metrics, resume/LinkedIn/portfolio/readiness, job search, or compensation.

The frontend must not define literal role/pay/certification/skill facts in JSX. It may define labels, section names, and missing-field prompts.

## Data quality assessment

| Area | Assessment |
|---|---|
| Employment | `current_role` exists. Employer/client/type/pay/start/department are now schema fields but currently unknown. |
| Target career | `target_role` and `future_role` exist. Target salary/timeline are now schema fields but currently unknown. |
| Certifications | Names and progress existed. Provider/priority/status/exam/expiration now exist but are unknown. Known baseline conflicts still require user-confirmed data entry before marking complete/expired. |
| Skills | Names and current/target proficiency existed. Last practiced and next task now exist but are unknown. |
| Study plan | Roadmap progress existed. Today’s tasks, streak, and study progress now exist but are currently blank/unknown. |
| Resume / LinkedIn / Portfolio | Status fields now exist but are unknown. |
| Interview readiness | Field now exists but is unknown. |
| Job search | Status/applications fields now exist; `applications_sent` is unknown until entered. |
| Compensation | Pay/target/notes/income lever fields now exist but are unknown. |

## Gap analysis field matrix

| Domain | Field | Status | Registry key / migration note |
|---|---|---|---|
| Employment | Employer | Exists | `employer` (currently null) |
| Employment | Client | Exists | `client` (currently null) |
| Employment | Employment type | Exists | `employment_type` (currently null) |
| Employment | Current role | Exists | `current_role` |
| Employment | Hourly rate | Exists | `hourly_rate` (currently null) |
| Employment | Annual salary | Exists | `annual_salary` (currently null) |
| Employment | Contract-to-perm status | Exists | `contract_to_perm_status` (currently null) |
| Employment | Start date | Exists | `start_date` (currently null) |
| Employment | Department | Exists | `department` (currently null) |
| Target Career | Target role | Exists | `target_role` |
| Target Career | Target salary | Exists | `target_salary` (currently null) |
| Target Career | Timeline | Exists | `target_timeline` (currently null) |
| Certifications | Certification name | Exists | `certifications[].name` |
| Certifications | Provider | Exists | `certifications[].provider` (currently null) |
| Certifications | Priority | Exists | `certifications[].priority` (currently null) |
| Certifications | Status | Exists | `certifications[].status` (currently null) |
| Certifications | Progress | Exists / legacy-compatible | `certifications[].progress_percent`; do not duplicate as a second `progress` value. |
| Certifications | Exam date | Exists | `certifications[].exam_date` (currently null) |
| Certifications | Expiration | Exists | `certifications[].expiration_date` (currently null) |
| Skills | Skill name | Exists | `skills[].name` |
| Skills | Current level | Exists / legacy-compatible | `skills[].current_proficiency_percent`; do not duplicate as `current_level`. |
| Skills | Target level | Exists / legacy-compatible | `skills[].target_proficiency_percent`; do not duplicate as `target_level`. |
| Skills | Last practiced | Exists | `skills[].last_practiced` (currently null) |
| Skills | Next task | Exists | `skills[].next_task` (currently null) |
| Study Plan | Today’s tasks | Exists | `today_tasks` (currently []) |
| Study Plan | Streak | Exists | `study_streak_days` (currently null) |
| Study Plan | Progress | Exists | `study_progress_percent`; roadmap still uses `roadmap_progress_percent` |
| Resume | Resume | Exists | `resume_status` (currently null) |
| LinkedIn | LinkedIn | Exists | `linkedin_status` (currently null) |
| Portfolio | Portfolio | Exists | `portfolio_status` (currently null) |
| Interview Readiness | Interview readiness | Exists | `interview_readiness` (currently null) |
| Job Search | Job search | Exists | `job_search_status`, `applications_sent` (currently null) |
| Compensation | Compensation | Exists | `hourly_rate`, `annual_salary`, `target_salary`, `compensation_notes`, `next_income_lever` |

## Missing fields

After this pass, no requested Career Command field is absent from the schema. Many fields are present but intentionally empty because no verified data was supplied.

## Duplicate fields

No duplicate registry or duplicate schema was created.

Potential semantic duplicates to watch:

- `roadmap_progress_percent` and `study_progress_percent` are related but not identical. Keep `roadmap_progress_percent` for overall career roadmap; use `study_progress_percent` for study-plan progress if supplied.
- `target_completion_date` and `exam_date` are related certification date fields. Keep `target_completion_date` as legacy-compatible scheduling metadata; use `exam_date` for the actual scheduled exam date.
- Do not add separate `current_level` or `target_level` alongside existing skill proficiency percentages unless a migration explicitly deprecates the percentage fields.

## Legacy fields

| Legacy-compatible field | Keep? | Reason |
|---|---|---|
| `future_role` | Yes | Existing dashboard summary uses current -> target -> future role. |
| `current_priority` | Yes | Used to select current certification priority. |
| `next_milestone` | Yes | Feeds next action fallback. |
| `current_blockers` | Yes | Feeds Career Risk / blockers. |
| `roadmap_progress_percent` | Yes | Existing progress metric and health score input. |
| `certifications[].progress_percent` | Yes | Existing normalized progress field. |
| `certifications[].target_completion_date` | Yes | Backward-compatible scheduling field. |
| `skills[].current_proficiency_percent` | Yes | Existing skill progress bars depend on it. |
| `skills[].target_proficiency_percent` | Yes | Existing target progress detail depends on it. |

## Recommended improvements

1. Add a small `hermes_cli/career_registry.py` module if Career Registry operations grow beyond dashboard rendering. Keep it pointed at the same JSON path; do not create a second registry.
2. Add explicit validation for known field types and date formats before accepting write APIs, if a future write API is approved.
3. Add a data-entry workflow for the currently null fields instead of hardcoding values in React.
4. Reconcile certification truth only with user-approved facts. Earlier audits suggested Security+ and Linux+ may be complete and AWS Cloud Practitioner may be expired, but this pass did not encode those claims.
5. Document that `HERMES_CAREER_REGISTRY_PATH` is a path override for testing/alternate deployments, not a second registry source.
6. If Obsidian narrative remains enabled, add a regression test proving Obsidian cannot override registry-owned employment/pay/certification/skill facts.

## Implementation changes made in this pass

- Extended `_DEFAULT_CAREER_REGISTRY` in `hermes_cli/web_server.py` with missing Career Command fields.
- Updated `_dashboard_career_registry_contract()` to serialize the registry payload through `career_progress` while preserving normalized `items`, `milestones`, `source`, and compatibility fields.
- Extended `/home/yuu/.hermes/profiles/engineering_lab/dashboard/career_registry.json` in place with null/empty placeholders only.
- Updated `CareerCommandConsole` to read canonical keys such as `hourly_rate`, `annual_salary`, `contract_to_perm_status`, `target_timeline`, `today_tasks`, and `skills[].next_task` while preserving backward-compatible aliases.
- Added regression tests for single-source registry serialization and missing-field non-fabrication.

## Verification commands

Run:

```bash
python3 -m pytest tests/hermes_cli/test_web_server.py -q -k 'career_registry or career_progress or obsidian_operating_notes' -o 'addopts='
python3 -m pytest tests/hermes_cli/test_reports_page_executive_homepage.py -q -k 'career_command' -o 'addopts='
cd web && npm run build
```
