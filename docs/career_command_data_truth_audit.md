# Career Command Data Truth Audit

Date: 2026-06-30

Architecture rule audited:
External Sources → Learning Registry / Career Registry → Dashboard API → Career Command UI

The Career Command UI must render the Dashboard API projection only. It must not parse resume, GitHub, Udemy, Obsidian, or other external sources directly, and it must not hardcode career facts.

## Registry sources

- Career Registry: `/home/yuu/.hermes/profiles/engineering_lab/dashboard/career_registry.json`
- Learning Registry: `/home/yuu/.hermes/profiles/engineering_lab/dashboard/learning_registry.json`
- Dashboard API projection: `hermes_cli.web_server._dashboard_career_registry_contract()` via `/api/dashboard/v2.career_progress`
- Frontend consumer: `web/src/pages/ReportsPage.tsx` `CareerCommandConsole`

## Global defects found and repaired

- Certification Roadmap mixed certification status with course progress. Security+ and Linux+ resume certifications had `progress_percent: 0`, which could be rendered as weak/missing progress even though the credentials are verified in the Career Registry. Repaired by modeling `certification_status` separately from `course_progress_percent`.
- Learning Intelligence selected the highest-progress learning item, causing Security+ 99% to dominate AWS SAA 93%. Repaired by prioritizing the active career certification (`current_priority` / `current_certification_priority`) before progress.
- Today’s Study Plan could be generic or source-ambiguous. Repaired by deriving it from active target priority and learning progress; current plan is AWS SAA-first.
- Career Risk was too generic and could imply missing certifications that already exist. Repaired by computing explicit registry-backed risks.
- Skill Matrix was too generic and did not consistently merge resume, GitHub, learning, registry skill, and target-role evidence. Repaired by generating a normalized matrix in the API projection.
- Job Readiness was partially scattered across fields. Repaired by producing a `job_readiness` API object.
- Frontend now consumes `certification_roadmap`, `learning_summary`, `skill_matrix`, `career_risks`, `today_tasks`, and `job_readiness` from the API projection.

## Section-by-section truth map

### Current Position

Displayed fields:
- `current_role`
- `employer` / `client`
- `contract_to_perm_status`
- `hourly_rate`
- `start_date`
- `conversion_target`

Source registry path:
- Career Registry

Source fields:
- `current_role`, `employer`, `client`, `contract_to_perm_status`, `hourly_rate`, `start_date`, `conversion_target`

Source evidence:
- Current registry entry. Current employment is recorded in `career_timeline[0]` with source `registry`.

Freshness:
- Career Registry `last_updated`: `2026-06-29T23:10:21Z`

Confidence:
- Medium-high for registry-entered current role fields.
- Lower for missing employer/conversion target fields because they require manual completion.

Computed or stored:
- Mostly stored.
- UI display fallback is computed by frontend only for missing-field labeling, not factual content.

Current defects:
- `employer` is null while `client` is American Airlines; UI displays client as available.
- `conversion_target` is null and remains a real missing input.

### Target Role

Displayed fields:
- `target_role`
- `target_salary`
- `target_timeline`
- `skill_gaps`

Source registry path:
- Career Registry

Source fields:
- `target_role`, `future_role`, `target_salary`, `target_timeline`, `skill_gaps`

Source evidence:
- Career Registry planning fields.

Freshness:
- Career Registry `last_updated`: `2026-06-29T23:10:21Z`

Confidence:
- Medium for role direction.
- Low for salary/timeline until populated.

Computed or stored:
- Stored.

Current defects:
- `target_salary` is missing.
- `target_timeline` is missing.

### Certification Roadmap

Displayed fields:
- `name`
- `certification_status`
- `course_status`
- `progress_percent`
- `course_progress_percent`
- `course`
- `learning_provider`
- `source`
- `source_evidence`
- `priority`
- `next_action`

Source registry path:
- Career Registry + Learning Registry

