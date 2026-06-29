# Finance Registry Plaid Sandbox Setup

This integration is read-only and sandbox-only until sandbox sync, registry mapping, encryption, and tests are complete.

## Secrets

Put Plaid credentials in the Hermes profile environment, not in the repo:

`/home/yuu/.hermes/profiles/engineering_lab/.env`

Required variables:

```bash
PLAID_CLIENT_ID=...
PLAID_SECRET=...
PLAID_ENV=sandbox
PLAID_PRODUCTS=transactions,liabilities,investments
PLAID_COUNTRY_CODES=US
```

Do not commit `.env`, `*.env`, `*.key`, `*.secret`, or local finance secret files. The repo `.gitignore` protects these patterns.

## Token storage

Plaid access tokens are encrypted with a Fernet key stored under the active Hermes profile:

`$HERMES_HOME/finance/secrets/plaid_token.key`

The SQLite Finance Registry stores only the encrypted token ciphertext in `finance_institutions.encrypted_access_token`. Hermes never stores bank usernames, passwords, SSNs, full account numbers, routing numbers, or raw PII.

## CLI workflow

Create a Sandbox Link token:

```bash
hermes finance plaid link-token
```

Exchange a Sandbox public token returned by Plaid Link:

```bash
hermes finance plaid exchange-token PUBLIC-SANDBOX-TOKEN
```

Sync sandbox data into the existing registry:

```bash
hermes finance sync --sandbox
```

Check sync status:

```bash
hermes finance sync-status
```

Disconnect and remove local encrypted token reference:

```bash
hermes finance disconnect
```

## Rotation/removal

To rotate Plaid credentials:

1. Update `PLAID_CLIENT_ID` / `PLAID_SECRET` in the profile `.env`.
2. Run `hermes finance disconnect` for the old item.
3. Create a new link token and exchange a new public token.
4. Run `hermes finance sync --sandbox` and verify sync health.

To remove local token material manually, delete:

`$HERMES_HOME/finance/secrets/plaid_token.key`

and clear `finance_institutions.encrypted_access_token` from the active registry, or use `hermes finance disconnect` when the stored token is still valid.

## Dashboard boundary

The dashboard reads only the Finance Registry:

`/api/dashboard/v2 -> financial_metrics -> Finance Registry`

It must never call Plaid directly.
