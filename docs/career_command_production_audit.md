# Career Command Production Audit

## Current Architecture

Career Command now follows the canonical Hermes application flow:

```text
External Sources
  -> Connectors / Importers
  -> Career Registry + Learning Registry
  -> Career Intelligence Layer
  -> Dashboard API (/api/dashboard/v2.career_progress)
  -> Career Command UI
```

The frontend remains presentation-only. It renders the `career_progress` contract from the Dashboard API and does not parse registry files or external sources.

## Source Inventory

| Source | Status | Connector / Importer | Evidence | Confidence | Limitations |
|---|---|---|---|---:|---|
| Career Registry | Connected when `dashboard/career_registry.json` exists | JSON registry loader | Registry path + source evidence entries | 1.0 when configured | Authoritative for career facts only |
| Learning Registry | Connected when `dashboard/learning_registry.json` exists | Learning registry projection | Courses, certifications, sources, source evidence | 1.0 when configured | Detailed learning history stays in Learning Registry |
| Obsidian | Supported | Obsidian learning sync | Note paths/frontmatter/manual review records | Per record | Notes feed registries only; UI does not parse notes |
| Udemy | Supported | Browser-session importer | Course/cert progress records | Per record | Requires user browser session; no fake API |
| Microsoft Learn | Documented / manual evidence | Manual export/import until approved connector exists | Transcript/screenshot/user export | 0 unless evidence supplied | No approved personal-progress API integration |
| AWS Skill Builder | Documented / manual evidence | Manual export/import until approved connector exists | Export/screenshot/PDF evidence | 0 unless evidence supplied | No approved personal-progress API integration |
| GitHub | Registry-backed | Registered source connection + portfolio projects | Repo/project entries | Per project | Live GitHub analysis only after imported into registry |
| Resume | Registry-backed | Resume import into Career Registry | Imported skills/history/certs | Per record | Resume cert existence is not course progress |
| LinkedIn | Registry-backed/manual | Source connection/status field | Profile/status evidence | Per record | No direct frontend/live parsing |
| Calendar | Future/registry-backed | Source connection/status field | Calendar availability when imported | Per record | Scheduler uses only registered available-time evidence |

## Registry Inventory

- Career Registry: current/target role, employment, salary, resume status, LinkedIn/applications/interview status, certifications, skills, source connections, source evidence, portfolio projects, employment history, timeline, military service, leadership experience.
- Learning Registry: providers, certifications, courses, study sessions/streaks, recommendations, source evidence, manual review items.

## Projection Inventory

Dashboard API `career_progress` includes:

- `certification_roadmap`
- `learning_summary`
- `skill_matrix`
- `career_risks`
- `job_readiness`
- `study_plan`
- `study_schedule`
- `study_scheduler.time_blocks`
- `portfolio_intelligence`
- `learning_connectors`
- `income_strategy`
- `provenance`

## Computed Fields

- Certification Roadmap: reconciles Career Registry certifications with Learning Registry course/cert progress.
- Skill Matrix: evidence-driven rows from resume, GitHub/portfolio, learning records, and registry skills. Evidence count and confidence are exposed.
- Job Readiness: weighted score from resume, GitHub, portfolio, LinkedIn, interview readiness, applications, certifications, projects, learning progress, and employment stability.
- Career Risk: computed risks only from missing or source-backed facts. Each risk includes severity, probability, impact, mitigation, source, and confidence.
- Study Scheduler: deterministic time-block schedule from active learning target, study plan, risks, and registry evidence.
- Portfolio Intelligence: registered project analysis for languages, frameworks, architecture, complexity, relevance, quality, missing projects, and downstream links to Skill Matrix, Job Readiness, and Career Risk.
- Income Strategy: annualized compensation and target gap are computed in the API, not the UI.

## Stored Fields

Stored fields remain in the registries. The API may serialize them and attach provenance, but it does not turn frontend literals into business facts.

## Confidence Model

- Direct configured registry fields with evidence: high confidence.
- Learning provider records: provider confidence when present.
- Computed intelligence: confidence is weighted by evidence availability.
- Missing/unconnected providers: zero or low confidence; never simulated.

## Risk Model

Risks are emitted only when a source-backed fact is missing or indicates risk:

- No target salary
- No exam scheduled when active certification course progress is high
- Missing interview readiness
- LinkedIn not connected
- Microsoft Learn not connected/manual evidence only
- No applications tracked
- Skill evidence incomplete

Each risk includes mitigation and traceable source fields.

## Future Connector Plan

1. Microsoft Learn: support user-exported transcript/progress import first; add browser or official API connector only after validating stable access.
2. AWS Skill Builder: support export/screenshot/PDF evidence import first; do not fabricate private progress API access.
3. Coursera / Pluralsight / A Cloud Guru: add provider records and manual evidence import before any live connector.
4. Books / YouTube: manual evidence import with explicit source URLs/pages and confidence.
5. Calendar: schedule only from registered availability blocks, not direct UI calendar parsing.

## Known Gaps

- Frontend provenance click-through UI can be richer; the API provenance contract is present.
- Live GitHub repository analysis should be an importer that writes portfolio intelligence evidence back to the registry before display.
- Microsoft Learn and AWS Skill Builder remain documented/manual-evidence connectors until a real approved connector is implemented.
- Registry schema validation should be tightened so all fields consistently carry metadata where practical.

## Recommended Improvements

- Add a dedicated Career Intelligence module outside `web_server.py` once contracts stabilize.
- Add schema validators for Career Registry and Learning Registry metadata fields.
- Add a provenance drawer in Career Command that renders `career_progress.provenance` without exposing raw registry internals.
- Add connector-specific CLI commands for Microsoft Learn/AWS Skill Builder manual evidence import.
- Add GitHub importer tests that prove repo analysis flows through the registry before affecting Skill Matrix or Job Readiness.