Source fields:
- Career Registry: `certifications[]`, `current_priority`, `current_certification_priority`
- Learning Registry: `certifications[]`, `courses[]`, `source_evidence[]`

Source evidence:
- AWS SAA course progress: Learning Registry Udemy course `Ultimate AWS Certified Solutions Architect Associate 2026`, 93%, `udemy_browser` evidence URL.
- Security+ certification status: Career Registry resume import, `status: completed`, source path `/home/yuu/Downloads/MyResume.pdf`; course progress: Udemy 99%.
- Linux+ certification status: Career Registry resume import, `status: completed`, source path `/home/yuu/Downloads/MyResume.pdf`; course progress: Udemy 0%.
- Network+ course progress: Learning Registry Udemy 19%.
- CySA+ course progress: Learning Registry Udemy 0%.
- CCNA course progress: Learning Registry Udemy 0%.

Freshness:
- Learning Registry `last_updated`: `2026-06-30T17:19:56Z`
- Career Registry `last_updated`: `2026-06-29T23:10:21Z`

Confidence:
- 0.9 for Udemy learning records.
- High for resume-confirmed Security+ and Linux+ existence, but date semantics need manual review as noted by resume import.

Computed or stored:
- Computed API projection.
- Source records are stored in Career Registry and Learning Registry.

Current defects:
- Repaired: Security+ no longer shows 0% as certification progress.
- Repaired: certification status is separate from course progress.
- Remaining: AWS SAA exam date is missing.

Expected current projection:
- AWS Solutions Architect Associate — course 93%, certification `in_progress`, source Udemy.
- Security+ — certification `verified`, course 99%, sources resume + Udemy.
- Linux+ — certification `verified`, course 0%, sources resume + Udemy.
- Network+ — course 19%, certification/course in progress from Udemy.
- CySA+ — 0%, not started.
- CCNA — 0%, not started.

### Learning Intelligence

Displayed fields:
- `primary_certification`
- `primary_active_learning_target`
- `learning_provider`
- `course`
- `certification_progress`
- `course_progress_percent`
- `next_learning_task`
- `next_recommendation`
- `secondary_learning_items`
- `provider_connections`
- `study_streak_days`
- `weekly_study_hours`
- `learning_risk`

Source registry path:
- Learning Registry, projected through Career Registry/Dashboard API

Source fields:
- Learning Registry: `certifications[]`, `courses[]`, `sources`, `study_sessions`, `learning_streak`, `study_recommendations`
- Career Registry: `current_priority`, `current_certification_priority`, existing `learning_summary`

Source evidence:
- Primary active learning target: AWS SAA from Career Registry `current_priority`.
- Provider/course/progress: Udemy course `Ultimate AWS Certified Solutions Architect Associate 2026`, 93%.
- Secondary items: Security+ 99%, Network+ 19%, Python course 7%, plus additional lower-priority course records.

Freshness:
- Learning Registry `last_updated`: `2026-06-30T17:19:56Z`

Confidence:
- 0.9 for Udemy imported progress.
- 1.0 for provider connection statuses where manually recorded.

Computed or stored:
- Computed API projection from Learning Registry and active priority.
- Learning Registry stores raw source records.

Current defects:
- Repaired: Security+ 99% no longer overrides AWS SAA as primary.
- Remaining: AWS Skill Builder and Microsoft Learn are not connected.

### Income Strategy

Displayed fields:
- `hourly_rate`
- computed annual estimate
- `target_salary`
- computed income gap
- `next_income_lever`

Source registry path:
- Career Registry

Source fields:
- `hourly_rate`, `annual_salary`, `annualized_income`, `target_salary`, `next_income_lever`, `compensation_notes`

Source evidence:
- Career Registry compensation fields and notes.

Freshness:
- Career Registry `last_updated`: `2026-06-29T23:10:21Z`

Confidence:
- Medium-high for current pay.
- Low for target/gap until `target_salary` is populated.

Computed or stored:
- Current pay and notes are stored.
- Annual estimate and gap are computed in UI from API fields.

