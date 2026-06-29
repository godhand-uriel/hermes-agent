# Plaid Production Readiness Audit & Migration

Date: 2026-06-29
Scope: Hermes Finance Registry, Plaid connector, dashboard API, frontend Plaid Link flow, token storage, environment handling, sync/recovery controls.
Result: GO for controlled Production credential entry and first-institution verification. Do not switch automatically; keep Sandbox active until the migration checklist is executed.

## Executive Recommendation

Recommendation: GO, with operator-controlled migration only.

Hermes is production-ready for Plaid Pay As You Go from an application-readiness standpoint after this audit. The implementation still defaults to Sandbox and does not connect a real financial institution automatically. Production activation requires explicit local configuration of PLAID_ENV=production and Production credentials in a gitignored/private env file or deployment secret manager.

No real Production Plaid institution was connected during this audit.

## Architecture

```mermaid
flowchart LR
  Browser[Dashboard Frontend] -->|Request short-lived Link token| API[Hermes Backend API]
  Browser -->|Plaid Link JS only; returns public_token| PlaidLink[Plaid Link]
  PlaidLink -->|public_token to frontend callback| Browser
  Browser -->|POST public_token + metadata| API
  API -->|client_id + secret server-side only| PlaidAPI[Plaid API]
  PlaidAPI -->|access_token server-side only| API
  API -->|Fernet encrypt| TokenStore[(Finance Registry: finance_institutions.encrypted_access_token)]
  API -->|accounts/transactions/liabilities/investments sync| Registry[(Finance Registry SQLite)]
  Registry --> Metrics[Registry-derived finance metrics]
  Metrics --> DashboardAPI[/api/dashboard/v2 financial_metrics]
  DashboardAPI --> Browser
```

Source-of-truth boundary: Plaid is ingestion-only. Dashboard metrics are derived exclusively from the Finance Registry. The frontend uses Plaid Link only to obtain a public_token; it does not receive Plaid client secrets or access tokens and does not call Plaid data APIs.

## Phase 1 — Environment Separation

Status: PASS.

Evidence:
- Added support for optional private Plaid env files via HERMES_PLAID_ENV_FILE.
- Added templates:
  - .env.sandbox.template
  - .env.production.template
- Runtime env files remain untracked and gitignored:
  - .env
  - .env.sandbox via *.env
  - .env.production via *.env
  - finance/secrets/plaid_token.key via finance/secrets/
- Production credentials are not required in code and are not committed.
- Env file loader refuses group/world-readable env files.
- Production credentials never reach frontend endpoints; only short-lived link_token, environment label, request_id, sync status, and registry-derived metrics are returned.

## Phase 2 — Configuration

Status: PASS.

Supported variables:
- PLAID_CLIENT_ID
- PLAID_SECRET
- PLAID_ENV
- PLAID_PRODUCTS
- PLAID_COUNTRY_CODES
- HERMES_PLAID_ENV_FILE
- HERMES_FINANCE_TOKEN_KEY_PATH
- HERMES_FINANCE_REGISTRY_PATH

Supported Plaid environments:
- sandbox -> https://sandbox.plaid.com
- production -> https://production.plaid.com

Environment switching is configuration-only. No code edits are required to switch; set PLAID_ENV and credentials in the selected private env file or deployment environment.

## Phase 3 — Security Audit

Status: PASS.

Verified:
- Client secret is only loaded server-side in hermes_cli/plaid_connector.py.
- Plaid access tokens are encrypted with Fernet before storage.
- Public token exchange is server-side only at /api/finance/plaid/exchange-public-token.
- Dashboard API does not return encrypted_access_token, raw access_token, client secret, account numbers, routing numbers, SSNs, usernames, or passwords.
- Registry stores Plaid account mask only, not full account/routing numbers.
- Sync errors sanitize Plaid client id/secret and token-like strings before persistence.
- Finance registry DB permissions are forced to 0600 on open.
- Finance token key directory/file permissions verified: secrets dir 0700, plaid_token.key 0600.
- Runtime secrets remain outside Git; .gitignore protects .env*, *.key, *.secret, and finance/secrets/.

