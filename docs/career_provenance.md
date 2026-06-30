# Career Command Provenance

Career Command is a presentation layer over the Dashboard API. The UI must not parse external sources, registry files, Obsidian notes, resumes, GitHub repositories, Udemy pages, Microsoft Learn pages, AWS Skill Builder pages, or any other upstream source directly.

## Canonical lineage

```text
External Sources
  -> Connectors / Importers
  -> Career Registry + Learning Registry
  -> Career Intelligence Layer
  -> GET /api/dashboard/v2.career_progress
  -> Career Command UI
```

## Authoritative registries

- Career Registry: profile dashboard/career_registry.json
- Learning Registry: profile dashboard/learning_registry.json

These are the only authoritative registries for Career Command. External systems can contribute only by writing/importing evidence into one of these registries. The frontend consumes only the Dashboard API projection.

## Provenance contract

Every Career Command projection should be explainable through metadata with this shape:

```json
{
  "value": "AWS Solutions Architect Associate",
  "source": "learning_registry_projection",
  "registry": "Learning Registry",
  "confidence": 0.9,
  "last_updated": "2026-06-30T00:00:00Z",
  "verified": true,
  "evidence": ["Udemy Browser Sync"],
  "computed": true,
  "evidence_count": 1
}
```

The API exposes this at:

- `career_progress.provenance.fields.<field>`
- `career_progress.provenance.lineage`

The UI may show concise provenance labels, but must not expose raw registry internals as editable/source data.

## Click-through explanation model

A displayed learning value such as AWS SAA 93% should explain as:

```text
Career Registry
  -> Learning Registry
  -> Udemy Browser Sync
```

A computed score such as Job Readiness should explain as:

```text
Career Registry fields + Learning Registry summary + portfolio evidence
  -> Career Intelligence job_readiness engine
  -> Dashboard API
  -> Career Command UI
```

## Field categories

### Stored registry fields

Examples: current role, target role, target salary, source connections, resume status, employment history, certifications, portfolio projects.

Stored fields use source `career_registry.<field>` and registry `Career Registry` unless the registry item itself provides a more specific source/evidence record.

### Learning projection fields

Examples: active certification, course progress, provider, secondary learning items, study streak, weekly hours.

Learning fields use source `learning_registry_projection` and registry `Learning Registry`.

### Computed intelligence fields

Examples: certification roadmap, skill matrix, job readiness, career risks, study schedule, portfolio intelligence.

Computed fields include `computed: true` and evidence references back to the registry fields/items used.

## Governance rules

1. No displayed Career Command value may originate only in JSX/TSX.
2. No direct frontend parsing of external sources.
3. No raw upstream provider APIs feed the UI directly.
4. Missing evidence remains missing; do not invent evidence.
5. Scores must include source, registry, confidence, timestamp, and explanation.
6. Risks must include severity, probability, impact, mitigation, source, and confidence.
7. Study schedule blocks must be deterministic from registry-backed inputs.
8. Provider connectors that are not implemented must be documented as not connected/manual evidence, not simulated.
