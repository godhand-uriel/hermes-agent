# Finance Source Audit

Audit timestamp: 2026-06-19T16:05:07Z
Repository: `/home/yuu/.hermes/hermes-agent`
Active Hermes home: `/home/yuu/.hermes/profiles/engineering_lab`

## Registry identity

- Exact registry location: `/home/yuu/.hermes/profiles/engineering_lab/finance/registry.db`
- Resolver: `hermes_cli/finance_registry.py:finance_registry_path()`
- Override env var: `HERMES_FINANCE_REGISTRY_PATH`
- Source type: SQLite
- Table: `finance_snapshots`
- Backend owner: `hermes_cli/finance_registry.py`
- Dashboard API path: `GET /api/dashboard/v2` -> `financial_metrics`
- Finance-specific API paths:
  - `GET /api/finance`
  - `GET /api/finance/widgets`
  - `GET /api/finance/trends/{metric}`
  - `POST /api/finance/snapshots`
  - `POST /api/finance/seed-defaults`
- Frontend consumer: `web/src/pages/ReportsPage.tsx`, `financeCards` in `Finance Command Center`

## Update mechanism

1. `POST /api/finance/snapshots` inserts a new row into `finance_snapshots` through `insert_finance_snapshot()`.
2. `POST /api/finance/seed-defaults` inserts the approved default seed through `seed_default_finance_registry()`.
3. `GET /api/dashboard/v2` calls `dashboard_financial_metrics()`. If the finance registry is uninitialized, that function currently seeds defaults automatically, then rereads the contract.
4. Trends read historical rows from `finance_snapshots` by metric column.

## Current source file status

- File exists: yes
- File size: 24,576 bytes
- File mtime: 2026-06-19T10:58:35Z
- Table exists: yes, `finance_snapshots`
- Snapshot row count observed: 3
- Latest snapshot id: 3
- Latest snapshot captured_at: 2026-06-19T09:39:13Z
- Seed status: initialized with the code's default seed values. The row payload matches `DEFAULT_SEED` shape and includes default note: `Debt account registry initialized; add accounts as balances become available.`

## Current latest contents

Latest observed row:

| Field | Value |
|---|---:|
| annual_income | 52000.0 |
| monthly_income | 4333.33 |
| monthly_expenses | 215.0 |
| emergency_fund | 0.0 |
| car_fund | 0.0 |
| brokerage_value | 0.0 |
| checking_balance | 0.0 |
| savings_balance | 0.0 |
| debt_total | 0.0 |
| net_worth | 0.0 |
| runway_months | 0.0 |
| savings_rate_percent | 95.04 |

Payload keys observed: `annual_income`, `brokerage_contributions`, `brokerage_growth_percent`, `brokerage_value`, `car_fund`, `car_fund_target`, `checking_balance`, `debt_accounts`, `debt_original_total`, `debt_payoff_progress_percent`, `debt_total`, `emergency_fund`, `emergency_fund_target`, `expense_accounts`, `housing`, `metrics`, `monthly_expenses`, `monthly_income`, `net_worth`, `notes`, `runway_months`, `savings_balance`, `savings_rate_percent`, `transportation`.

## Metric verification

| Metric | Source location | Current value | Calculation method | Display risk / `No Metrics Yet` reason |
|---|---|---:|---|---|
| Net Worth | `finance_snapshots.net_worth`; fallback in `calculate_finance_metrics()` | 0.0 | If explicit `net_worth` is null, `checking_balance + savings_balance + emergency_fund + car_fund + brokerage_value - debt_total`. Current seed assets and debt are all 0. | Should not show `No Metrics Yet` when `/api/dashboard/v2` returns finance widgets. If it does, the frontend is using fallback/legacy Reports data or v2 failed. |
| Monthly Income | `finance_snapshots.monthly_income`; derived from `annual_income` when absent | 4333.33 | `annual_income / 12` when `monthly_income` is missing; current seed explicitly stores 4333.33. | Same as above. |
| Monthly Expenses | `finance_snapshots.monthly_expenses`; fallback sum of `expense_accounts` | 215.0 | If `monthly_expenses` is missing, sum `expense_accounts[].amount/balance/current_balance`. Current seed expenses are Electric 100 + Internet 70 + Phone 45. | Same as above. |
| Savings Rate | `finance_snapshots.savings_rate_percent`; metrics payload | 95.04% | `(monthly_income - monthly_expenses) / monthly_income * 100`. With 4333.33 and 215.0 = 95.04%. | Same as above. |
| Runway | `finance_snapshots.runway_months`; metrics payload | 0.0 months | If explicit runway null, `(checking_balance + savings_balance + emergency_fund) / monthly_expenses`. Current liquid assets are 0, expenses 215. | Same as above. |
| Emergency Fund | `finance_snapshots.emergency_fund` and target | 0.0 | Direct stored value. Completion detail uses `emergency_fund / emergency_fund_target * 100`; target is 1000. | Same as above. |
| Car Fund | `finance_snapshots.car_fund` and target | 0.0 | Direct stored value. Completion detail uses `car_fund / car_fund_target * 100`; target is 5000. | Same as above. |
| Brokerage | `finance_snapshots.brokerage_value` | 0.0 | Direct stored value; allocation detail uses brokerage / positive net worth, otherwise null. | Same as above. |
| Debt | `finance_snapshots.debt_total` and `debt_accounts` | 0.0 | If `debt_total` null, sum `debt_accounts`. Current seed has no debt accounts and `debt_total` 0. | Same as above; detail should say no debt accounts registered. |

## Why `No Metrics Yet` appears when it appears

`No Metrics Yet` is a frontend empty-state fallback, not the current finance registry value.

Relevant frontend paths:

- `ReportsPage.tsx` uses `dashboard.financialMetrics.metrics.length ? "data available" : "No Metrics Yet"` for summary health.
- Finance tiles use `metric?.value ?? "No Metrics Yet"`.
- In `buildFallbackDashboard()`, `financialMetrics.metrics` is an empty array because the legacy Reports API has no finance source.

Therefore the finance widgets show `No Metrics Yet` only when:

1. `/api/dashboard/v2` fails and the UI falls back to legacy Reports data; or
2. the v2 response omits `financial_metrics.metrics`, `financial_metrics.widgets`, and `finance_command_center.widgets`; or
3. the finance source is truly uninitialized and the auto-seed path fails.

In the audited local source, the finance DB is initialized and the latest snapshot is readable, so persistent `No Metrics Yet` is a wiring/runtime problem, not absence of registry data.

## Repair recommendation

- Treat current values as seed/default, not bank-verified actual financial truth.
- Add a visible source freshness check from `financial_metrics.source.captured_at` to the dashboard diagnostics.
- Replace seed values by posting a real snapshot through `POST /api/finance/snapshots` only when actual finance source data is approved.
- If UI still shows `No Metrics Yet`, verify `/api/dashboard/v2.financial_metrics.metrics` before changing UI.
