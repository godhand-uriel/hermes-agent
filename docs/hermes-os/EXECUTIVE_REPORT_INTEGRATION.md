# Executive Report Integration

## Purpose

This deliverable records how notification watchdog results are integrated into Command Center executive reporting. The goal is to make notification coverage visible in the Daily Executive Brief, Weekly Executive Review, and Monthly Executive Review so coverage failures cannot silently persist.

## Where the data appears

Watchdog results appear in generated executive report content as a dedicated `Notification watchdog status` section.

Covered report cadences:

| Cadence | Generated report type(s) | Required watchdog entry |
| --- | --- | --- |
| Daily Executive Brief | `morning_brief`, `evening_report` | Latest watchdog status for the day, including coverage failure callouts and any safe remediations performed. |
| Weekly Executive Review | `weekly_executive_review` | Latest coverage status plus remediation history and high/critical unresolved risks from the reporting period. |
| Monthly Executive Review | `monthly_executive_review` | Latest coverage status plus monthly remediation history, unresolved issues, and recurring risks/recommendations. |

Each entry summarizes:

* Coverage percentage.
* Total active tasks.
* Tasks missing subscriptions.
* Remediations performed.
* Unresolved issues.
* Remediation history.
* Notable risk/recommendation items.

Coverage below 100% or any missing subscriptions renders an explicit `COVERAGE FAILURE` line.

## How the data is generated

The source of truth is the deterministic notification watchdog:

```bash
hermes kanban watchdog run --mode repair-safe --json
```

That command audits the scoped Command Center boards, performs safe subscription repairs when a canonical Telegram target is available, emits JSON, and writes audit rows to the Kanban home audit database:

```text
notification_watchdog/remediations.db
```

Report-generation jobs should embed the watchdog JSON payload in their generated report JSON under any of these equivalent keys:

* `notification_watchdog`
* `watchdog_status`
* `watchdog_results`
* `subscription_watchdog`

Dashboard/report rendering then converts that object into readable Markdown. The raw payload remains available in report metadata for audit/replay.

## Rendering contract

The generated report renderer in `hermes_cli/web_server.py` recognizes the watchdog payload and emits:

```markdown
## Notification watchdog status
- Status: uncovered — 3/4 active tasks (75.0% coverage); missing subscriptions: 1; remediations performed: 2; unresolved issues: 1
- COVERAGE FAILURE: 1 active task(s) are missing Command Center notification subscriptions.
- Remediation history: add_missing_subscription=1, reset_stale_cursor=1
- Risk/recommendation item: high command-center-board task=t_missing123: missing_subscription (open)
```

This makes coverage failures obvious to executives while preserving remediation details for operators.

## Updated specifications

* `docs/hermes-os/HERMES_REPORTING_SPEC.md` now requires watchdog status in the Daily Morning Brief, Daily Evening Report, Weekly Executive Review, and Monthly Executive Review sections.
* `docs/hermes-os/DASHBOARD_V2_REPORTS_API.md` documents the generated-report payload keys, watchdog command source, audit DB source, rendered fields, and coverage-failure behavior.
* `tests/hermes_cli/test_web_server.py` covers JSON report normalization with embedded watchdog data, including coverage percentage, coverage failure callout, remediation history, and risk item rendering.
