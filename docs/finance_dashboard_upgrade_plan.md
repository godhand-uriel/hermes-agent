# Finance Dashboard Upgrade Plan

Goal: modernize Hermes Dashboard finance metrics so they are automatically generated from the existing Finance Registry, never directly from aggregator APIs.

## Source rule

All dashboard metrics must flow through:

`Aggregator -> Finance Registry -> Metrics Engine -> Hermes API -> Dashboard`

Forbidden:

`Dashboard -> Aggregator API`

## Current dashboard state

The dashboard currently renders Finance Command Center cards from the registry-backed `financial_metrics` contract. Visible card labels are:

- Net Worth
- Emergency Fund
- Car Fund
- Brokerage
- Monthly Income
- Monthly Expenses
- Runway
- Debt
- Savings Rate

Current gaps:

- Metrics are based on aggregate seed snapshot fields, not normalized account/transaction data.
- No cash/debt/investment drill-down.
- No data freshness indicators per institution/account.
- No recurring bills or monthly burn detail.
- No travel fund even though future dashboard examples include it.
- No dividend income or asset allocation details beyond brokerage aggregate.

## Target dashboard sections and metrics

### Executive Finance

| Metric | Source in registry | Calculation |
|---|---|---|
| Net Worth | balances + liabilities + holdings | total assets - total liabilities |
| Cash Position | depository account balances + fund accounts | checking + savings + cash-like accounts |
| Debt Position | liabilities + credit balances | credit cards + loans + other debts |
| Savings Rate | income transactions/streams and expense transactions | `(income - expenses) / income` over selected period |
| Monthly Burn | transaction ledger | recurring + average non-discretionary outflows over 30/60/90 days |
| Monthly Income | recurring income streams + deposits | recurring payroll/income average |
| Net Cash Flow | income - expenses | monthly income minus monthly burn/spend |
| Runway | liquid assets / monthly burn | cash/liquid funds divided by burn |

### Funds

| Metric | Source | Calculation |
|---|---|---|
| Emergency Fund Progress | account/fund category + target | current emergency fund / target |
| Car Fund Progress | account/fund category + target | current car fund / target |
| Travel Fund Progress | new `travel_fund` category + target | current travel fund / target |
| Fund Allocation | fund categories | current balances by fund |

Required registry addition: `fund_category` on accounts and/or `finance_funds` table for manual targets.

### Debt

| Metric | Source | Calculation |
|---|---|---|
| Total Debt | liabilities + credit balances | sum balances |
| Debt-Free Projection | liabilities + planned payment rules | amortization/payoff estimate |
| Payoff Progress | original principal vs current | `(original - current) / original` |
| Credit Utilization | credit card balance / credit limit | utilization percent |
| Next Debt Payment | liabilities due dates | minimum upcoming payment |

### Career / Income

| Metric | Source | Calculation |
|---|---|---|
| Current Salary | user-verified income source or W-2 note mapped into registry | annualized salary baseline |
| Annualized Income | income streams | monthly/biweekly income annualized |
| Next Paycheck | recurring income stream | predicted next income date/amount |
| Income Stability | income stream consistency | confidence from recurring detection |

Important: Obsidian W-2 note can seed/annotate a registry income source, but dashboard metrics should read the registry record.

### Investments

| Metric | Source | Calculation |
|---|---|---|
| Portfolio Value | investment holdings | sum holding values |
| Asset Allocation | holdings security/asset class | percent by asset class |
| Dividend Income | investment transactions | trailing 30/90/365 day dividends |
| Contribution Rate | investment transactions/transfers | recurring contribution average |
| Brokerage Growth | value vs contributions/cost basis | growth percent |

## Dashboard UI upgrades

### Finance Command Center top row

Replace simple card grid with compact executive KPI strip:

- Net Worth
- Cash Position
- Debt Position
- Monthly Cash Flow
- Monthly Burn
- Savings Rate

Each card should show:

- value
- trend arrow from latest snapshots
- freshness badge: `fresh`, `stale`, `partial`, `seed`
- source: `Finance Registry`

### Fund progress panel

Visual progress bars/rings:

- Emergency Fund
- Car Fund
- Travel Fund

Each should show:

- current / target
- percent complete
- linked account/category
- last updated

### Debt panel

- Total debt
- Payoff progress bar
- credit utilization
- next payment due
- debt-free projection

### Investments panel

- Portfolio value
- allocation chart
- top holdings
- dividend income
- brokerage growth

### Income and burn panel

- Monthly income
- next paycheck
- recurring bills due next 30 days
- burn breakdown by category
- top spending categories

### Diagnostics drawer

For trust, add a non-executive diagnostics drawer showing:

- registry path
- latest import run id
- last successful sync
- stale account count
- connections requiring reauth
- provider status
- seed/manual/provider-synced status

## API contract additions

Extend `financial_metrics` with:

```json
{
  "source": {
    "type": "finance_registry",
    "configured": true,
    "path": "...",
    "captured_at": 1781861953,
    "snapshot_source": "aggregator",
    "verified_status": "provider_synced",
    "last_successful_sync_at": 1781861953,
    "freshness": "fresh"
  },
  "executive_finance": {...},
  "funds": [...],
  "debt": {...},
  "income": {...},
  "investments": {...},
  "diagnostics": {...}
}
```

Keep existing `metrics` and `widgets` arrays for backward compatibility.

## Data quality display rules

| Registry state | Dashboard behavior |
|---|---|
| Seed only | Show values, but badge `Seed data` in diagnostics; do not imply bank verified |
| Manual user-verified | Show `Manual verified` badge |
| Provider synced fresh | Show normal source-backed cards |
| Provider synced stale | Show values with stale badge and last sync age |
| Partial sync | Show available values with warning |
| Requires reauth | Keep last-known-good values; show action in diagnostics |
| No registry | Show `Source not initialized` and setup action |

## Tests required

Backend tests:

- Metrics engine derives dashboard fields from normalized registry tables.
- Dashboard v2 response includes freshness and verified status.
- Existing `widgets` labels remain backward compatible.
- Seed rows are marked as seed, not provider-synced.
- Stale provider sync preserves last-known-good values.

Frontend tests:

- Finance Command Center renders registry values and freshness badges.
- No component imports provider/Plaid client code.
- Missing optional sections hide gracefully.
- Travel Fund appears only when target/category exists or when a transparent zero/target default is configured.
- Diagnostics drawer contains registry/source status, not secrets.

## Execution order

1. Extend registry schema and metrics engine.
2. Add source freshness/status fields.
3. Add normalized ingestion-derived metrics.
4. Update API contract with new sections while keeping current widgets.
5. Update dashboard UI to render new sections.
6. Add diagnostics drawer.
7. Add frontend/backend regression tests.
