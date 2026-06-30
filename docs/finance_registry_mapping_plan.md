# Finance Registry Mapping Plan

Goal: map read-only aggregator data into the existing Hermes Finance Registry without creating a new registry.

Recommended provider: Plaid first. The mapping uses provider-neutral names so MX/Teller/Finicity can be added later.

## Current registry baseline

Existing table:

- `finance_snapshots`

Existing aggregate fields:

- income: `annual_income`, `monthly_income`
- expenses/burn: `monthly_expenses`, `net_cash_flow`
- funds: `emergency_fund`, `emergency_fund_target`, `car_fund`, `car_fund_target`
- brokerage: `brokerage_value`, `brokerage_contributions`, `brokerage_growth_percent`
- cash: `checking_balance`, `savings_balance`
- debt: `debt_total`, `debt_accounts`, `debt_original_total`, `debt_payoff_progress_percent`
- derived: `net_worth`, `runway_months`, `savings_rate_percent`
- full JSON: `payload`

This table should remain as the materialized dashboard rollup while normalized tables are added.

## Required schema changes

Add these tables to the existing SQLite registry database.

### `finance_provider_connections`

Stores read-only provider connection metadata.

| Field | Type | Notes |
|---|---|---|
| `id` | TEXT PK | Internal UUID |
| `provider` | TEXT | `plaid`, `teller`, `mx`, `finicity` |
| `provider_item_id` | TEXT | Provider connection/item id |
| `institution_id` | TEXT | Provider institution id |
| `institution_name` | TEXT | Display name |
| `status` | TEXT | `active`, `requires_reauth`, `revoked`, `error`, `disabled` |
| `products_enabled` | TEXT JSON | Read-only product list |
| `access_token_ref` | TEXT | Reference to encrypted token/secret, not plaintext if possible |
| `created_at` | INTEGER | Unix timestamp |
| `updated_at` | INTEGER | Unix timestamp |
| `last_successful_sync_at` | INTEGER | Unix timestamp |
| `last_error` | TEXT | Sanitized error |

### `finance_accounts`

| Field | Type | Notes |
|---|---|---|
| `id` | TEXT PK | Internal UUID |
| `connection_id` | TEXT FK | Provider connection |
| `provider` | TEXT | Provider name |
| `provider_account_id` | TEXT UNIQUE | Stable provider account id |
| `institution_name` | TEXT | Denormalized display |
| `name` | TEXT | Account display name |
| `official_name` | TEXT | Provider official name |
| `type` | TEXT | `depository`, `credit`, `loan`, `investment`, `other` |
| `subtype` | TEXT | checking/savings/credit card/mortgage/etc. |
| `mask` | TEXT | Last digits only, if available |
| `currency` | TEXT | ISO currency |
| `is_active` | INTEGER | Boolean |
| `include_in_net_worth` | INTEGER | Boolean/manual override |
| `fund_category` | TEXT | `emergency`, `car`, `travel`, `general_cash`, etc. |
| `created_at` | INTEGER | Unix timestamp |
| `updated_at` | INTEGER | Unix timestamp |

### `finance_account_balances`

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Row id |
| `account_id` | TEXT FK | Internal account id |
| `captured_at` | INTEGER | Snapshot time |
| `available_balance` | REAL | Provider available balance |
| `current_balance` | REAL | Provider current balance |
| `limit_amount` | REAL | Credit limit if applicable |
| `currency` | TEXT | Currency |
| `source` | TEXT | provider/manual |
| `import_run_id` | TEXT | Import run |

### `finance_transactions`

| Field | Type | Notes |
|---|---|---|
| `id` | TEXT PK | Internal UUID |
| `account_id` | TEXT FK | Internal account id |
| `provider` | TEXT | Provider |
| `provider_transaction_id` | TEXT UNIQUE | Provider transaction id |
| `pending_provider_transaction_id` | TEXT | For pending->posted matching |
| `date` | TEXT | Transaction date |
| `authorized_date` | TEXT | Authorization date if available |
| `amount` | REAL | Canonical signed amount; define expense positive or negative consistently |
| `currency` | TEXT | Currency |
| `name` | TEXT | Raw/normalized name |
| `merchant_name` | TEXT | Merchant |
| `category_primary` | TEXT | Provider/category normalized |
| `category_detailed` | TEXT | Detailed category |
| `registry_category` | TEXT | Hermes canonical category |
| `is_pending` | INTEGER | Boolean |
| `is_income` | INTEGER | Derived/manual |
| `is_bill` | INTEGER | Derived/manual |
| `recurring_stream_id` | TEXT | Link to recurring item |
| `notes` | TEXT | Manual note |
| `raw_hash` | TEXT | Hash of provider payload |
| `import_run_id` | TEXT | Import run |
| `created_at` | INTEGER | Unix timestamp |
| `updated_at` | INTEGER | Unix timestamp |

