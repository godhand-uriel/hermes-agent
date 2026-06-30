# Learning Registry Sync Report

Generated: 2026-06-30

## Implemented flow

```text
Obsidian Notes
  ↓
Learning Sync Engine (`hermes_cli/learning_registry.py`)
  ↓
Learning Registry (`learning_registry.json`)
  ↓
Career Registry (`career_registry.json.learning_summary`)
  ↓
Career Command UI (`CareerCommandConsole`)
```

Career Command continues to read `career_progress` from `/api/dashboard/v2`; it does not parse Obsidian directly.

## Sync engine

Implemented module:

`hermes_cli/learning_registry.py`

Responsibilities:

- Resolve Obsidian vault path.
- Read markdown notes.
- Parse YAML/frontmatter.
- Import only safe structured fields.
- Preserve Obsidian evidence paths.
- Deduplicate providers/certifications/courses/modules by stable IDs.
- Create study sessions only when explicit study date/hour fields exist.
- Avoid invented progress by leaving unclear fields `null`.
- Log ambiguous notes/fields to `manual_review`.
- Write Learning Registry.
- Project executive summary into Career Registry.

## Current sync result

Command executed:

```bash
PYTHONPATH=/home/yuu/.hermes/hermes-agent python3 - <<'PY'
from pathlib import Path
from hermes_cli.learning_registry import sync_obsidian_learning_registry
print(sync_obsidian_learning_registry(vault_path=Path('/home/yuu/Sync/ObsidianVault')))
PY
```

Result:

```text
vault_path: /home/yuu/Sync/ObsidianVault
notes_scanned: 24
learning_notes: 7
records_created: 0
manual_review_count: 3
learning_registry_path: /home/yuu/.hermes/profiles/engineering_lab/dashboard/learning_registry.json
career_registry_path: /home/yuu/.hermes/profiles/engineering_lab/dashboard/career_registry.json
```

Why records_created is 0: the current vault has learning keywords but no typed `type: learning` notes with structured provider/certification/course/module frontmatter. The engine intentionally did not convert dashboard prompt text or operating-note prose into learning progress.

## Current Learning Registry status

- Obsidian: Connected.
- Manual entries: Allowed.
- Microsoft Learn: Not connected.
- AWS Skill Builder: Not connected.
- Certifications: none imported from Obsidian yet.
- Courses: none imported from Obsidian yet.
- Modules: none imported from Obsidian yet.
- Study sessions: none imported from Obsidian yet.
- Learning streak: 0 days because no dated study-session field was present.

## Manual review items

The sync engine found learning keywords in these notes but did not import progress:

- `Business Ventures/Engineering Brand/Engineering Brand.md`
- `Career Development/Career Development.md`
- `Personal/Reading.md`

Recommended action: convert real learning progress into typed notes under `Learning/` using the schema in `docs/learning_registry_schema.md`.

## Missing provider access

Microsoft Learn and AWS Skill Builder remain missing connected sources.

Required user actions:

- Microsoft Learn: export transcript/progress or provide screenshots.
- AWS Skill Builder: export completion/progress evidence or provide screenshots/PDF.

## Career Registry projection

The sync wrote a `learning_summary` executive projection into:

`/home/yuu/.hermes/profiles/engineering_lab/dashboard/career_registry.json`

Because no verified structured Obsidian progress exists yet, the summary does not fabricate a primary certification/progress from note prose. It does include provider connection statuses and the recommendation to standardize learning notes.

## UI update

Career Command now contains a `Learning Intelligence` card backed by `career_progress.learning_summary`.

Displayed fields:

- Primary certification
- Progress
- Last studied
- Study streak
- Today’s study task
- Weekly study progress
- Learning risk
- Next recommendation
- Microsoft Learn connection status

## Verification commands

Targeted tests run:

```bash
PYTHONPATH=/home/yuu/.hermes/hermes-agent /home/yuu/.hermes/hermes-agent/.venv/bin/python -m pytest \
  tests/hermes_cli/test_learning_registry.py \
  tests/hermes_cli/test_web_server.py \
  tests/hermes_cli/test_reports_page_executive_homepage.py \
  -q -k 'learning_registry or extended_career_registry or career_command' \
  -o 'addopts='
```

Result: `9 passed, 241 deselected`.

Frontend build run from `web/`:

```bash
npm run build
```

Result: TypeScript build and Vite production build completed successfully. Vite emitted only the existing large-chunk warning.

API contract smoke check:

```bash
PYTHONPATH=/home/yuu/.hermes/hermes-agent /home/yuu/.hermes/hermes-agent/.venv/bin/python - <<'PY'
from hermes_cli.web_server import _dashboard_career_registry_contract
career = _dashboard_career_registry_contract()
print(career.get('learning_summary'))
PY
```

Result: Career contract contains `learning_summary.source == learning_registry` and currently reports `learning_risk == Needs learning source standardization` because no typed learning note has been imported yet.