Current defects:
- `target_salary` is missing, so gap is not actionable.

### Skill Matrix

Displayed fields:
- `name`
- `current_proficiency_percent`
- `target_proficiency_percent`
- `gap_percent`
- `current_evidence`
- `next_task`

Source registry path:
- Career Registry + Learning Registry

Source fields:
- Career Registry: `skills[]`, `portfolio_projects[]`, `github_profile`, `source_connections`, `technical_stack_evidence`, `target_role`, resume-imported skill sources.
- Learning Registry: certification/course evidence for AWS, Linux, Networking, Security, Python.

Source evidence:
- Resume evidence: skill `sources[]`, `verified_by_resume`, and resume import lines.
- GitHub evidence: `github_profile`, `portfolio_projects[].primary_language`, repository list.
- Learning evidence: Udemy and certification roadmap for AWS/Security/Linux/Network+/Python.
- Target role requirements: Cloud Engineer/Cloud Architect target role drives gaps such as Terraform, Docker, Kubernetes.

Freshness:
- Career Registry `last_updated`: `2026-06-29T23:10:21Z`
- Learning Registry `last_updated`: `2026-06-30T17:19:56Z`

Confidence:
- Medium for resume/GitHub evidence.
- Medium-low for proficiency percentages where resume evidence exists but no explicit proficiency score exists.

Computed or stored:
- Computed API projection.
- Underlying skills and evidence are stored in Career Registry/Learning Registry.

Current defects:
- Repaired: no generic `Needs input` for skills with evidence.
- Remaining: some target gap skills still need direct proficiency evidence, especially Microsoft 365, SQL, Docker, Kubernetes.

### Today’s Study Plan

Displayed fields:
- Ordered task list.

Source registry path:
- Career Registry + Learning Registry

Source fields:
- Career Registry: `current_priority`, `target_role`, `current_blockers`, `today_tasks`, roadmap fields.
- Learning Registry: `certifications[]`, `courses[]`, active AWS SAA course progress.

Source evidence:
- Active target certification: AWS SAA.
- Course progress: Udemy 93%.
- Risk: AWS SAA nearly complete but exam not scheduled.

Freshness:
- Learning Registry `last_updated`: `2026-06-30T17:19:56Z`

Confidence:
- High for AWS SAA-first ordering because it follows explicit active priority.

Computed or stored:
- Computed API projection.

Current defects:
- Repaired: no longer suggests Security+ first when AWS SAA is active.

Expected current plan:
1. Finish AWS SAA remaining Udemy content/review.
2. Complete AWS SAA practice questions.
3. Update Obsidian AWS SAA note after study.

### Career Risk

Displayed fields:
- `label`
- `value`
- `severity`
- `source`

Source registry path:
- Career Registry + Learning Registry

Source fields:
- `certification_roadmap[].course_progress_percent`
- `certification_roadmap[].exam_date`
- `target_salary`
- `interview_readiness`
- `source_connections.linkedin`
- `learning_summary.provider_connections.microsoft_learn`
- `applications_sent`
- `skill_matrix[].current_proficiency_percent`

Source evidence:
- AWS SAA 93% from Udemy with missing exam date.
- `target_salary: null`.
- `interview_readiness: null`.
- LinkedIn not connected / needs user action.
- Microsoft Learn not connected.
- `applications_sent: null`.
- Some skills lack explicit proficiency evidence.

Freshness:
- Computed at API request time from latest registries.

Confidence:
- High for missing structured fields.
- Medium for skill evidence risk because it depends on available evidence sources.

Computed or stored:
- Computed API projection.

Current defects:
- Repaired: no `Missing certification: Security+` risk when Security+ is resume-confirmed.
- Remaining: legitimate risks listed above.

### Job Readiness

Displayed fields:
- Resume
- GitHub
- LinkedIn
- Portfolio
- Interview
- Applications

Source registry path:
- Career Registry

