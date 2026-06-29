# Finance Dashboard Data Audit

Scope: Finance Command Center KPI pipeline audit and repair. This audit covers the normalized Finance Registry -> Dashboard API -> frontend API mapping -> React Finance Command Center render path.

Date: 2026-06-29
Registry inspected: /home/yuu/.hermes/profiles/engineering_lab/finance/registry.db
Dashboard endpoint: /api/dashboard/v2
Frontend component: web/src/pages/ReportsPage.tsx, ExecutiveFinanceDashboard()

## Executive Summary

The Plaid ingestion layer and normalized Finance Registry were populated, but the dashboard translation layer still had legacy snapshot-era assumptions. The main defects were:

1. Normalized account aggregation used all active account rows without a complete asset/liability model, which undercounted debt by preferring partial finance_liabilities detail rows over account balances.
2. Net worth calculation only counted checking, savings, emergency, car, and brokerage, not all normalized cash/depository balances.
3. Cash Available showed checking + savings only and omitted money market, cash management, CD, HSA, emergency, and car cash accounts.
4. Credit utilization was not calculated from normalized credit account balances and available credit.
5. Transaction aggregation counted transfers as expenses.
6. Trend charts read legacy finance_snapshots first, so trends could be stale or seeded even when normalized sync history existed.
7. Connected Institutions included a zero-account sandbox row even when live institutions had connected accounts.
8. The frontend expected executive_dashboard.kpis, but several backend KPI fields were null because the normalized translation layer did not populate them.

No frontend direct Plaid financial data calls were added. Plaid remains read-only ingestion. The dashboard continues reading finance data from /api/dashboard/v2.

## Pipeline Map

Finance Registry normalized tables:
- finance_institutions
- finance_accounts
- finance_balances
- finance_transactions
- finance_investments
- finance_liabilities
- finance_sync_runs
- finance_sync_errors

Backend aggregation entrypoints:
- hermes_cli.finance_registry.normalized_finance_snapshot()
- hermes_cli.finance_registry._normalized_finance_aggregate()
- hermes_cli.finance_registry.calculate_finance_metrics()
- hermes_cli.finance_registry.executive_finance_dashboard()
- hermes_cli.finance_registry.dashboard_financial_metrics()

Dashboard API serialization:
- hermes_cli.web_server /api/dashboard/v2 returns financial_metrics.
- financial_metrics.finance_command_center contains source, metrics, sync, and executive_dashboard.
- financial_metrics.executive_dashboard is exposed directly for frontend binding.

Frontend transformation:
- web/src/pages/ReportsPage.tsx normalizeDashboardPayload()
- Reads payload.financial_metrics.finance_command_center and payload.financial_metrics.executive_dashboard.
- Produces DashboardViewModel.financialMetrics.executiveDashboard.

React render binding:
- web/src/pages/ReportsPage.tsx ExecutiveFinanceDashboard()
- Uses financeKpi(exec, key) to bind kpis.
- Uses exec.alerts, exec.connected_institutions, exec.trends, exec.recent_activity, exec.insights, exec.registry_metadata.

## Per-KPI Audit

