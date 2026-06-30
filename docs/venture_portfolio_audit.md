# Venture Portfolio Audit

Audit timestamp: 2026-06-19T16:05:07Z
Repository: `/home/yuu/.hermes/hermes-agent`
Active Hermes home: `/home/yuu/.hermes/profiles/engineering_lab`

## Registry identity

- Source file: `/home/yuu/.hermes/profiles/engineering_lab/ventures/registry.json`
- Resolver: `hermes_cli/web_server.py:_venture_registry_path()`
- Override env var: `HERMES_VENTURE_REGISTRY_PATH`
- Source type: JSON, with optional Kanban rollups for explicitly attached tasks
- Backend loader: `hermes_cli/web_server.py:_load_venture_registry()`
- Dashboard rollup: `_dashboard_registered_ventures()`
- Generated rank envelope: `_generated_venture_portfolio_rank_envelope()`
- API path: `GET /api/dashboard/v2` -> `venture_registry`, `portfolio_ventures`, `portfolio_health`
- Frontend consumer: `web/src/pages/ReportsPage.tsx`, `VentureRows` under `Registered Venture Command`

## Current file status

- File exists: yes
- File size: 913 bytes
- File mtime: 2026-06-18T22:34:00Z
- Top-level schema: `{ "version": 1, "ventures": [...] }`

## Canonical venture boundary

The backend canonical boundary currently accepts:

- `bureauos`
- `parlay-analyzer`
- `trustbase`

Aliases normalize some alternate names. In code comments, the intended boundary is BureauOS, Parlay Analyzer, and TrustBase. The broader user memory says Venture Portfolio must display only explicitly registered ventures: BureauOS, Parlay Analyzer, Trust Base Social Platform, and Frontend Streaming Platform. Current code, however, only accepts the three canonical ids above; Frontend Streaming Platform is present in the JSON but ignored by current loader because it is not in `_CANONICAL_DASHBOARD_VENTURE_IDS`.

## Current registry contents and source audit

| Venture | Registry entry | Accepted by backend | Priority source | Confidence source | Last activity source | Milestone source | Current milestone |
|---|---|---|---|---|---|---|---|
| BureauOS | `id: bureauos`, `name: BureauOS` | yes | `rank` if present, else registry order / canonical order | `confidence: 72` | `latest_activity`, `latest_research`, `updated_at`, or explicit Kanban task rollup; current registry lacks these fields | `next_milestone` | Select First MVP |
| Parlay Analyzer | `id: parlay-analyzer`, `name: Parlay Analyzer` | yes | `rank` if present, else registry order / canonical order | `confidence: 64` | Same as above; current registry lacks activity fields | `next_milestone` | Define Core User Workflow |
| TrustBase | Current JSON uses `id: trust-base-social-platform`, `name: Trust Base Social Platform`, `aliases: [TrustBase]` | yes, via alias/canonicalization to `trustbase` | `rank` if present, else registry order / canonical order | `confidence: 68` | Same as above; current registry lacks activity fields | `next_milestone` | Validate Trust Model |

Additional registry row:

| Venture | Registry entry | Accepted by backend | Reason |
|---|---|---|---|
| Frontend Streaming Platform | `id: frontend-streaming-platform`, `name: Frontend Streaming Platform` | no | Current backend canonical allowlist excludes it. It is in the JSON but filtered out before dashboard rollup. |

## Priority source

Priority/rank is calculated in `_load_venture_registry()`:

1. Use `raw.rank` if present.
2. Else use canonical order index: BureauOS first, Parlay Analyzer second, TrustBase third.
3. `_dashboard_registered_ventures()` sorts by `rank` and `registry_index`.

The current JSON has no explicit `rank` fields, so priority is generated from canonical order, not an explicit business priority field.

## Confidence source

Confidence is source-backed from `ventures[].confidence`:

- BureauOS: 72
- Parlay Analyzer: 64
- TrustBase / Trust Base Social Platform: 68

The frontend displays confidence from `data.confidence ?? data.score`.

## Last activity source

Potential sources:

- Venture registry fields: `latest_activity`, `latest_research`, `updated_at`
- Kanban rollup field: `latest_activity_at` derived from explicitly attached tasks

Important issue: `_dashboard_registered_ventures()` sets `latest_activity_at` to `metrics.latest_activity_at or now`. If no explicit Kanban activity exists, the backend can emit the current request time as `latest_activity_at`. That makes the UI look active even when registry activity fields are absent. Conversely, the venture drawer displays `No Activity Yet` if `latest_activity_at` is absent from the frontend data.

Current registry lacks `latest_activity`, `latest_research`, and `updated_at` for all three audited ventures. Any `No Activity Yet` text is therefore a generated empty-state placeholder unless real Kanban tasks are explicitly attached.

## Milestone source

Milestone source is `ventures[].next_milestone` or `ventures[].milestone`.

Current values:

- BureauOS: Select First MVP
- Parlay Analyzer: Define Core User Workflow
- TrustBase: Validate Trust Model

These are source-backed registry strings.

## Why `Not Started` appears

`Not Started` is a frontend fallback, not a registry value, in these places:

- Venture drawer: `drawer.data?.stage || "Not Started"`, `drawer.data?.status || "Not Started"`, `drawer.data?.next_milestone || drawer.data?.recommendation || "Not Started"`
- Venture rows: `data?.stage || data?.status || "Not Started"`, and `data?.next_milestone || data?.recommendation || "Not Started"`

For the current accepted ventures, `stage` and `next_milestone` exist in the registry. `status` does not exist, but backend fills `status` with `No data available`.

Therefore `Not Started` should only display when:

1. The venture row lacks `data` because the API did not return a matching `portfolio_ventures` item; or
2. `/api/dashboard/v2` failed and the frontend is on fallback data; or
3. a venture is listed in UI from a non-registry source and cannot be matched to a registry entry.

## Why `No Activity Yet` appears

`No Activity Yet` is a frontend fallback for missing activity/research fields:

- Row last activity: `venture.research || (data?.latest_activity_at ? formatDate(data.latest_activity_at) : "No Activity Yet")`
- Drawer last activity: `drawer.data?.latest_activity_at ? formatDate(...) : "No Activity Yet"`
- Drawer research: `drawer.research || "No Activity Yet"`

The current registry does not contain activity fields, and the audited JSON does not contain explicit task/activity history. If no explicit Kanban rollup attaches activity, `No Activity Yet` is accurate as an empty state.

## Repair recommendation

- Add explicit `rank` fields if priority matters operationally.
- Add `status`, `latest_activity`, `latest_research`, and `updated_at` when real venture work occurs.
- Decide whether Frontend Streaming Platform should remain in the portfolio. Current memory says yes; current code filters it out. This is a data contract mismatch, not a UI layout issue.
- Do not infer venture activity from task/report names unless tasks explicitly attach via venture id/name/alias.
