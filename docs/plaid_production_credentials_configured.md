# Plaid Production Credentials Configured

## Scope

Phase 3 configured Plaid Production credentials for Hermes Finance without connecting real bank accounts, creating a Plaid Link token, exchanging a public token, or running a production sync.

No secrets are included in this document.

## Credential Source

- Source path: `/home/yuu/.hermes/profiles/engineering_lab/.env.production`
- Loader path: `hermes_cli.plaid_connector.plaid_config_from_env()` loads the profile-scoped production env file when `PLAID_ENV=production`; `HERMES_PLAID_ENV_FILE` can still be used as an explicit override/fallback.
- File exists: yes
- File permissions: `0600`
- Git protection: repo `.gitignore` includes `.env`, `*.env`, `*.key`, `*.secret`, and `finance/*/access_tokens.json`; the credential file is profile-local outside the repo checkout.

## Production Configuration

- `PLAID_ENV`: `production`
- Products: `transactions`, `auth`, `identity`, `liabilities`, `investments`
- Country codes: `US`
- Credential values: present, validated by safe length/presence checks only; full values were not printed.

## Safe Credential Presence Validation

| Key | Present | Length | Placeholder |
| --- | --- | ---: | --- |
| `PLAID_ENV` | true | 10 | false |
| `PLAID_CLIENT_ID` | true | 24 | false |
| `PLAID_SECRET` | true | 30 | false |
| `PLAID_PRODUCTS` | true | 50 | false |
| `PLAID_COUNTRY_CODES` | true | 2 | false |

## Production Configuration Dry Run

Command run:

```bash
PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m hermes_cli.main finance plaid validate-production-config
```

Result summary:

- Environment: `production`
- Credentials loaded: true
- Products valid: true
- Country codes valid: true
- Production token namespace path: `/home/yuu/.hermes/profiles/engineering_lab/finance/production`
- Production token store path: `/home/yuu/.hermes/profiles/engineering_lab/finance/production/access_tokens.json`
- Production token namespace exists: true
- Production token records: 0
- Production legacy registry token rows: 0
- Sandbox token namespace path: `/home/yuu/.hermes/profiles/engineering_lab/finance/sandbox`
- Sandbox token namespace exists: true
- Sandbox and production token stores are separate: true
- Errors: none

The dry run does not call Plaid Link, does not exchange a public token, and does not sync provider data.

## Safety Checks

- Sandbox tokens remain separate: true
- Production token namespace is empty before first connection: true
- No production access token exists yet: true
- Registry backup exists: true
- Sandbox baseline exists: true (`docs/plaid_sandbox_baseline_before_production.md`)
- Backup path verified from baseline: `/home/yuu/.hermes/profiles/engineering_lab/finance/backups/registry_sandbox_before_production_20260630T231345Z.db`
- Sandbox namespace still exists: true

## Verification

Code/config checks run:

```bash
PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m py_compile hermes_cli/plaid_connector.py hermes_cli/finance_cli.py
PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m hermes_cli.main finance plaid validate-production-config
```

Required targeted tests run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/hermes_cli/test_plaid_connector.py tests/hermes_cli/test_finance_registry.py -q -o 'addopts='
```

Result: `31 passed in 1.49s`.

Secret leak check:

- Compared `PLAID_CLIENT_ID` and `PLAID_SECRET` values from the private env file against the current git diff.
- Result: neither secret value appears in the diff.

## Next Step

Phase 4: Production Link Token.

Before Phase 4, keep the same safety boundaries:

- Create a production Link token only when explicitly approved.
- Do not exchange a public token until the operator completes Link.
- Do not run a production sync until a production access token has been created and the sync is explicitly approved.
- Continue to keep Sandbox and Production token namespaces separate.