Source fields:
- `resume_status`
- `github_profile`
- `source_connections.github`
- `portfolio_projects[]`
- `linkedin_status`
- `source_connections.linkedin`
- `portfolio_readiness`
- `interview_readiness`
- `applications_sent`

Source evidence:
- Resume import present: `resume_status: Imported from trusted resume source.`
- GitHub repositories present in `portfolio_projects[]`.
- LinkedIn not connected / needs user action.
- Portfolio partial due to GitHub repository evidence.
- Interview readiness missing.
- Applications tracking missing.

Freshness:
- Career Registry `last_updated`: `2026-06-29T23:10:21Z`

Confidence:
- High for resume/GitHub source status.
- High for missing LinkedIn/interview/applications status because fields are explicit.

Computed or stored:
- Computed API projection.

Current defects:
- Repaired: Job Readiness is now a single API object.
- Remaining: LinkedIn, interview assessment, and applications tracking need user input/source connection.

Expected current projection:
- Resume: connected/imported.
- GitHub: connected/repositories found.
- LinkedIn: not connected.
- Portfolio: partial, based on GitHub.
- Interview: needs assessment.
- Applications: needs input.

### Employment History

Displayed fields:
- role/title
- company/organization
- start/end dates
- source/provenance retained in record

Source registry path:
- Career Registry

Source fields:
- `employment_history[]`

Source evidence:
- Resume import from `/home/yuu/Downloads/MyResume.pdf` with extracted line references.

Freshness:
- Resume imported at `2026-06-29T23:10:21Z`

Confidence:
- High for resume-imported historical roles.

Computed or stored:
- Stored records.

Current defects:
- Good enough. Preserve section. Source/provenance exists in records.

### Career Timeline

Displayed fields:
- organization/company
- title/role
- start/end dates
- type
- source/provenance retained in record

Source registry path:
- Career Registry

Source fields:
- `career_timeline[]`

Source evidence:
- Current employment from registry.
- Historical employment and military service from resume import.

Freshness:
- Resume imported at `2026-06-29T23:10:21Z`

Confidence:
- High for resume-derived historical timeline.
- Medium-high for current registry entry.

Computed or stored:
- Stored regenerated timeline in Career Registry.

Current defects:
- Good enough. Preserve section. Source/provenance exists in records.

### Military Service

Displayed fields:
- branch
- rank
- unit
- role
- dates
- responsibilities
- source/provenance retained in record

Source registry path:
- Career Registry

Source fields:
- `military_service[]`

Source evidence:
- Resume import from `/home/yuu/Downloads/MyResume.pdf`, lines `/tmp/myresume_extracted.txt:98-154`.

Freshness:
- Resume imported at `2026-06-29T23:10:21Z`

Confidence:
- High for resume-derived military service summary.

Computed or stored:
- Stored records.

Current defects:
- Good enough. Preserve section. Source/provenance exists in records.

### Leadership Experience

Displayed fields:
- description
- type
- team size where available
- source/provenance retained in record

Source registry path:
- Career Registry

Source fields:
- `leadership_experience[]`

Source evidence:
- Resume import from `/home/yuu/Downloads/MyResume.pdf`, line ranges including `/tmp/myresume_extracted.txt:101-110`, `/tmp/myresume_extracted.txt:148`, and `/tmp/myresume_extracted.txt:17-24,51-56,66-69,77-80`.

Freshness:
- Resume imported at `2026-06-29T23:10:21Z`

Confidence:
- High for resume-derived descriptions.

Computed or stored:
- Stored records.

Current defects:
- Good enough. Preserve section. Source/provenance exists in records.

## Regression coverage added

- Certification Roadmap and Learning Intelligence reconciliation.
- Certification status separate from course progress.
- AWS SAA selected as primary active target over Security+ 99%.
- Security+ not marked missing when resume/cert registry confirms it.
- Skill Matrix populated from resume, GitHub, learning, and target-role evidence.
- Today’s Study Plan generated from active target priority.
- Job Readiness sourced from source status fields.
- Frontend Career Command component uses API projection fields and excludes known stale hardcoded career literals.
