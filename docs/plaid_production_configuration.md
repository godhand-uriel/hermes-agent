# Plaid Production Configuration

This phase configures Hermes for Plaid Production without connecting real bank accounts, requesting Link tokens, deleting Sandbox credentials, or migrating Sandbox data.

## Scope

Configuration only:

- `PLAID_ENV=sandbox` and `PLAID_ENV=production` are both supported by the same Plaid connector.
- The Finance Registry remains the single source of truth for normalized finance data.
- No Finance Registry schema changes are required for environment selection or token namespace separation.
- The data flow remains: Plaid connector -> Finance Registry -> Dashboard.

## Environment variables

Store credential values in Hermes Secrets for the active profile, for example:

```bash
hermes config set PLAID_CLIENT_ID '<client-id>'
hermes config set PLAID_SECRET '<secret>'
```

Hermes routes secret-like values to the active profile `.env` / configured secret source. Do not put real credentials in the repository, docs, tests, or committed config.

Required runtime variables:

```text
PLAID_ENV=sandbox|production
PLAID_CLIENT_ID=<from Hermes Secrets>
PLAID_SECRET=<from Hermes Secrets>
PLAID_PRODUCTS=transactions,liabilities,investments
PLAID_COUNTRY_CODES=US
```

Notes:

- Sandbox remains the default when `PLAID_ENV` is unset.
- Production requires `PLAID_ENV=production` plus all four Plaid configuration variables above.
- Sandbox may use default products and country codes for backward compatibility, but setting them explicitly is recommended.
- Production validation returns friendly missing-variable errors and never prints secret values.
- Money-movement products such as `auth`, `transfer`, `payment_initiation`, `processor_payments`, and `signal` are rejected.

## Directory layout

Plaid access tokens are encrypted and stored outside the Finance Registry in environment-specific namespaces under the active Hermes profile:

```text
$HERMES_HOME/
  finance/
    registry.db
    secrets/
      plaid_token.key
    sandbox/
      access_tokens.json
    production/
      access_tokens.json
```

Security expectations:

- `finance/secrets/` is private (`0700` where supported).
- `finance/secrets/plaid_token.key` is private (`0600` where supported).
- `finance/sandbox/access_tokens.json` and `finance/production/access_tokens.json` are private (`0600` where supported).
- Repository `.gitignore` excludes local finance token and secret paths.

## Token storage

The connector writes new Plaid access tokens to:

- Sandbox: `$HERMES_HOME/finance/sandbox/access_tokens.json`
- Production: `$HERMES_HOME/finance/production/access_tokens.json`

Each file contains encrypted token ciphertext and non-secret metadata such as institution id, item id, product list, and timestamps. Plaintext access tokens are not written to disk.

Production token reads never fall back to Sandbox or legacy unprefixed Sandbox rows. Sandbox token reads keep backward compatibility with older Sandbox token records, but new writes use the Sandbox file namespace.

## Registry boundary

The Finance Registry remains unchanged and continues to be the single source of truth for finance data consumed by the dashboard:

```text
Plaid connector
  -> Finance Registry normalized tables
  -> /api/dashboard/v2 financial_metrics
  -> Dashboard
```

The dashboard must not call Plaid directly and must not read token files or Plaid credentials.

## Rollback procedure

To return to Sandbox configuration without deleting Production credentials or tokens:

```bash
unset PLAID_ENV
export PLAID_ENV=sandbox
```

or set the active Hermes profile secret/config environment back to:

```text
PLAID_ENV=sandbox
PLAID_PRODUCTS=transactions,liabilities,investments
PLAID_COUNTRY_CODES=US
```

Then verify status without requesting a Link token:

```bash
PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab \
  .venv/bin/python -m hermes_cli.main finance sync-status
```

Rollback does not require deleting:

- Sandbox credentials
- Production credentials
- Sandbox token namespace
- Production token namespace
- Finance Registry data

If a future Production phase writes registry data and a full data rollback is required, restore the separately captured `registry.db` backup from before that phase. Do not migrate Sandbox data into Production.

## Verification steps

Configuration-only verification:

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/hermes_cli/test_plaid_connector.py \
  tests/hermes_cli/test_finance_registry.py \
  -q -o 'addopts='

python3 -m py_compile \
  hermes_cli/plaid_connector.py \
  hermes_cli/finance_cli.py
```

Manual non-secret checks:

```bash
PYTHONPATH=. .venv/bin/python - <<'PY'
from hermes_cli.plaid_connector import token_store_path
print(token_store_path('sandbox'))
print(token_store_path('production'))
PY
```

Do not run `finance plaid link-token`, `exchange-token`, or any real bank connection steps during this phase.
