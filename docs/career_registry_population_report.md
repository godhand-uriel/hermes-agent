# Career Registry Population Report

Generated: 2026-06-29T22:24:49Z

## Registry populated

Updated existing registry only:

- `/home/yuu/.hermes/profiles/engineering_lab/dashboard/career_registry.json`

No new Career Registry was created.

## Source policy followed

- Career Command remains registry-backed.
- The frontend was not hardcoded with career facts.
- Source systems were not parsed directly by the UI.
- Missing data was left as `null`, `[]`, or explicit `Needs user action` source-status text.
- Career facts were not fabricated.

## Populated from Obsidian

Sources:

- `/home/yuu/Sync/ObsidianVault/Career Development/First Job.md`
- `/home/yuu/Sync/ObsidianVault/Finance/Income/W-2.md`
- `/home/yuu/Sync/ObsidianVault/Career Development/Career Development.md`

Populated fields:

| Registry field | Value | Source |
|---|---|---|
| `current_role` | `Desktop Support Technician` | `Career Development/First Job.md:21` |
| `client` | `American Airlines` | `Career Development/First Job.md:21` |
| `department` | `MIA Airport` | `Career Development/First Job.md:21` |
| `employment_type` | `W-2 / contract-to-hire` | `First Job.md` and `W-2.md` headings/status |
| `hourly_rate` | `25` | `Career Development/First Job.md:25` |
| `overtime_hourly_rate` | `37.5` | `Career Development/First Job.md:26` |
| `annual_salary` | `52000` | `Career Development/First Job.md:31` |
| `annual_income_with_overtime_range` | `$60,000-$80,000/year` | `Career Development/First Job.md:32` |
| `contract_to_perm_status` | `Contract-to-Hire` | `Career Development/First Job.md:27` |
| `start_date` | `2026-06-15` | `Career Development/First Job.md:45` |
| `skill_gaps` | Career roadmap gap list | `Career Development.md:46-52` |
| `today_tasks` | Next actions from career note | `Career Development.md:77-81` |
| `weekly_plan` | Current priorities from career note | `Career Development.md:54-59` |
| `current_blockers` | Career blockers from career note | `Career Development.md:66-69` |
| `next_milestone` | Next portfolio project action | `Career Development.md:79-80` |

## Populated from GitHub

Source:

- `gh` CLI authenticated as `godhand-uriel`

Populated fields:

| Registry field | Value |
|---|---|
| `github_profile` | `https://github.com/godhand-uriel` |
| `portfolio_status` | `GitHub profile connected; repositories found.` |
| `portfolio_readiness` | Partially connected; curated public portfolio still needs user input. |
| `portfolio_projects` | `hermes-agent`, `job-separation-navigator`, `PythonProject`, `PythonTouchStone`, `dmv-navigator` |
| `technical_stack_evidence` | Python, JavaScript, HTML, PowerShell |
| `source_connections.github.status` | `Connected` |

## Populated from existing registry facts

Existing facts retained because they were already in the Career Registry and were not contradicted by available sources:

- `target_role`: `Cloud Engineer`
- `future_role`: `Cloud Architect`
- `current_priority`: `AWS Solutions Architect Associate`
- `roadmap_progress_percent`: `18`
- Certification list:
  - AWS Solutions Architect Associate
  - Terraform Associate
  - AZ-900
  - Linux+
  - Security+
- Existing skill percentages for AWS, Azure, Linux, Networking, Security, Python, and Terraform.

## Added missing skill rows without fabricated levels

The requested Career Command skill set now exists in the registry. Where no source provided a level, the skill row exists with `null` proficiency fields so the UI can display `Needs input` rather than invent a level.

Added rows:

- Windows
- Microsoft 365
- PowerShell
- SQL
- Git
- Docker
- Kubernetes
- Troubleshooting
- Customer Support

## Missing or blocked fields

These remain missing because no available source clearly stated them:

- Employer/vendor separate from client
- Conversion target
- Target salary
- Target timeline
- Study streak
- Study progress
- Study consistency
- Study hours needed
- Daily study target
- Certification exam dates
- Certification expiration dates
- Resume file/path/content
- LinkedIn completeness/profile content
- Interview readiness
- Job applications sent
- Job search status
- Target income
- Income gap

## Needs-user-action entries written to registry

- `resume_status`: `Needs user action: provide latest resume file or resume text.`
- `linkedin_status`: `Needs user action: export LinkedIn profile PDF or paste profile sections.`
- `source_connections.microsoft_learn.needed_user_action`: export transcript/progress or provide screenshot/profile data.
- `source_connections.calendar.needed_user_action`: complete Google Calendar OAuth or provide calendar export.

## UI verification expectation

Career Command should now show real registry-backed values for:

- Current role
- Client
- Employment type / contract-to-hire status
- Hourly rate
- Annualized estimate
- Start date
- Current certification priority
- Portfolio/GitHub status
- Study plan from Obsidian next actions
- Skill rows for all requested skill areas

`Needs input` should remain for fields that are genuinely unavailable, including employer/vendor, conversion target, target salary, target timeline, exam dates, interview readiness, and missing per-skill next tasks.
