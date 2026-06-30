# Plaid Sandbox Baseline Before Production

Generated: 2026-06-30T23:13:45Z

## Scope

This report preserves the verified Plaid Sandbox baseline before any Hermes Finance production switch.

No production switch was performed. No sandbox data was deleted. No production credentials were overwritten. No real bank accounts were connected.

## Current Environment

| Field | Value |
| --- | --- |
| Active Plaid environment | sandbox |
| Provider label | Plaid Sandbox |
| Registry source | Finance Registry |
| Registry model | Normalized Registry |
| Registry location | `/home/yuu/.hermes/profiles/engineering_lab/finance/registry.db` |
| Registry file mode | `0600` |
| PLAID_CLIENT_ID present | yes |
| PLAID_SECRET present | yes |
| HERMES_PLAID_ENV_FILE | unset |

`PLAID_ENV` controls the active Plaid environment. The connector maps `sandbox` to `https://sandbox.plaid.com` and `production` to `https://production.plaid.com`. The finance CLI now accepts `finance sync --sandbox` to force sandbox sync, and refuses `finance sync --production` unless `PLAID_ENV=production` is already set.

## Latest Sync Status

Latest `finance sync-status` returned:

| Field | Value |
| --- | --- |
| Status | success |
| Sync health | warning |
| Message | Plaid sandbox sync complete |
| Last successful sync | 2026-06-29T15:29:17+00:00 (`1782746957`) |
| Latest sync run id | 11 |
| Latest run duration | 3 seconds |
| Latest run accounts | 12 |
| Latest run transactions | 48 |
| Latest run investments | 13 |
| Latest run liabilities | 3 |
| Schedule | manual, disabled |

The health is `warning` even though the latest Plaid Sandbox sync completed successfully; preserve that as the baseline health state.

## Sync History Summary

| Environment | Status | Runs | Last completed |
| --- | --- | ---: | --- |
| sandbox | success | 11 | 2026-06-29T15:29:17+00:00 (`1782746957`) |

Five newest sync runs before this baseline:

| Run id | Environment | Status | Started | Completed | Accounts | Transactions | Liabilities | Investments | Message |
| ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 11 | sandbox | success | 2026-06-29T15:29:14+00:00 | 2026-06-29T15:29:17+00:00 | 12 | 48 | 3 | 13 | Plaid sandbox sync complete |
| 10 | sandbox | success | 2026-06-29T15:27:25+00:00 | 2026-06-29T15:27:28+00:00 | 12 | 48 | 3 | 13 | Plaid sandbox sync complete |
| 9 | sandbox | success | 2026-06-29T15:27:01+00:00 | 2026-06-29T15:27:05+00:00 | 12 | 48 | 3 | 13 | Plaid sandbox sync complete |
| 8 | sandbox | success | 2026-06-29T15:25:26+00:00 | 2026-06-29T15:25:31+00:00 | 12 | 48 | 3 | 13 | Plaid sandbox sync complete |
| 7 | sandbox | success | 2026-06-29T15:06:37+00:00 | 2026-06-29T15:06:41+00:00 | 12 | 48 | 3 | 13 | Plaid sandbox sync complete |

## Registry Table Counts

These are cumulative normalized registry table counts at baseline time:

| Table | Rows |
| --- | ---: |
| finance_institutions | 3 |
| finance_accounts | 60 |
| finance_balances | 132 |
| finance_transactions | 240 |
| finance_investments | 143 |
| finance_liabilities | 15 |
| finance_sync_runs | 11 |
| finance_sync_errors | 0 |

## Connected Sandbox Institutions

Sensitive encrypted token values are intentionally not included.

| Institution id | Name | Item id | Status | Has encrypted token | Last sync |
| --- | --- | --- | --- | --- | --- |
| `ins_109508` | First Platypus Bank | `5PMRL1qmvGUG3MkXZbjqUNkB8gnGoxfx67XDM` | active | no | 2026-06-29T12:27:01+00:00 (`1782736021`) |
| `ins_129911` | Platypus No Products | `18yE1w49QVIWkeRvlky4uoelWA4BJ1fQE3ymq` | active | yes | 2026-06-29T15:29:17+00:00 (`1782746957`) |
| `sandbox` | Plaid Sandbox | `5PMRL1qmvGUG3MkXZbjqUNkB8gnGoxfx67XDM` | active | yes | not recorded |

## Account/Balances Summary

`finance_accounts` contains 60 cumulative rows. The latest sync run reported 12 accounts. Active account totals by type/subtype at baseline:

| Account type | Subtype | Rows | Total current balance |
| --- | --- | ---: | ---: |
| credit | credit card | 10 | 27150.00 |
| depository | cash management | 5 | 60300.00 |
| depository | cd | 5 | 5000.00 |
| depository | checking | 5 | 550.00 |
| depository | hsa | 5 | 30045.00 |
| depository | money market | 5 | 216000.00 |
| depository | savings | 5 | 1050.00 |
| investment | 401k | 5 | 118159.90 |
| investment | ira | 5 | 1603.80 |
| loan | mortgage | 5 | 281510.30 |
| loan | student | 5 | 326310.00 |

## Credential and Token Separation

Verified implementation properties:

- `PLAID_ENV` is the active environment selector.
- Sandbox and production access tokens are stored as distinct institution ids using environment prefixes, for example `sandbox:<institution_id>` and `production:<institution_id>`.
- Production token lookup no longer falls back to unprefixed legacy sandbox rows.
- Sandbox lookup retains backward compatibility with legacy unprefixed sandbox rows.
- Production sync through the CLI is refused unless `PLAID_ENV=production` is already set.
- Sandbox sync can be forced with `finance sync --sandbox`.
- Token encryption key is stored under the finance secrets directory, which is gitignored.

## Backup

A timestamped pre-production sandbox registry backup was created with file permissions preserved:

`/home/yuu/.hermes/profiles/engineering_lab/finance/backups/registry_sandbox_before_production_20260630T231345Z.db`

Backup verification:

| Field | Value |
| --- | --- |
| Backup exists | yes |
| Source size | 286720 bytes |
| Backup size | 286720 bytes |
| Source mode | `0600` |
| Backup mode | `0600` |

The repo `.gitignore` includes `finance/backups/`. This backup is outside the repository under the Engineering Lab profile and must not be committed to Git.

## Known Sandbox Limitations

- Plaid Sandbox data is synthetic and should not be treated as real financial history.
- Sandbox balances, transactions, investments, and liabilities can be deterministic or fixture-like and may not model every production institution edge case.
- Current sync health is `warning` despite successful sync status; keep this as an observed baseline rather than changing health semantics during this phase.
- Cumulative table counts include repeated sandbox sync history; latest run counts are the authoritative per-sync baseline.
- Some institution rows are legacy/unprefixed sandbox-era rows; production token lookup is guarded so production does not consume them.

## Post-Backup Verification

After the backup and environment-separation hardening, a sandbox-only sync was run with:

```bash
PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m hermes_cli.main finance sync --sandbox
```

The final post-backup sync status is healthy:

| Field | Value |
| --- | --- |
| Latest sync run id | 13 |
| Status | success |
| Sync health | healthy |
| Message | Plaid sandbox sync success |
| Last successful sync | 2026-06-30T23:17:24+00:00 (`1782861444`) |
| Latest run accounts | 24 |
| Latest run transactions | 96 |
| Latest run investments | 26 |
| Latest run liabilities | 6 |

A failed run id 12 exists immediately before the successful verification run. It was produced while hardening sandbox legacy-token lookup; the code was corrected so sandbox lookups include legacy unprefixed sandbox tokens while production lookups do not. The final run id 13 is successful and is the current health baseline.

Current cumulative registry counts after post-backup verification:

| Table | Rows |
| --- | ---: |
| finance_institutions | 5 |
| finance_accounts | 60 |
| finance_balances | 156 |
| finance_transactions | 240 |
| finance_investments | 169 |
| finance_liabilities | 15 |
| finance_sync_runs | 13 |
| finance_sync_errors | 0 |

## Rollback Instructions

Use these steps only if a later production-prep change needs to restore the backed-up sandbox baseline.

1. Stop any running Hermes Finance sync process.
2. Keep the current registry as an additional safety copy:
   ```bash
   cp -p /home/yuu/.hermes/profiles/engineering_lab/finance/registry.db /home/yuu/.hermes/profiles/engineering_lab/finance/backups/registry_pre_rollback_$(date -u +%Y%m%dT%H%M%SZ).db
   ```
3. Restore the baseline backup:
   ```bash
   cp -p /home/yuu/.hermes/profiles/engineering_lab/finance/backups/registry_sandbox_before_production_20260630T231345Z.db /home/yuu/.hermes/profiles/engineering_lab/finance/registry.db
   ```
4. Ensure private permissions:
   ```bash
   chmod 600 /home/yuu/.hermes/profiles/engineering_lab/finance/registry.db
   ```
5. Confirm sandbox mode and status:
   ```bash
   PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m hermes_cli.main finance sync-status
   ```
6. Run a sandbox-only sync smoke test:
   ```bash
   PYTHONPATH=. HERMES_HOME=/home/yuu/.hermes/profiles/engineering_lab .venv/bin/python -m hermes_cli.main finance sync --sandbox
   ```

Do not set `PLAID_ENV=production` during rollback verification.