| KPI | Registry tables/columns | SQL/source query | Python aggregation | API payload | Frontend binding | Expected value source | Actual after repair | Mismatch and fix |
|---|---|---|---|---|---|---|---|---|
| Net Worth | finance_accounts.current_balance/type, finance_investments.investment_holdings | Active account rows; latest investment captured_at | cash_position + brokerage_value - debt_total | executive_dashboard.kpis.net_worth.current and metrics.net_worth | financeKpi(exec, "net_worth").current | Normalized depository assets + latest holdings - credit/loan balances | live: -167768.79 | Previously omitted most cash and undercounted liabilities. Fixed with _normalized_finance_aggregate(). |
| Cash Available | finance_accounts.current_balance where account_type='depository' | SELECT active finance_accounts | Sum all depository balances; bucket checking/savings for display | kpis.cash_available | cash.checking, cash.savings, cash.available_cash | All normalized depository cash accounts | live: 187767.00 | Previously only checking+savings. Fixed to expose total cash_position as available_cash. |
| Monthly Income | finance_transactions.amount/date/category/name | 30-day window anchored to latest registry transaction date, amount < 0, excluding transfers | _normalized_monthly_income_expenses() | kpis.monthly_cash_flow.income and metrics.monthly_income | flow.income | Income transactions from registry | live: 1500.00 | Previously date window depended on wall clock and could miss registry dates; transfers were not excluded. Fixed latest-date anchored SQL and transfer exclusion. |
| Monthly Expenses | finance_transactions.amount/date/category/name | 30-day window anchored to latest registry transaction date, amount > 0, excluding transfers | _normalized_monthly_income_expenses() | kpis.monthly_cash_flow.expenses and metrics.monthly_expenses | flow.expenses | Expense transactions from registry | live: 14398.38 | Previously transfers counted as spend. Fixed transfer exclusion. |
| Monthly Cash Flow | Derived from income/expenses | N/A | income - expenses | kpis.monthly_cash_flow.cash_flow/status | flow.cash_flow and flow.status | Monthly income minus monthly expenses | live: -12898.38 | Depended on income/expense defects. Fixed through source aggregation. |
| Emergency Fund | finance_accounts.current_balance, fund_category or account_name | Active depository account rows | Sum accounts with fund_category='emergency' or emergency in name | kpis.emergency_fund | ef.current/target/progress_percent/status | Dedicated normalized emergency cash accounts | live: 0.00 | Previously only legacy snapshot field. Fixed bucket classification from normalized accounts. |
| Car Fund | finance_accounts.current_balance, fund_category or account_name | Active depository account rows | Sum accounts with fund_category='car' or car fund in name | metrics.car_fund and trends.car_fund_progress | Trend card / widgets | Dedicated normalized car fund accounts | live: 0.00 | Previously only legacy snapshot field. Fixed bucket classification from normalized accounts. |
| Brokerage Value | finance_investments.investment_holdings latest captured_at; fallback investment accounts | SELECT SUM(investment_holdings) at latest captured_at | _latest_investment_value() | kpis.investment_portfolio.current_value and metrics.brokerage_value | inv.current_value | Latest normalized investment holdings | live: 25446.39 | Existing query mostly correct; preserved and wrapped in normalized aggregate. |
| Investment Portfolio | finance_investments and net worth | Latest holdings; allocation calculated against positive net worth | brokerage_value, gain_loss null until cost basis exists, allocation when net worth positive | kpis.investment_portfolio | inv.current_value/gain_loss/allocation | Registry holdings; no fabricated gain/loss | live: value 25446.39, allocation null | Allocation was misleading when net worth was negative. calculate_finance_metrics already nulls allocation unless net worth positive. |
| Debt | finance_accounts.current_balance for credit/loan; finance_liabilities only for detail rows missing account balance | Active credit/loan account rows + unmatched liabilities | _normalized_liability_total() | kpis.debt.total_debt and metrics.total_debt | debt.total_debt | Outstanding credit and loan account balances | live: 380982.18 | Previously preferred partial finance_liabilities rows and undercounted debt as 5201.31. Fixed to use account balances and avoid double counting detail rows. |
| Monthly Burn | Derived from monthly expenses | N/A | monthly_expenses | kpis.monthly_burn.average_monthly_spending | burn.average_monthly_spending | Average monthly spending from expense transactions | live: 14398.38 | Fixed via transaction aggregation. |
| Savings Rate | Derived from income/expenses | N/A | ((income - expenses) / income) * 100 | kpis.savings_rate.monthly_percent | savings.monthly_percent | Registry income and expense transactions | live: -859.89% | Fixed via transaction aggregation. Negative value is registry-derived, not placeholder. |
| Runway | finance_accounts depository cash + monthly expenses | Active depository accounts and expense aggregation | cash_position / monthly_burn | kpis.runway.months_remaining | runway.months_remaining | Cash divided by monthly burn | live: 13.04 months | Previously used only checking+savings+emergency, yielding 0.03. Fixed to use cash_position. |
| Credit Utilization | finance_accounts current_balance/available_balance where account_type='credit' | Active credit rows | current balance / (current + available) * 100 | kpis.credit_utilization.current_utilization/status | util.current_utilization/status | Credit card balance divided by credit limit | live: 52.16%, Watch | Previously null. Fixed _normalized_credit_utilization(). |
| Financial Health Score | Derived metrics: emergency, debt ratio, cash flow, savings rate, credit utilization, liquidity, net worth trend | Uses metrics plus normalized history | executive_financial_health() weighted score | executive_dashboard.financial_health | ExecutiveHealthCard(exec) | Weighted live registry components | live: score 18, Poor | Previously credit/debt/liquidity components used stale/null values. Fixed upstream metrics and history. |
| Dashboard Intelligence | finance_history normalized points + metrics | _normalized_history_points() and current metrics | executive_finance_insights() | executive_dashboard.insights | exec.insights | Live trend deltas | live: net worth decreased, spending changed | Previously could emit generic trend placeholder. Normalized history now uses finance_balances/finance_investments/transactions. |
| Executive Alerts | Metrics and recent activity | recent_finance_activity() + calculated metrics | executive_finance_alerts() | executive_dashboard.alerts | exec.alerts | Actionable registry-backed conditions | live: emergency, cashflow, debt, large transaction, income | Existing alert logic preserved; inputs repaired. |
| Recent Activity | finance_transactions, finance_investments | Transactions newest first; holdings latest first | recent_finance_activity() | executive_dashboard.recent_activity | activity latest_income/largest_recent_expenses/recent_transfers/investment_activity/debt_payments | Registry transactions, holdings, debt payments/transfers/income | live counts: 5,5,5,10,5 | Existing source was normalized; verified populated. |
| Connected Institutions | finance_institutions joined finance_accounts | SELECT i.*, COUNT(a.id), GROUP_CONCAT(account types) | connected_finance_institutions() | executive_dashboard.connected_institutions | exec.connected_institutions | Institution name/status/account count/last sync | live: 2 connected rows after filtering empty sandbox row | Previously showed zero-account Plaid Sandbox row. Fixed to omit zero-account rows when connected institutions exist. |
| Trend Charts | finance_balances, finance_investments, finance_transactions | _normalized_history_points(metric) grouped by sync_run_id | finance_history() prefers normalized history | executive_dashboard.trends | exec.trends -> MiniBars | Historical normalized snapshots/sync history | live: 6 points per chart | Previously finance_history read legacy finance_snapshots first. Fixed normalized history preference. |
| Last Successful Sync | finance_sync_runs.completed_at/status | latest_finance_sync_status() | latest sync status | kpis.last_successful_sync and financial_metrics.sync | lastSync + finance.sync | Successful registry sync run | live: 1782740436, duration 4s | Existing source preserved. |