Security notes:
- Existing tests contain fake token strings only; no real secrets were found or required.
- Plaid Link JS is loaded from Plaid CDN in the browser, but data access still flows through Hermes backend only.

## Phase 4 — Multi-Institution Audit

Status: PASS.

Verified/implemented:
- Multiple active Plaid Items are supported through finance_institutions rows.
- Manual sync now enumerates all active encrypted tokens for the configured environment rather than only syncing the most recent Item.
- Environment-prefixed institution storage keys prevent Sandbox and Production credentials from overwriting one another, e.g. sandbox:ins_x and production:ins_x.
- Account uniqueness remains stable by provider_account_id.
- Transaction uniqueness remains stable by transaction_id.
- The Finance Registry merges institutions into one normalized financial picture for dashboard metrics.

Supported account classes through Plaid products and normalized schema:
- Checking
- Savings
- Brokerage / investment
- Credit cards
- Loans
- Retirement/investment accounts where Plaid reports them through accounts/investments

## Phase 5 — Institution Management

Status: PASS for required production migration controls.

Supported:
- Connect Institution: /api/finance/plaid/link-token + /api/finance/plaid/exchange-public-token.
- Reconnect Institution: CLI can issue reconnect/update Link token via `hermes finance plaid reconnect-token`; backend error mapping guides UI to reconnect on expired/revoked Item states.
- Disconnect Institution: `hermes finance disconnect` calls Plaid /item/remove and removes local encrypted tokens.
- Manual Sync: `hermes finance sync` and POST /api/dashboard/v2/finance/sync.
- Automatic Sync Configuration: `hermes finance schedule {manual|hourly|every_6_hours|every_12_hours|daily}` persists cadence/backoff policy in Finance Registry.
- View Sync Status: `hermes finance sync-status` and GET /api/dashboard/v2/finance/sync.
- View Last Sync: latest_finance_sync_status returns last_sync_at and last_successful_sync_at.
- View Errors: latest_finance_sync_status includes recent sanitized errors and per-run history.

## Phase 6 — Finance Registry Integrity

Status: PASS.

Verified/implemented:
- Duplicate transaction prevention: UNIQUE(provider, transaction_id), upsert behavior tested.
- Duplicate account prevention: UNIQUE(provider, provider_account_id), upsert behavior tested.
- Stable institution identifiers: provider + environment-prefixed institution_id.
- Stable account identifiers: provider_account_id retained separately from local row ID.
- Deleted accounts: accounts absent from a later institution sync are marked inactive, not deleted.
- Closed accounts: retained historically via inactive finance_accounts rows plus historical balances/transactions.
- Historical transactions: preserved via upsert, not destructive replace.
- Normalized data and legacy snapshots coexist; normalized registry takes precedence for dashboard metrics.
- Sync queue and schedule tables are idempotently created.

## Phase 7 — Failure Recovery

Status: PASS for application-level protection.

Handled:
- Network failure / timeout: friendly 504 Retry later response.
- Expired access token / revoked institution: friendly reconnect_required response.
- OAuth interruption: friendly oauth_interrupted response.
- Rate limiting: friendly 429 rate_limited response.
- Institution unavailable: friendly 503 institution_unavailable response.
- Partial sync: multi-item sync records per-item errors and returns partial status if at least one Item synced.
- Database rollback: normalized upsert is transactional per sync payload; failed payloads do not commit partial row sets.
- Registry corruption recovery: schema migrations are idempotent; registry path is local SQLite and can be restored/backed up before production migration.

Operational recovery recommendation:
- Before first Production institution, copy registry.db to a timestamped backup.
- If a production sync fails, return to Sandbox by restoring PLAID_ENV=sandbox and HERMES_PLAID_ENV_FILE=.env.sandbox; do not delete production rows until reviewed.

## Phase 8 — Dashboard Verification

Status: PASS.

