# Finance Registry Audit

Audit timestamp: 2026-06-29T02:44:47Z
Repository: `/home/yuu/.hermes/hermes-agent`
Active Hermes profile home used for live verification: `/home/yuu/.hermes/profiles/engineering_lab`

## Executive summary

The existing Hermes Finance Registry already exists and must remain the source of truth for finance reporting. It is implemented as a local SQLite snapshot store at:

`/home/yuu/.hermes/profiles/engineering_lab/finance/registry.db`

The registry is owned by `hermes_cli/finance_registry.py`, surfaced through finance-specific API endpoints in `hermes_cli/web_server.py`, and consumed by the Hermes Executive Dashboard in `web/src/pages/ReportsPage.tsx`.

Current state is source-backed but only seed/default quality. The latest snapshot is the built-in default seed, not verified bank data. It contains income, expenses, funds, brokerage, cash, debt, net-worth, runway, and savings-rate fields, but does not yet contain normalized accounts, transactions, external institution links, recurring bill records, investment holdings, loan terms, or per-source reconciliation metadata.

## Current architecture diagram

```mermaid
flowchart TD
    A[Manual seed or POST /api/finance/snapshots] --> B[hermes_cli.finance_registry]
    B --> C[(SQLite: finance/registry.db\nfinance_snapshots)]
    C --> D[finance_command_center_contract]
    D --> E[GET /api/finance]
    D --> F[GET /api/finance/widgets]
    C --> G[GET /api/finance/trends/{metric}]
    D --> H[dashboard_financial_metrics]
    H --> I[GET /api/dashboard/v2\nfinancial_metrics]
    I --> J[ReportsPage.tsx\nFinance Command Center]
    K[Obsidian Finance notes] -. narrative only .-> J
```

## Registry location

| Item | Current value |
|---|---|
| Registry resolver | `hermes_cli/finance_registry.py:finance_registry_path()` |
| Default location | `<get_hermes_home()>/finance/registry.db` |
| Live verified path | `/home/yuu/.hermes/profiles/engineering_lab/finance/registry.db` |
| Override env var | `HERMES_FINANCE_REGISTRY_PATH` |
| Storage format | SQLite |
| Table | `finance_snapshots` |
| Source owner | `hermes_cli/finance_registry.py` |
| Dashboard owner | `hermes_cli/web_server.py` + `web/src/pages/ReportsPage.tsx` |

## Storage schema

Live schema from `PRAGMA table_info(finance_snapshots)`:

| Column | Type | Meaning |
|---|---|---|
| `id` | INTEGER PK | Snapshot row id |
| `captured_at` | INTEGER | Unix timestamp for snapshot capture time |
| `annual_income` | REAL | Annual income baseline |
| `monthly_income` | REAL | Monthly income, derived from annual income if omitted |
| `monthly_expenses` | REAL | Monthly expenses/burn, derived from `expense_accounts` if omitted |
| `emergency_fund` | REAL | Emergency fund balance |
| `emergency_fund_target` | REAL | Emergency fund target |
| `car_fund` | REAL | Car fund balance |
| `car_fund_target` | REAL | Car fund target |
| `brokerage_value` | REAL | Brokerage/account investment value aggregate |
| `brokerage_contributions` | REAL | Cost/contribution baseline for brokerage growth |
| `checking_balance` | REAL | Aggregate checking balance |
| `savings_balance` | REAL | Aggregate savings balance |
| `debt_total` | REAL | Aggregate debt balance |
| `debt_accounts` | TEXT JSON | JSON array of debt account summaries |
| `debt_original_total` | REAL | Original debt principal/baseline |
| `net_worth` | REAL | Assets minus debt, derived if omitted |
| `runway_months` | REAL | Liquid assets divided by monthly burn |
| `savings_rate_percent` | REAL | `(monthly_income - monthly_expenses) / monthly_income` |
| `debt_payoff_progress_percent` | REAL | Progress against original debt baseline |
| `brokerage_growth_percent` | REAL | Growth relative to contributions |
| `payload` | TEXT JSON | Full normalized snapshot payload |
| `net_cash_flow` | REAL | Monthly income minus monthly expenses |

Indexes:

- `idx_finance_snapshots_captured_at` on `captured_at`.

## Live registry inventory

Live verification returned:

| Item | Value |
|---|---:|
| DB exists | yes |
| Snapshot row count | 3 |
| Latest snapshot id | 3 |
| Latest captured_at | `1781861953` / `2026-06-19T09:39:13Z` |
| Initialized contract | yes |

Latest observed values:

| Field | Value |
|---|---:|
| `annual_income` | 52000.0 |
| `monthly_income` | 4333.33 |
| `monthly_expenses` | 215.0 |
| `emergency_fund` | 0.0 |
| `car_fund` | 0.0 |
| `brokerage_value` | 0.0 |
| `checking_balance` | 0.0 |
| `savings_balance` | 0.0 |
| `debt_total` | 0.0 |
| `net_worth` | 0.0 |
| `runway_months` | 0.0 |
| `savings_rate_percent` | 95.04 |
| `net_cash_flow` | 4118.33 |

Current Finance Command Center widget labels:

- Net Worth
- Emergency Fund
- Car Fund
- Brokerage
- Monthly Income
- Monthly Expenses
- Runway
- Debt
- Savings Rate

Trend metrics supported by code:

- `net_worth`
- `emergency_fund`
- `car_fund`
- `brokerage_value`
- `brokerage_growth_percent`
- `monthly_income`
- `monthly_expenses`
- `runway_months`
- `debt_total`
- `savings_rate_percent`
- `debt_payoff_progress_percent`
- `net_cash_flow`

## Related Obsidian finance notes

The Obsidian vault has finance narrative/planning notes, but they are not the authoritative numeric registry:

| Path | Role | Notes |
|---|---|---|
| `/home/yuu/Sync/ObsidianVault/Finance/Finance.md` | Operating note | `dashboard_source: true`, finance area narrative, KPIs, blockers, next actions |
| `/home/yuu/Sync/ObsidianVault/Finance/Income/W-2.md` | Income planning note | W-2 role and estimated annual value; `dashboard_source: false` |
| `/home/yuu/Sync/ObsidianVault/Finance/Income/Dividend investments.md` | Empty financial plan | `status: empty`, no financial values |

These notes can provide narrative context and manually verified assumptions, but the dashboard should not calculate financial metrics directly from Markdown when the registry exists.

## Existing ingestion workflows

| Workflow | Endpoint/function | Behavior | Risk |
|---|---|---|---|
| Manual snapshot insertion | `POST /api/finance/snapshots` -> `insert_finance_snapshot(payload)` | Inserts a new normalized row into `finance_snapshots` | No provenance/source metadata; no duplicate detection; no schema for account-level data |
| Default seeding | `POST /api/finance/seed-defaults` -> `seed_default_finance_registry()` | Inserts built-in default seed | Easy to confuse seed defaults with verified financial truth |
| Dashboard auto-seed | `dashboard_financial_metrics()` | If uninitialized, seeds defaults automatically and re-reads contract | Dashboard can silently create placeholder source-backed values |
| History/trends | `GET /api/finance/trends/{metric}` | Reads historical columns from snapshots | Snapshot-only trends do not support per-account drill-down |

No scheduled Hermes cron jobs were present at audit time (`hermes cron list --all` returned no scheduled jobs). No Plaid/MX/Finicity/Teller ingestion job exists yet.

## Dashboard dependencies

| Dependency | File/endpoint | Current behavior |
|---|---|---|
| Backend dashboard API | `GET /api/dashboard/v2` in `hermes_cli/web_server.py` | Calls `dashboard_financial_metrics()` and embeds `financial_metrics` |
| Finance API | `GET /api/finance`, `/api/finance/widgets`, `/api/finance/trends/{metric}` | Returns source-backed finance contract/widgets/trends |
| Snapshot write API | `POST /api/finance/snapshots` | Inserts manual snapshot |
| Seed API | `POST /api/finance/seed-defaults` | Inserts default seed |
| Frontend dashboard | `web/src/pages/ReportsPage.tsx` | Builds `financialMetrics` from API metrics/widgets/finance command center widgets |
| Finance section visible cards | `ReportsPage.tsx` around Finance Command Center | Shows Net Worth, Emergency Fund, Car Fund, Brokerage, Monthly Income, Monthly Expenses, Runway, Debt, Savings Rate |
| Tests | `tests/hermes_cli/test_finance_registry.py` | Verifies metric calculations, empty state, API endpoints, seed/history behavior |

## Source-of-truth analysis

