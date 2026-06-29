# Career Source Gap Report

Generated: 2026-06-29T22:24:49Z

## Summary

| Source | Status | Evidence | Needed user action |
|---|---|---|---|
| Obsidian | Connected | `/home/yuu/Sync/ObsidianVault` exists; career notes found and parsed manually for registry population. | None for current available notes. Add/update notes for missing career facts. |
| Microsoft Learn | Not connected | No Microsoft Learn API/export/token/path found in profile environment or files. | Export Microsoft Learn transcript/progress, provide profile/certification progress screenshot, or provide an API/export path if available. |
| GitHub | Connected | `gh auth status` authenticated as `godhand-uriel`; `gh repo list` returned repositories. | None for profile/repository inventory. Optional: mark which repos should be public portfolio projects. |
| LinkedIn | Not connected | No LinkedIn API/export/profile file found. | Export LinkedIn profile PDF or paste About, Experience, Skills, Certifications, Projects, and Education sections. |
| Resume | Not connected | Search found no resume PDF/DOCX/TXT/Markdown file under `/home/yuu`. | Place latest resume in an accessible path or paste resume text. |
| Calendar | Not connected | `gws` missing; Google Workspace skill reports `NOT_AUTHENTICATED` because `google_token.json` and `google_client_secret.json` are absent. | Complete Google Workspace OAuth for Calendar or provide calendar export. |

## Obsidian

Status: Connected

Accessible vault:

- `/home/yuu/Sync/ObsidianVault`

Career-related notes found:

- `Career Development/Career Development.md`
- `Career Development/First Job.md`
- `Finance/Income/W-2.md`
- `Assets/HermesOS/prompts/HERMES OS — EXECUTIVE COMMAND CENTER v1.md`

Structured data extracted only when clearly stated:

- Current role: `Desktop Support Technician`
- Client: `American Airlines`
- Department/location: `MIA Airport`
- Employment type: `W-2 / contract-to-hire`
- Hourly rate: `$25/hour`
- Overtime rate: `$37.50/hour`
- Base estimated annual value: `~$52,000/year`
- With overtime estimated annual value: `~$60,000-$80,000/year`
- Contract-to-perm status: `Contract-to-Hire`
- Start date: `June 15, 2026`
- Career objectives, roadmap, priorities, blockers, risks, next actions, KPIs from `Career Development.md`

Not extracted because not clearly stated:

- Employer/vendor separate from client
- Conversion target
- Target salary
- Target timeline
- Exam dates
- Certification expiration dates
- Study streak
- Study progress
- Resume facts
- Interview readiness
- Application count

## Microsoft Learn

Status: Not connected

Current access:

- No Microsoft Learn CLI/API/export configured in this environment.
- No Microsoft Learn export file found.

Needed user action:

- Export Microsoft Learn transcript/progress, or
- Provide screenshots/profile data for certification progress, or
- Provide a documented API/export endpoint and credentials if available.

## GitHub

Status: Connected

Access confirmed:

- `gh auth status` succeeded for account `godhand-uriel`.
- Token scopes include `repo`, `workflow`, `gist`, `read:org`.

Collected data:

- Profile: `https://github.com/godhand-uriel`
- Name: `D'Angelo Rashid`
- Repositories returned:
  - `hermes-agent` — public — Python — `https://github.com/godhand-uriel/hermes-agent`
  - `job-separation-navigator` — private — JavaScript — `https://github.com/godhand-uriel/job-separation-navigator`
  - `PythonProject` — private — HTML — `https://github.com/godhand-uriel/PythonProject`
  - `PythonTouchStone` — private — Python — `https://github.com/godhand-uriel/PythonTouchStone`
  - `dmv-navigator` — private — PowerShell — `https://github.com/godhand-uriel/dmv-navigator`

Technical stack evidence:

- Python
- JavaScript
- HTML
- PowerShell

Needed user action:

- Optional: identify which private repositories should count as portfolio-ready evidence.
- Optional: add descriptions/readmes if repositories should be shown externally.

## LinkedIn

Status: Not connected

Current access:

- No LinkedIn API/export/file available.

Needed user action:

- Export LinkedIn profile PDF, or
- Paste profile sections:
  - Headline
  - About
  - Experience
  - Skills
  - Certifications
  - Education
  - Projects

## Resume

Status: Not connected

Current access:

- No resume PDF/DOCX/TXT/Markdown file found under `/home/yuu` with the available file search.

Needed user action:

- Place latest resume in an accessible path, or
- Paste resume text, or
- Provide the exact path to the resume file.

Fields blocked by missing resume source:

- latest resume path
- resume last updated
- resume status beyond source availability
- missing resume updates
- experience details
- project descriptions from resume
- resume-certified skills list

## Calendar

Status: Not connected

Current access:

- `gws` CLI is not installed.
- Google Workspace skill is installed but reports `NOT_AUTHENTICATED`.
- Missing credential files:
  - `/home/yuu/.hermes/profiles/engineering_lab/google_token.json`
  - `/home/yuu/.hermes/profiles/engineering_lab/google_client_secret.json`

Needed user action:

- Complete Google Workspace OAuth setup for Calendar, or
- Provide an `.ics` calendar export, or
- Manually provide exam dates, interviews, study blocks, work schedule, and deadlines.

Fields blocked by missing calendar source:

- exam dates
- interviews
- study blocks
- work schedule
- career deadlines