The Executive Dashboard reads through Finance Registry contracts and /api/dashboard/v2 financial_metrics. Verified KPI areas are registry-derived:
- Net Worth
- Cash
- Investments
- Debt
- Emergency Fund
- Runway
- Savings Rate
- Recent Activity
- Connected Institutions
- Executive Insights

No dashboard data API calls Plaid directly. Frontend API calls are Hermes endpoints only:
- /api/finance/plaid/link-token
- /api/finance/plaid/exchange-public-token
- /api/dashboard/v2/finance/sync
- /api/dashboard/v2

## Phase 9 — Sync Strategy

Status: PASS for configurable strategy and queue primitives.

Implemented supported cadences:
- Manual
- Hourly
- Every 6 hours
- Every 12 hours
- Daily

Implemented primitives:
- finance_sync_schedule table
- finance_sync_queue table
- retry_max_attempts
- retry_backoff_base_seconds
- CLI schedule command
- sanitized sync error history

Note: This audit implemented/persisted scheduling policy and queue primitives. If Hermes scheduler/cron is used for recurring execution, wire it to call `hermes finance sync` at the configured cadence after production migration approval.

## Phase 10 — Production Readiness Report

This document is the readiness report.

Remaining risks:
1. No real Production Plaid institution was connected in this audit by design.
2. Plaid product availability varies by institution; liabilities/investments may be missing for some institutions.
3. OAuth institutions require successful browser completion by the operator.
4. Automatic execution of the schedule depends on the external Hermes scheduler/cron invoking the existing CLI command.
5. Real production rate limits and institution outages can only be fully validated after first controlled Production connection.

Go / No-Go:
- Application readiness: GO.
- Automatic production switch: NO-GO. Do not switch automatically.
- Controlled migration: GO after operator enters production credentials and follows checklist below.

## Testing Evidence

Commands run:

```bash
PYTHONPATH=. HERMES_HOME=/tmp/hermes-test .venv/bin/python -m pytest \
  tests/hermes_cli/test_plaid_connector.py \
  tests/hermes_cli/test_finance_registry.py \
  -q -o 'addopts='
# 22 passed in 1.48s

PYTHONPATH=. HERMES_HOME=/tmp/hermes-test .venv/bin/python -m pytest \
  tests/hermes_cli/test_finance_registry.py \
  tests/hermes_cli/test_plaid_connector.py \
  tests/hermes_cli/test_web_server.py \
  tests/hermes_cli/test_dashboard_navigation_contract.py \
  tests/hermes_cli/test_reports_dashboard_smoke_contract.py \
  tests/hermes_cli/test_reports_page_executive_homepage.py \
  -q -o 'addopts='
# 272 passed, 1 warning in 11.77s

PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m py_compile \
  hermes_cli/finance_registry.py \
  hermes_cli/plaid_connector.py \
  hermes_cli/finance_cli.py \
  hermes_cli/web_server.py
# passed

PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m hermes_cli.main finance sync-status
# passed; returned registry status from Finance Registry

PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m hermes_cli.main finance schedule
# passed; returned manual schedule by default

cd web && npm run build
# tsc -b && vite build passed
```

Registry evidence:
- Live registry: /home/yuu/.hermes/profiles/engineering_lab/finance/registry.db
- Tables include finance_institutions, finance_accounts, finance_transactions, finance_sync_runs, finance_sync_errors, finance_sync_schedule, finance_sync_queue.
- File permissions after audit:
  - registry.db: 0600
  - finance/secrets: 0700
  - plaid_token.key: 0600

## Production Migration Checklist

Do not perform these steps until ready to connect the first real institution.

1. Exactly where to enter Production Plaid credentials

Create a private production env file in the Hermes Agent repo checkout:

```bash
cd /home/yuu/.hermes/hermes-agent
cp .env.production.template .env.production
chmod 600 .env.production
$EDITOR .env.production
```

Enter Production Plaid values in:

```text
PLAID_CLIENT_ID=<Plaid Production client id>
PLAID_SECRET=<Plaid Production secret>
PLAID_ENV=production
PLAID_PRODUCTS=transactions,liabilities,investments
PLAID_COUNTRY_CODES=US
```