## Legacy Code Search

Searched for:
- finance_snapshots
- legacy Finance Registry fields
- deprecated APIs / old DTOs
- obsolete serializers
- mockFinance / mockPlaid
- hardcoded demo values
- temporary fallback values

Findings:
- finance_snapshots still exists as backward-compatible manual snapshot storage and fallback when normalized registry tables are empty.
- Dashboard aggregation now prefers normalized registry data whenever finance_accounts exist.
- Executive dashboard trends now prefer normalized finance_balances / finance_investments / finance_transactions before legacy finance_snapshots.
- No mockFinance/mockPlaid/demo finance data is used in the Finance Command Center frontend render path.
- No raw Plaid access token is serialized to the dashboard.

## Fixes Applied

Backend:
- Added _normalized_finance_aggregate().
- Added _normalized_liability_total() to use active credit/loan account balances and avoid liability double-counting.
- Added _normalized_credit_utilization().
- Added _normalized_monthly_income_expenses() anchored to latest transaction date and excluding transfers.
- Added _normalized_history_points() and changed finance_history() to prefer normalized registry history.
- Changed normalized_finance_snapshot() to use the normalized aggregate.
- Changed calculate_finance_metrics() to use cash_position for assets and runway when present.
- Fixed Plaid loan ingestion mapping to avoid using mortgage current_late_fee as principal.
- Filtered zero-account institutions when real connected institutions exist.
- Corrected debt monthly reduction to report reduction as the inverse of debt change.

Frontend:
- No UI redesign was performed for this audit.
- Existing ExecutiveFinanceDashboard bindings were verified against executive_dashboard.kpis, alerts, trends, institutions, activity, insights, registry_metadata, and sync history.
- Regression test now asserts the finance render path has no mock/demo/placeholder finance data dependencies.

Tests added/updated:
- Normalized registry KPI fixture proving dashboard values come from normalized registry tables.
- API payload test proving /api/dashboard/v2 finance payload carries normalized executive dashboard values.
- Frontend source contract proving no mock/demo/placeholder finance dependency in ExecutiveFinanceDashboard.
- Existing empty-state contract updated to reflect the requirement that placeholders not remain in the Finance Command Center main path.

## Live Verification Snapshot

Live registry counts observed before repair:
- Institutions: 3
- Accounts: 36
- Balance snapshots: 72
- Transactions: 144
- Investments: 78
- Liabilities: 9
- Successful syncs: 6

Live dashboard values after repair from /api/dashboard/v2:
- Net Worth: -167768.79
- Cash Available: 187767.00
- Monthly Income: 1500.00
- Monthly Expenses: 14398.38
- Monthly Cash Flow: -12898.38
- Brokerage / Investments: 25446.39
- Debt: 380982.18
- Monthly Burn: 14398.38
- Runway: 13.04 months
- Savings Rate: -859.89%
- Credit Utilization: 52.16% Watch
- Financial Health Score: 18 / 100, Poor
- Connected Institutions displayed: Platypus No Products, First Platypus Bank
- Trend charts: 6 normalized points each
- Recent activity: populated from transactions/investments/debt/transfer classifications
- Dashboard intelligence: live trend-backed insights, no generic placeholder messages

## Verification Commands

Required verification command:

PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m pytest tests/hermes_cli/test_plaid_connector.py tests/hermes_cli/test_finance_registry.py tests/hermes_cli/test_web_server.py tests/hermes_cli/test_reports_page_executive_homepage.py tests/hermes_cli/test_reports_dashboard_smoke_contract.py tests/hermes_cli/test_dashboard_navigation_contract.py -q -o 'addopts='

Frontend build:

cd web && npm run build

Live sync status:

PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m hermes_cli.main finance sync-status