### Current source-of-truth status

The Finance Registry is the intended source of truth and is already the dashboard source. However, the current data inside it is not authoritative financial truth because it is default-seed data and lacks external account reconciliation.

### Sources currently competing or overlapping

| Source | Type | Should it be source of truth? | Reason |
|---|---|---|---|
| SQLite finance registry | Structured local registry | Yes | Existing registry, dashboard already consumes it |
| Obsidian Finance notes | Markdown narrative/planning | No, narrative only | Useful for assumptions, goals, and human notes; not normalized data |
| Frontend fallback values | React fallback builder | No | Should only display empty/error states if registry/API unavailable |
| Aggregator APIs | External read-only data source | No direct dashboard dependency | Must feed registry only; dashboard must never query aggregator directly |
| Seed defaults | Built-in placeholder bootstrap | No | Useful for initialization only; must be labeled and replaced by verified records |

## Data quality issues

| Issue | Severity | Evidence | Recommendation |
|---|---|---|---|
| Seed/default values are source-backed but not bank-verified | High | Latest payload matches default seed shape | Add `source_kind`, `verified_status`, `source_provider`, and `as_of` fields; mark seed rows as `seed` |
| No normalized accounts table | High | Only snapshot aggregate columns exist | Add `finance_accounts` or account JSON table before aggregator ingestion |
| No transaction records table | High | No `transactions` table; only snapshot payload | Add immutable transaction ledger keyed by aggregator transaction id |
| No aggregator connection/item table | High | No storage for item/account linkage or consent state | Add read-only connection metadata table, encrypted token reference, institution id/name, status |
| No recurring bill model | Medium | Only `expense_accounts` list in payload | Add recurring obligations derived from aggregator recurring transactions and manual bills |
| Debt model too shallow | Medium | `debt_accounts` JSON only | Add normalized liability/debt tables for credit cards, loans, interest rates, due dates |
| Investment model too shallow | Medium | `brokerage_value` aggregate only | Add holdings/securities/investment transactions tables |
| No reconciliation/audit metadata | High | No per-row source timestamps or import run ids | Add ingestion run table and reconciliation status per account/transaction/snapshot |
| Dashboard auto-seeding may obscure missing source | Medium | `dashboard_financial_metrics()` auto-seeds if uninitialized | Keep for approved defaults if required, but clearly mark seed/source freshness in dashboard diagnostics |

## Missing financial categories

Current registry covers only aggregate income, expenses, emergency fund, car fund, brokerage, cash, debt, net worth, runway, savings rate, and cash flow.

Missing or under-modeled categories:

- Accounts and institutions
- Transactions and transaction categories
- Recurring bills/subscriptions
- Recurring income/payroll deposits
- Credit cards with utilization, APR, minimum payment, due date
- Loans with principal, interest rate, term, next payment, payoff schedule
- Mortgages/student loans if applicable
- Investment holdings, securities, cost basis, asset allocation
- Investment transactions/dividends
- Manual funds beyond emergency/car, e.g. travel fund
- Reconciliation status/freshness
- Data provenance and user verification status

## Recommended improvements

1. Preserve the existing SQLite registry and module as the canonical finance source.
2. Add normalized registry tables alongside `finance_snapshots`; do not replace `finance_snapshots` immediately.
3. Add aggregator ingestion as a read-only source writer into the registry.
4. Store external provider tokens only through approved provider workflows and encrypted local secret storage if token persistence is required.
5. Add import-run metadata, source timestamps, and reconciliation status.
6. Mark seed/manual/aggregator-derived data explicitly.
7. Keep the dashboard dependent only on Finance Registry APIs/contracts, never aggregator APIs.
8. Build a metrics engine that derives dashboard metrics from normalized registry tables, with snapshots as materialized rollups.
9. Add tests for source boundaries: dashboard -> registry only, aggregator -> registry only, no money movement products enabled.

## Verification commands used

- `hermes cron list --all`
- Live Python import of `hermes_cli.finance_registry` with `HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab`
- SQLite schema/table/count/latest-row inspection
- File reads/searches across:
  - `hermes_cli/finance_registry.py`
  - `hermes_cli/web_server.py`
  - `web/src/pages/ReportsPage.tsx`
  - `tests/hermes_cli/test_finance_registry.py`
  - `/home/yuu/Sync/ObsidianVault/Finance/*`