2. Exactly which environment variables to change

For Production migration set:

```bash
export HERMES_PLAID_ENV_FILE=/home/yuu/.hermes/hermes-agent/.env.production
export PLAID_ENV=production
```

If credentials are not sourced from HERMES_PLAID_ENV_FILE, set these directly through the deployment secret manager:

```bash
export PLAID_CLIENT_ID=<Plaid Production client id>
export PLAID_SECRET=<Plaid Production secret>
export PLAID_ENV=production
```

3. Exactly which commands to run

Preflight:

```bash
cd /home/yuu/.hermes/hermes-agent
PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m hermes_cli.main finance sync-status
PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m hermes_cli.main finance schedule manual
```

Backup before first real institution:

```bash
cp /home/yuu/.hermes/profiles/engineering_lab/finance/registry.db \
  /home/yuu/.hermes/profiles/engineering_lab/finance/registry.db.pre-plaid-production.$(date +%Y%m%d-%H%M%S)
```

Start Hermes dashboard/backend with Production env loaded, then connect through the dashboard Connect Bank flow. For CLI preflight link token:

```bash
set -a
source /home/yuu/.hermes/hermes-agent/.env.production
set +a
export HERMES_PLAID_ENV_FILE=/home/yuu/.hermes/hermes-agent/.env.production
PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m hermes_cli.main finance plaid link-token
```

After Plaid Link returns a public_token through the dashboard, Hermes exchanges it server-side. If exchanging manually for a controlled test:

```bash
PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m hermes_cli.main finance plaid exchange-token '<PUBLIC_TOKEN_FROM_PLAID_LINK>'
```

Manual first sync:

```bash
PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m hermes_cli.main finance sync
PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m hermes_cli.main finance sync-status
```

Optional schedule after first institution is verified:

```bash
PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m hermes_cli.main finance schedule every_6_hours
```

4. Exactly how to verify the first Production institution

Run:

```bash
PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m hermes_cli.main finance sync-status
```

Verify:
- environment is Production
- status is success or partial with no critical errors
- accounts_count > 0
- last_successful_sync_at is set
- errors is empty or only non-critical institution/product limitations

Then open the dashboard and verify:
- Connected Institutions shows the institution name.
- Net Worth, Cash, Investments, Debt, Emergency Fund, Runway, Savings Rate, Recent Activity, and Executive Insights render from /api/dashboard/v2.
- Browser network requests do not include Plaid client secret or access token.
- No raw account/routing numbers appear in dashboard payloads.

Optional SQLite verification:

```bash
PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python - <<'PY'
import sqlite3
p='/home/yuu/.hermes/profiles/engineering_lab/finance/registry.db'
conn=sqlite3.connect(p)
for table in ['finance_institutions','finance_accounts','finance_transactions','finance_sync_runs']:
    print(table, conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0])
conn.close()
PY
```

5. Exactly how to rollback to Sandbox if needed

Stop Production env usage:

```bash
unset PLAID_CLIENT_ID PLAID_SECRET PLAID_ENV HERMES_PLAID_ENV_FILE
export HERMES_PLAID_ENV_FILE=/home/yuu/.hermes/hermes-agent/.env.sandbox
set -a
source /home/yuu/.hermes/hermes-agent/.env.sandbox
set +a
```

Confirm Sandbox:

```bash
PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m hermes_cli.main finance sync-status
PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m hermes_cli.main finance plaid link-token
```

If the registry itself must be rolled back, restore the backup made before Production:

```bash
cp /home/yuu/.hermes/profiles/engineering_lab/finance/registry.db.pre-plaid-production.<timestamp> \
  /home/yuu/.hermes/profiles/engineering_lab/finance/registry.db
chmod 600 /home/yuu/.hermes/profiles/engineering_lab/finance/registry.db
```

After rollback, run:

```bash
PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m hermes_cli.main finance sync-status
```

Only recommend switching to Plaid Production after the checklist has been completed and the first Production institution verifies cleanly.
