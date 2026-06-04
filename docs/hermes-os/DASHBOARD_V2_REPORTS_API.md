# Dashboard V2 Generated Reports API

Dashboard V2 consumes generated executive reports through the stable endpoints below. All endpoints return JSON and never fall back to the SPA HTML shell.

## Report types

The generated report contract currently reserves these report type slugs:

| Type slug | Label |
| --- | --- |
| `morning_brief` | Daily Morning Brief |
| `evening_report` | Daily Evening Report |
| `weekly_executive_review` | Weekly Executive Review |
| `monthly_executive_review` | Monthly Executive Review |
| `venture_portfolio_rank` | Venture Portfolio Rank |
| `blocked_tasks_review` | Blocked Tasks Review |

The backend also accepts common dash/space aliases such as `morning-brief` and `Weekly Executive Review`.

## Scheduled generation

Command Center report crons use script-only jobs that write JSON into the generated reports directory before delivering the rendered Markdown summary. The monthly executive review schedule is explicit: `0 20 1 * *` (20:00 on the first day of each month) via `executive_reports/monthly_executive_review.sh`.

Daily Executive Brief (`morning_brief` and `evening_report`), Weekly Executive Review, and Monthly Executive Review JSON payloads should embed the latest notification watchdog run under one of these equivalent keys: `notification_watchdog`, `watchdog_status`, `watchdog_results`, or `subscription_watchdog`. The expected source is `hermes kanban watchdog run --mode repair-safe --json`, which writes the same data to the watchdog audit DB at the Kanban home under `notification_watchdog/remediations.db`. The dashboard renderer turns that object into a `Notification watchdog status` section with coverage percentage, total active tasks, tasks missing subscriptions, remediations performed, unresolved issues, remediation history, and risk/recommendation items. If coverage is below 100% or any subscriptions are missing, the rendered report includes an explicit `COVERAGE FAILURE` line.

## Endpoints

### `GET /api/reports/generated`

Returns the full generated report contract:

```json
{
  "version": 1,
  "generated_at": 1780351200,
  "report_types": {
    "morning_brief": { "label": "Daily Morning Brief", "aliases": ["morning brief"] }
  },
  "latest": {
    "morning_brief": {
      "type": "morning_brief",
      "type_label": "Daily Morning Brief",
      "status": "available",
      "report": { "type": "morning_brief", "title": "Daily Morning Brief" },
      "error": null
    }
  },
  "history": {
    "morning_brief": []
  },
  "errors": []
}
```

Query parameters:

| Name | Default | Notes |
| --- | --- | --- |
| `limit` | `20` | Maximum historical reports per type; clamped to 1–100. |

### `GET /api/reports/generated/status`

Returns only the latest status envelope for each report type:

```json
{
  "version": 1,
  "generated_at": 1780351200,
  "reports": {
    "morning_brief": {
      "type": "morning_brief",
      "type_label": "Daily Morning Brief",
      "status": "available",
      "report": { "title": "Daily Morning Brief" },
      "error": null
    },
    "evening_report": {
      "type": "evening_report",
      "type_label": "Daily Evening Report",
      "status": "missing",
      "report": null,
      "error": "No Daily Evening Report report found in configured report directories."
    }
  }
}
```

### `GET /api/reports/generated/latest/{type}`

Returns the latest report envelope for one type. Missing reports return HTTP 200 with `status: "missing"` and `report: null` so Dashboard V2 can show a clear empty state. Unknown type slugs return HTTP 404.

### `GET /api/reports/generated/history/{type}`

Returns historical reports for one type:

```json
{
  "type": "morning_brief",
  "type_label": "Daily Morning Brief",
  "count": 2,
  "reports": []
}
```

Query parameters:

| Name | Default | Notes |
| --- | --- | --- |
| `limit` | `20` | Maximum reports to return; clamped to 1–100. |

### Compatibility surfaces

`GET /api/reports` includes the same contract under `generated_reports` while preserving the existing legacy report fields.

`GET /api/dashboard/v2` includes the same contract under `generated_reports` so Dashboard V2 consumers can retrieve generated reports alongside the board, model, portfolio, and engineering summaries.

## Report item payload

Every available report item has these fields:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string | Stable path-derived ID. |
| `type` | string | One of the report type slugs above. |
| `type_label` | string | Human label for display. |
| `title` | string | JSON `title`, first Markdown H1, or filename-derived title. |
| `status` | string | `available`, `degraded`, or `failed`. Missing reports use an envelope with `status: "missing"`. |
| `error` | string/null | Error text from JSON `error`/`error_message` or Markdown `Error:`/`Failure:`. |
| `path` | string | Absolute source path on the server. |
| `relative_path` | string | Path relative to the discovered report root. |
| `project` | string | Markdown `Project:` value, otherwise `default`. |
| `updated_at` | number | File mtime as Unix seconds. |
| `generated_at` | number | JSON timestamp, filename date (`YYYY-MM-DD`), or file mtime. |
| `content_type` | string | `application/json` or `text/markdown`. |
| `content` | string | Full generated report body for Dashboard V2 rendering. |
| `excerpt` | string | Compact preview. |
| `metadata` | object | JSON report metadata excluding large content/body fields. |

## Source discovery

The backend scans report files with `.md`, `.txt`, and `.json` extensions from:

1. `$HERMES_REPORTS_DIR` when set.
2. Kanban home `reports/` directories.
3. The active Hermes home `reports/` directory.
4. Per-board `reports/` directories under the Kanban boards root.

Reports are classified from explicit JSON `type`/`report_type`/`slug`, filename, title, or heading aliases.

## Dashboard routing QA contract

Dashboard V2 cards must route only to explicit functional targets:

| Clickable item | Expected destination |
| --- | --- |
| Command Brief area card: Career Development | `/reports#career-development` / in-page `#career-development` |
| Command Brief area card: BureauOS | `/reports#bureauos` / in-page `#bureauos` |
| Command Brief area card: Engineering Brand | `/reports#engineering-brand` / in-page `#engineering-brand` |
| Command Brief area card: Artist Management | `/reports#artist-management` / in-page `#artist-management` |
| Command Brief area card: Venture Portfolio | `/reports#venture-portfolio` / in-page `#venture-portfolio` |
| Command Brief area card: Hermes Operations | `/reports#hermes-operations` / in-page `#hermes-operations` |
| Recent task card/title | `/kanban?task=<task_id>` and optionally `board=<board_slug>` when known |
| Active project / board card | `/kanban?board=<project_or_board_slug>` |
| Task assignee/profile link | `/profiles?profile=<profile_name>` |
| Legacy report file card | `/reports?report=<report_id>` readable file detail panel |
| Generated report card | `/reports/generated/<type>` readable generated report detail panel |

QA should treat any dashboard item that falls through to `/sessions` as a routing regression unless the clicked item is explicitly a session-history item. If a metric/card has no real destination yet, it should render as static content or as a disabled control with explanatory copy rather than looking clickable.