### `finance_recurring_items`

| Field | Type | Notes |
|---|---|---|
| `id` | TEXT PK | Internal UUID |
| `provider_stream_id` | TEXT | Provider recurring stream id if available |
| `type` | TEXT | `income`, `bill`, `subscription`, `transfer`, `other` |
| `merchant_or_source` | TEXT | Display name |
| `category` | TEXT | Registry category |
| `average_amount` | REAL | Average recurring amount |
| `last_amount` | REAL | Last observed amount |
| `frequency` | TEXT | weekly/biweekly/monthly/etc. |
| `next_expected_date` | TEXT | Predicted next date |
| `last_date` | TEXT | Last observed date |
| `account_id` | TEXT | Typical account |
| `status` | TEXT | active/inactive/user_ignored |
| `manual_override` | TEXT JSON | User corrections |

### `finance_liabilities`

| Field | Type | Notes |
|---|---|---|
| `id` | TEXT PK | Internal UUID |
| `account_id` | TEXT FK | Account |
| `liability_type` | TEXT | credit_card, student, mortgage, personal_loan, auto_loan |
| `current_balance` | REAL | Current owed |
| `original_principal` | REAL | Original balance |
| `apr_percent` | REAL | Interest rate/APR |
| `minimum_payment` | REAL | Minimum/next payment |
| `next_payment_due_date` | TEXT | Due date |
| `last_payment_amount` | REAL | Last payment |
| `last_payment_date` | TEXT | Last payment date |
| `term_months` | INTEGER | Loan term |
| `maturity_date` | TEXT | Loan maturity |
| `updated_at` | INTEGER | Unix timestamp |

### `finance_investment_holdings`

| Field | Type | Notes |
|---|---|---|
| `id` | TEXT PK | Internal UUID |
| `account_id` | TEXT FK | Investment account |
| `provider_security_id` | TEXT | Provider security id |
| `ticker` | TEXT | Symbol |
| `name` | TEXT | Security name |
| `security_type` | TEXT | equity, ETF, mutual fund, cash, crypto, other |
| `quantity` | REAL | Shares/units |
| `price` | REAL | Latest price |
| `value` | REAL | Market value |
| `cost_basis` | REAL | Cost basis if available |
| `asset_class` | TEXT | Cash/US equity/international/bonds/etc. |
| `captured_at` | INTEGER | Timestamp |
| `import_run_id` | TEXT | Import run |

### `finance_investment_transactions`

| Field | Type | Notes |
|---|---|---|
| `id` | TEXT PK | Internal UUID |
| `account_id` | TEXT FK | Account |
| `provider_investment_transaction_id` | TEXT UNIQUE | Provider id |
| `date` | TEXT | Date |
| `type` | TEXT | buy/sell/dividend/fee/transfer/etc. |
| `ticker` | TEXT | Symbol |
| `quantity` | REAL | Quantity |
| `price` | REAL | Price |
| `amount` | REAL | Amount |
| `fees` | REAL | Fees |
| `currency` | TEXT | Currency |
| `import_run_id` | TEXT | Import run |

### `finance_import_runs`

| Field | Type | Notes |
|---|---|---|
| `id` | TEXT PK | UUID |
| `provider` | TEXT | Provider |
| `connection_id` | TEXT | Connection |
| `started_at` | INTEGER | Start |
| `finished_at` | INTEGER | End |
| `status` | TEXT | success/partial/failed |
| `accounts_seen` | INTEGER | Count |
| `transactions_seen` | INTEGER | Count |
| `records_inserted` | INTEGER | Count |
| `records_updated` | INTEGER | Count |
| `error_summary` | TEXT | Sanitized |
| `source_cursor` | TEXT | Provider cursor if used |

## Aggregator-to-registry mappings

### Accounts

Provider fields map to `finance_accounts`:

| Aggregator concept | Registry field |
|---|---|
| account id | `provider_account_id` |
| item/connection id | `connection_id` |
| institution id/name | `institution_id`, `institution_name` |
| account name | `name` |
| official name | `official_name` |
| type/subtype | `type`, `subtype` |
| mask | `mask` |
| currency | `currency` |
| current/available balance | `finance_account_balances` |

### Transactions

| Aggregator concept | Registry field |
|---|---|
| transaction id | `provider_transaction_id` |
| pending transaction id | `pending_provider_transaction_id` |
| account id | `account_id` |
| date/authorized date | `date`, `authorized_date` |
| amount | `amount` |
| name/merchant | `name`, `merchant_name` |
| category/personal finance category | `category_primary`, `category_detailed`, `registry_category` |
| pending flag | `is_pending` |
| payment channel/location | Optional future fields or JSON extension |

### Balances

| Aggregator concept | Registry field |
|---|---|
| available | `available_balance` |
| current | `current_balance` |
| limit | `limit_amount` |
| iso currency | `currency` |
| timestamp | `captured_at` |

### Income

Income should be derived first from recurring deposits/transactions, then supplemented with provider income products if enabled.

| Aggregator concept | Registry field |
|---|---|
| payroll/income stream | `finance_recurring_items` with `type='income'` |
| deposit transaction | `finance_transactions.is_income=1` |
| gross/net income estimate | materialized snapshot `monthly_income` and future `finance_income_sources` table |
| employer/source name | `merchant_or_source` |
| pay frequency | `frequency` |

### Recurring bills

| Aggregator concept | Registry field |
|---|---|
| recurring outflow stream | `finance_recurring_items` with `type='bill'` or `subscription` |
| merchant | `merchant_or_source` |
| average/last amount | `average_amount`, `last_amount` |
| frequency | `frequency` |
| predicted next date | `next_expected_date` |
| linked transactions | `finance_transactions.recurring_stream_id` |

### Debt / loans / credit cards

| Aggregator concept | Registry field |
|---|---|
| credit/loan account | `finance_accounts.type in ('credit','loan')` |
| balance | `finance_liabilities.current_balance` and balance history |
| APR/interest rate | `apr_percent` |
| minimum/next payment | `minimum_payment` |
| due date | `next_payment_due_date` |
| original principal | `original_principal` |
| loan term/maturity | `term_months`, `maturity_date` |

### Investments

| Aggregator concept | Registry field |
|---|---|
| investment account | `finance_accounts.type='investment'` |
| security | `provider_security_id`, `ticker`, `name`, `security_type` |
| holding quantity/value | `quantity`, `price`, `value` |
| cost basis | `cost_basis` |
| transaction | `finance_investment_transactions` |
| dividend | investment transaction with `type='dividend'`; dashboard derives dividend income |

## Required migrations

Migration order:

1. Add provider connection and import run tables.
2. Add account and balance tables.
3. Add transaction table with unique provider transaction id.
4. Add recurring item table.
5. Add liability table.
6. Add investment holding/transaction tables.
7. Extend `finance_snapshots.payload` to include `snapshot_source`, `import_run_id`, `verified_status`, and `source_freshness`.
8. Update metrics engine to prefer normalized tables and continue emitting legacy widget contract.

## Required new registry fields in snapshots

Add these fields to snapshot payloads and optionally indexed columns later:

- `snapshot_source`: `seed`, `manual`, `aggregator`, `mixed`
- `provider`: `plaid`, `teller`, etc.
- `import_run_id`
- `verified_status`: `seed`, `user_verified`, `provider_synced`, `stale`, `partial`
- `as_of`
- `last_successful_sync_at`
- `stale_account_count`
- `requires_reauth_count`
- `cash_position`
- `debt_position`
- `investment_position`
- `monthly_burn_30d`
- `monthly_income_30d`
- `travel_fund` and `travel_fund_target` if the dashboard will show Travel Fund

## Idempotency rules

- `provider_account_id` must be unique per provider.
- `provider_transaction_id` must be unique per provider.
- Investment transaction ids must be unique per provider.
- Balance snapshots can have many rows per account/captured_at, but ingestion should avoid duplicate import-run balance rows.
- Import runs must be replay-safe.

## Dashboard compatibility

Keep the existing contract:

- `finance_command_center_contract()`
- `dashboard_financial_metrics()`
- `widgets` with labels currently consumed by `ReportsPage.tsx`

Add fields rather than breaking current ones. The dashboard can be modernized after the normalized registry is in place.
