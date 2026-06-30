# BureauOS Registry Audit

Audit timestamp: 2026-06-19T16:05:07Z
Repository: `/home/yuu/.hermes/hermes-agent`
Active Hermes home: `/home/yuu/.hermes/profiles/engineering_lab`

## Registry identity

- Registry file location: `/home/yuu/.hermes/profiles/engineering_lab/ventures/bureauos_applications.json`
- Resolver: `hermes_cli/web_server.py:_bureauos_application_registry_path()`
- Override env var: `HERMES_BUREAUOS_APPLICATION_REGISTRY_PATH`
- Source type: JSON
- Backend loader: `hermes_cli/web_server.py:_load_bureauos_application_registry()`
- API path: `GET /api/dashboard/v2` -> `bureauos_application_registry` and `venture_pipeline`
- Frontend consumers:
  - `BureauOS Overview` -> `BureauOSRows`
  - `Venture Pipeline / Stage Summary` -> `CompactStageSummary`

## File status

- File exists: yes
- File size: 1,509 bytes
- File mtime: 2026-06-19T09:34:17Z
- `last_updated` field: 2026-06-19T09:34:17Z
- Seed status: appears auto-seeded/backfilled from `_DEFAULT_BUREAUOS_APPLICATIONS` in `web_server.py`.

## Update mechanism

1. Edit `bureauos_applications.json`, or set `HERMES_BUREAUOS_APPLICATION_REGISTRY_PATH`.
2. The backend reads top-level `applications`.
3. If no explicit env override is set and default applications are missing, `_load_bureauos_application_registry()` appends missing defaults and writes the file back.
4. Dashboard fetch recalculates `bureauos_application_registry.applications` and `venture_pipeline.stages`.

## Verified required applications

All required applications exist in the current registry:

| Application | Exists | Stage | Confidence | Progress | Next milestone | Blocking issue | Latest research |
|---|---|---|---:|---:|---|---|---|
| DMV Navigator | yes | Research | 45 | 10 | Complete problem research | null | null |
| Veteran Benefits Navigator | yes | Research | 45 | 10 | Complete benefits workflow research | null | null |
| Insurance Denial Navigator | yes | Research | 40 | 8 | Map denial appeal workflows | null | null |
| Tenant Rights Navigator | yes | Research | 40 | 8 | Map tenant-rights jurisdictions | null | null |
| Small Business Compliance Navigator | yes | Research | 40 | 8 | Define compliance scope | null | null |

## Registry boundary rules

The backend only accepts these application slugs:

- `dmv-navigator`
- `veteran-benefits-navigator`
- `insurance-denial-navigator`
- `tenant-rights-navigator`
- `small-business-compliance-navigator`

It also requires the parent venture to canonicalize to BureauOS. Non-allowed applications and non-BureauOS parent ventures are ignored.

## Stage tracking source

Stage tracking source: `applications[].stage` in `/home/yuu/.hermes/profiles/engineering_lab/ventures/bureauos_applications.json`.

The stage is normalized by `_normalize_dashboard_stage()`. If the text equals or contains the first word of a known stage, it maps into the canonical stage bucket.

Accepted stage buckets from `_PIPELINE_STAGES`:

| Stage | Current count |
|---|---:|
| Research | 5 |
| Validation | 0 |
| MVP | 0 |
| Build | 0 |
| Production | 0 |
| Paying Clients | 0 |
| Scale | 0 |

The current pipeline is therefore source-backed but seeded/default-heavy: all five applications are in Research.

## Verified stage list requested

| Requested stage | Supported by code | Current count | Source field |
|---|---|---:|---|
| Research | yes | 5 | `applications[].stage` |
| Validation | yes | 0 | `applications[].stage` |
| MVP | yes | 0 | `applications[].stage` |
| Build | yes | 0 | `applications[].stage` |
| Production | yes | 0 | `applications[].stage` |
| Paying Clients | yes | 0 | `applications[].stage` |
| Scale | yes | 0 | `applications[].stage` |

## Operational assessment

- The registry exists and contains exactly the five required BureauOS applications.
- Stage tracking is real in the sense that it is backed by JSON fields and API rollup code.
- The current contents appear seeded, not validated operational data. There is no evidence of real validation interviews, MVP build status, production deployment, paying clients, or scale data.
- `latest_research` values are null in the actual JSON even though default code literals include research-required strings. That means the current file has less narrative activity than the default constant.

## Repair recommendation

- Keep the application registry as the source of truth.
- Add real stage updates only when backed by research/validation/build artifacts.
- Add `last_activity`, `updated_at`, and `latest_research` to each application when real work occurs.
- Do not infer BureauOS app stage from venture portfolio, Kanban task titles, or UI placeholders.
