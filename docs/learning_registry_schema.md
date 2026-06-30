# Learning Registry Schema

The Learning Registry is the structured source of truth for learning progress.

Path:

`/home/yuu/.hermes/profiles/engineering_lab/dashboard/learning_registry.json`

## Source flow

```text
Obsidian Notes
  ↓
Learning Sync Engine
  ↓
Learning Registry
  ↓
Career Registry executive projection
  ↓
Career Command UI
```

Career Command must not parse Obsidian directly. It reads the Career Registry / dashboard API career contract only.

## Top-level shape

```json
{
  "schema_version": 1,
  "last_updated": "2026-06-30T00:00:00Z",
  "sources": {},
  "providers": [],
  "certifications": [],
  "courses": [],
  "modules": [],
  "study_sessions": [],
  "learning_streak": {},
  "study_recommendations": [],
  "source_evidence": [],
  "manual_review": []
}
```

Every imported or derived record includes:

- `source`
- `confidence`
- `last_updated`
- `evidence_path` when sourced from Obsidian

## Sources

Connected/source-status records live under `sources`.

Current source policy:

- `obsidian`: connected if the vault path exists.
- `manual`: allowed for future user-supplied entries.
- `microsoft_learn`: not connected. Needed action: export transcript/progress or provide screenshots.
- `aws_skill_builder`: not connected. Needed action: export completion/progress evidence or provide screenshots/PDF.

Microsoft Learn and AWS Skill Builder are not treated as connected personal-progress APIs because they do not expose reliable public personal-progress APIs for this use case.

## Provider records

```json
{
  "id": "aws",
  "name": "AWS",
  "status": "connected_by_evidence",
  "source": "obsidian",
  "confidence": 0.95,
  "last_updated": "2026-06-30T00:00:00Z",
  "evidence_path": "Learning/AWS/AWS SAA.md"
}
```

## Certification records

```json
{
  "id": "cert_aws_<hash>",
  "name": "AWS Solutions Architect Associate",
  "provider": "AWS",
  "status": "in_progress",
  "progress_percent": 15,
  "last_studied": "2026-06-29",
  "next_action": "Complete VPC module",
  "source": "obsidian",
  "confidence": 0.95,
  "last_updated": "2026-06-30T00:00:00Z",
  "evidence_path": "Learning/AWS/AWS SAA.md"
}
```

## Course and module records

Courses and modules use the same evidence policy as certifications. A note may provide a certification, course, module, or any combination. Missing progress remains `null`; the sync engine must not invent progress.

## Study sessions

Study-session records are created when a learning note contains `last_studied`, `study_hours`, or `weekly_study_hours`.

```json
{
  "id": "study_<hash>",
  "date": "2026-06-29",
  "provider": "AWS",
  "certification": "AWS Solutions Architect Associate",
  "course": "AWS SAA Study Plan",
  "module": "VPC fundamentals",
  "hours": 1.5,
  "weekly_hours": 4.0,
  "next_action": "Complete VPC module",
  "source": "obsidian",
  "confidence": 0.95,
  "last_updated": "2026-06-30T00:00:00Z",
  "evidence_path": "Learning/AWS/AWS SAA.md"
}
```

## Learning streak

`learning_streak` is derived only from study sessions with explicit dates.

If no dated study session exists:

```json
{
  "current_days": 0,
  "last_studied": null,
  "source": "learning_registry",
  "confidence": 0.0,
  "last_updated": "...",
  "evidence_path": null
}
```

## Career Registry projection

Only executive summary fields are projected into Career Registry under `learning_summary`:

- `primary_certification`
- `certification_progress`
- `next_learning_task`
- `study_streak_days`
- `last_studied`
- `weekly_study_hours`
- `learning_risk`
- `next_recommendation`
- provider connection statuses
- source/confidence/evidence metadata

Full learning history remains in Learning Registry and is not duplicated into Career Registry.
