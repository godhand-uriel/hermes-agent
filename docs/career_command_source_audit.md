# Career Command Source Audit

Generated: 2026-06-29T22:24:49Z

## Executive finding

Career Command is registry-backed. The dashboard API must expose `career_progress` from the existing Career Registry only. Source systems such as Obsidian, Microsoft Learn, GitHub, LinkedIn, Resume, and Calendar are allowed to populate the Career Registry, but the Career Command UI must not parse those sources directly.

This pass removed the remaining Career Command direct-Obsidian presentation path. Obsidian remains available as an input source to the Career Registry.

## Data-flow diagram

```text
Obsidian / Microsoft Learn / GitHub / LinkedIn / Resume / Calendar
        ↓
Career sync/import layer or manual registry update
        ↓
Career Registry
        /home/yuu/.hermes/profiles/engineering_lab/dashboard/career_registry.json
        ↓
Dashboard API
        GET /api/dashboard/v2 -> career_progress
        ↓
Career Command UI
        web/src/pages/ReportsPage.tsx -> CareerCommandConsole
```

## Confirmed registry path

- Path: `/home/yuu/.hermes/profiles/engineering_lab/dashboard/career_registry.json`
- Format: JSON
- Schema version: `2`
- Source override env var: `HERMES_CAREER_REGISTRY_PATH`
- Loader: `hermes_cli/web_server.py::_dashboard_career_registry_contract()`
- Generic registry loader: `hermes_cli/web_server.py::_load_dashboard_json_registry()`

## Registry schema inventory

Current registry top-level groups:

- Employment:
  - `current_role`
  - `employer`
  - `client`
  - `employment_type`
  - `hourly_rate`
  - `overtime_hourly_rate`
  - `annual_salary`
  - `annual_income_with_overtime_range`
  - `contract_to_perm_status`
  - `start_date`
  - `department`
  - `conversion_target`
- Target career:
  - `target_role`
  - `future_role`
  - `target_salary`
  - `target_timeline`
  - `skill_gaps`
  - `next_milestone`
- Certifications:
  - `certifications[]` with `name`, `provider`, `priority`, `status`, `progress_percent`, `exam_date`, `expiration_date`, `target_completion_date`, `next_action`
- Skills:
  - `skills[]` with `name`, `current_proficiency_percent`, `target_proficiency_percent`, `last_practiced`, `next_task`
- Study plan:
  - `today_tasks`
  - `weekly_plan`
  - `study_streak_days`
  - `study_progress_percent`
  - `study_consistency`
  - `study_hours_needed`
  - `daily_study_target`
- Resume:
  - `resume_status`
  - `latest_resume`
  - `resume_last_updated`
  - `resume_missing_updates`
- LinkedIn:
  - `linkedin_status`
  - `linkedin_completeness`
  - `linkedin_missing_sections`
- Portfolio:
  - `portfolio_status`
  - `github_profile`
  - `portfolio_readiness`
  - `portfolio_projects[]`
  - `technical_stack_evidence[]`
- Interview readiness:
  - `interview_readiness`
  - `interview_weak_areas`
  - `interview_next_task`
- Job search:
  - `applications_sent`
  - `job_search_status`
- Compensation:
  - `compensation_notes`
  - `current_hourly_rate`
  - `annualized_income`
  - `target_income`
  - `income_gap`
  - `next_income_lever`
- Source governance:
  - `source_connections`
  - `source_evidence`
  - `last_updated`

## Dashboard API path

- API route: `GET /api/dashboard/v2`
- Response field: `career_progress`
- Source mirror: `dashboard_sources.career_registry`
- Backend contract: `hermes_cli/web_server.py::_dashboard_career_registry_contract()`

Career fields are returned by spreading the registry payload into the API response. The API adds derived presentation helpers only:

- `status`
- `summary`
- `items`
- `milestones`
- `source`

No source data is scraped by the frontend.

## Frontend Career Command component

- File: `web/src/pages/ReportsPage.tsx`
- Component: `CareerCommandConsole`
- Data source: `dashboard.careerProgress`, built from `data.career_progress`
- Missing-value behavior: `careerMissing(field)` returns `Needs input: <field>`
- UI source rule: the component reads only the API payload; it does not read Obsidian, GitHub, LinkedIn, Resume, Microsoft Learn, or Calendar directly.

## Existing source ingestion paths

### Existing before this pass

- Career Registry JSON loader:
  - `HERMES_CAREER_REGISTRY_PATH` or profile dashboard path.
- Obsidian vault parser for operating notes:
  - `HERMES_DASHBOARD_OBSIDIAN_VAULT`
  - `_read_dashboard_operating_note()`
  - Still used by Artist Management.
  - No longer used as the direct Career Command source.
- GitHub access:
  - `gh` CLI authenticated as `godhand-uriel`.
- Google Workspace / Calendar:
  - Google Workspace skill exists, but token/client secret are missing for this profile.
- Resume / LinkedIn / Microsoft Learn:
  - No authenticated/exported source found in this environment.

### Correct ingestion model

Career-source ingestion must write to the Career Registry first. Career Command should never bypass the registry.

## Existing tests

Relevant tests:

- `tests/hermes_cli/test_web_server.py`
  - Dashboard v2 contract tests.
  - Career Registry source-of-truth tests.
  - Missing-field serialization tests.
  - Registry-not-Obsidian direct-parse regression.
- `tests/hermes_cli/test_reports_page_executive_homepage.py`
  - Career Command frontend structure and missing-input display tests.

## Source-of-truth analysis

| Layer | Correct source | Status |
|---|---|---|
| Career source systems | Obsidian, Microsoft Learn, GitHub, LinkedIn, Resume, Calendar, manual input | Inputs only |
| Registry | `/home/yuu/.hermes/profiles/engineering_lab/dashboard/career_registry.json` | Single source of truth |
| API | `/api/dashboard/v2.career_progress` | Presentation serialization |
| UI | `CareerCommandConsole` | Presentation only |

## Direct-source bypass check

- Career Command frontend: no direct source parsing found.
- Dashboard API before this pass: Career data could be merged with Obsidian operating-note narrative.
- Dashboard API after this pass: Career Command uses `_dashboard_career_registry_contract()` only. Obsidian career notes are documented as source evidence inside the registry instead of being parsed into Career Command live.

## Recommended improvements

1. Add a dedicated career sync command that imports from connected sources and writes only to `career_registry.json`.
2. Add source-specific import provenance for every field: `field`, `value`, `source`, `confidence`, `imported_at`.
3. Add schema validation for `career_registry.json`.
4. Add a manual-input UI/API for missing fields rather than editing JSON by hand.
5. Add Microsoft Learn, LinkedIn, Resume, and Calendar connectors when the user provides the required exports or OAuth access.
