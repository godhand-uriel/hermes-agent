"""Read-only Plaid Sandbox connector for the Hermes Finance Registry.

The connector intentionally uses Plaid Sandbox first and exposes only read-only
financial-data methods. It never stores bank usernames, passwords, SSNs, full
account numbers, routing numbers, or raw PII. Plaid access tokens are encrypted
before being stored in the existing Finance Registry database.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable
from urllib import request, error

from cryptography.fernet import Fernet

from hermes_cli.config import get_hermes_home
from hermes_cli.finance_registry import (
    _connect,
    ensure_schema,
    finance_registry_path,
    finish_finance_sync_run,
    latest_finance_sync_status,
    record_finance_sync_error,
    start_finance_sync_run,
    upsert_plaid_registry_data,
)

PLAID_BASE_URLS = {
    "sandbox": "https://sandbox.plaid.com",
    "production": "https://production.plaid.com",
}
DEFAULT_PRODUCTS = ("transactions", "liabilities", "investments")
DEFAULT_COUNTRY_CODES = ("US",)
READ_ONLY_PRODUCTS = frozenset({"transactions", "auth", "identity", "liabilities", "investments"})
FORBIDDEN_PRODUCTS = frozenset({"transfer", "payment_initiation", "processor_payments", "signal"})
Transport = Callable[[str, dict[str, Any]], dict[str, Any]]


def _load_hermes_secrets() -> None:
    """Load profile-scoped Hermes Secrets into the process environment.

    Hermes stores credential variables in the active profile `.env` or an
    external secret backend wired through `load_hermes_dotenv()`. The connector
    reads only environment variables after this load step; it never hardcodes,
    prints, or commits credential material.
    """
    existing = {key: os.environ[key] for key in os.environ if key.startswith("PLAID_")}
    try:
        from hermes_cli.env_loader import load_hermes_dotenv

        load_hermes_dotenv(hermes_home=get_hermes_home())
    except Exception:
        # Keep tests and embedded callers deterministic: explicit process env
        # remains authoritative if the full Hermes env loader is unavailable.
        pass
    finally:
        # `load_hermes_dotenv()` intentionally lets profile secrets override
        # stale shell exports for most Hermes entrypoints. The Plaid connector is
        # also used in tests and embedded callers, so values explicitly present
        # when this function was entered remain authoritative here.
        os.environ.update(existing)


def _load_plaid_env_file() -> None:
    """Load optional Plaid-only env file without overriding process env.

    Set HERMES_PLAID_ENV_FILE to a private env file when running locally.
    Existing process environment values win so deployments can inject secrets
    through Hermes Secrets or their normal secret manager. The file is parsed as
    simple KEY=VALUE lines and is never exposed to the frontend.
    """
    env_file = os.environ.get("HERMES_PLAID_ENV_FILE", "").strip()
    override_existing = bool(env_file)
    if not env_file and os.environ.get("PLAID_ENV", "").strip().lower() == "production":
        candidate = get_hermes_home() / ".env.production"
        if candidate.exists():
            env_file = str(candidate)
            override_existing = True
    if not env_file:
        return
    path = Path(env_file).expanduser()
    if path == get_hermes_home() / ".env.production":
        override_existing = True
    if not path.exists():
        raise PlaidConfigurationError(f"Plaid env file does not exist: {path}")
    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        raise PlaidSecurityError(f"Plaid env file must not be group/world-readable: {path}")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('\"').strip("'")
        if key.startswith("PLAID_") and (override_existing or key not in os.environ):
            os.environ[key] = value


class PlaidConfigurationError(RuntimeError):
    pass


class PlaidSecurityError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlaidConfig:
    client_id: str
    secret: str
    environment: str = "sandbox"
    products: tuple[str, ...] = DEFAULT_PRODUCTS
    country_codes: tuple[str, ...] = DEFAULT_COUNTRY_CODES

    @property
    def base_url(self) -> str:
        try:
            return PLAID_BASE_URLS[self.environment]
        except KeyError as exc:
            raise PlaidSecurityError("PLAID_ENV must be sandbox or production.") from exc


def plaid_config_from_env() -> PlaidConfig:
    _load_hermes_secrets()
    _load_plaid_env_file()
    env = os.environ.get("PLAID_ENV", "sandbox").strip().lower() or "sandbox"
    if env not in PLAID_BASE_URLS:
        raise PlaidSecurityError("PLAID_ENV must be sandbox or production.")

    client_id = os.environ.get("PLAID_CLIENT_ID", "").strip()
    secret = os.environ.get("PLAID_SECRET", "").strip()
    raw_products = os.environ.get("PLAID_PRODUCTS")
    raw_country_codes = os.environ.get("PLAID_COUNTRY_CODES")
    products = tuple(p.strip() for p in (raw_products if raw_products is not None else ",".join(DEFAULT_PRODUCTS)).split(",") if p.strip())
    country_codes = tuple(c.strip().upper() for c in (raw_country_codes if raw_country_codes is not None else "US").split(",") if c.strip())

    missing: list[str] = []
    if not client_id:
        missing.append("PLAID_CLIENT_ID")
    if not secret:
        missing.append("PLAID_SECRET")
    if env == "production":
        if raw_products is None or not products:
            missing.append("PLAID_PRODUCTS")
        if raw_country_codes is None or not country_codes:
            missing.append("PLAID_COUNTRY_CODES")
    if missing:
        joined = ", ".join(missing)
        raise PlaidConfigurationError(
            f"Plaid {env} configuration is missing required Hermes Secret(s): {joined}. "
            "Set them in the active Hermes profile secrets before running Plaid commands."
        )

    normalized_products = {p.lower() for p in products}
    if FORBIDDEN_PRODUCTS.intersection(normalized_products):
        raise PlaidSecurityError("Money-movement Plaid products are forbidden for the Finance Registry integration.")
    invalid_products = normalized_products.difference(READ_ONLY_PRODUCTS)
    if invalid_products:
        invalid = ", ".join(sorted(invalid_products))
        raise PlaidSecurityError(f"Unsupported Plaid product(s) for Finance Registry: {invalid}.")
    if not country_codes:
        raise PlaidConfigurationError("PLAID_COUNTRY_CODES must include at least one country code.")
    return PlaidConfig(client_id=client_id, secret=secret, environment=env, products=products, country_codes=country_codes)


def _is_placeholder_secret(value: str) -> bool:
    raw = (value or "").strip()
    lowered = raw.lower()
    return not raw or "<" in raw or ">" in raw or "placeholder" in lowered or "your_" in lowered or lowered.startswith("changeme")


def _safe_key_status(key: str) -> dict[str, Any]:
    value = os.environ.get(key, "")
    return {"present": bool(value), "length": len(value), "placeholder": _is_placeholder_secret(value)}


def validate_production_config(*, env_file: Path | None = None, path: Path | None = None) -> dict[str, Any]:
    """Validate production Plaid configuration without contacting Plaid.

    The returned payload is safe to print: it reports key presence, lengths,
    validation booleans, and namespace state, but never credential values or
    access-token values.
    """
    selected_env_file = (env_file or (get_hermes_home() / ".env.production")).expanduser()
    original_env = dict(os.environ)
    result: dict[str, Any] = {
        "credential_source_path": str(selected_env_file),
        "credential_source_exists": selected_env_file.exists(),
        "credential_source_mode": None,
        "credential_source_private": False,
        "environment": "production",
        "keys": {},
        "credentials_loaded": False,
        "products": [],
        "products_valid": False,
        "country_codes": [],
        "country_codes_valid": False,
        "production_token_namespace": {},
        "sandbox_token_namespace": {},
        "sandbox_tokens_remain_separate": False,
        "production_token_namespace_empty": False,
        "production_access_token_exists": False,
        "registry_backup_exists": False,
        "sandbox_baseline_exists": False,
        "errors": [],
    }
    if selected_env_file.exists():
        mode = selected_env_file.stat().st_mode & 0o777
        result["credential_source_mode"] = f"{mode:04o}"
        result["credential_source_private"] = not bool(mode & 0o077)
    try:
        os.environ["PLAID_ENV"] = "production"
        os.environ["HERMES_PLAID_ENV_FILE"] = str(selected_env_file)
        for key in ("PLAID_CLIENT_ID", "PLAID_SECRET", "PLAID_PRODUCTS", "PLAID_COUNTRY_CODES"):
            os.environ.pop(key, None)
        try:
            cfg = plaid_config_from_env()
            result["environment"] = cfg.environment
            result["credentials_loaded"] = bool(cfg.client_id and cfg.secret and cfg.environment == "production")
            result["products"] = list(cfg.products)
            result["products_valid"] = all(p.lower() in READ_ONLY_PRODUCTS for p in cfg.products)
            result["country_codes"] = list(cfg.country_codes)
            result["country_codes_valid"] = bool(cfg.country_codes)
        except (PlaidConfigurationError, PlaidSecurityError) as exc:
            result["errors"].append(str(exc))
        result["keys"] = {key: _safe_key_status(key) for key in ("PLAID_ENV", "PLAID_CLIENT_ID", "PLAID_SECRET", "PLAID_PRODUCTS", "PLAID_COUNTRY_CODES")}

        prod_store = token_store_path("production", registry_path=path)
        sandbox_store = token_store_path("sandbox", registry_path=path)
        prod_records = _read_token_store("production", registry_path=path)
        sandbox_records = _read_token_store("sandbox", registry_path=path)
        prod_legacy_count = len(_legacy_registry_token_rows("production", path=path))
        result["production_token_namespace"] = {"path": str(prod_store.parent), "token_store_path": str(prod_store), "exists": prod_store.parent.exists(), "token_records": len(prod_records), "legacy_registry_token_rows": prod_legacy_count}
        result["sandbox_token_namespace"] = {"path": str(sandbox_store.parent), "token_store_path": str(sandbox_store), "exists": sandbox_store.parent.exists(), "token_records": len(sandbox_records), "legacy_compatible": True}
        result["sandbox_tokens_remain_separate"] = prod_store != sandbox_store and prod_store.parent != sandbox_store.parent
        result["production_token_namespace_empty"] = len(prod_records) == 0 and prod_legacy_count == 0
        result["production_access_token_exists"] = not bool(result["production_token_namespace_empty"])

        registry = path or finance_registry_path()
        backup_dir = registry.parent / "backups"
        result["registry_backup_exists"] = backup_dir.exists() and any(backup_dir.glob("registry_sandbox_before_production_*.db"))
        result["sandbox_baseline_exists"] = (Path.cwd() / "docs" / "plaid_sandbox_baseline_before_production.md").exists()
    finally:
        os.environ.clear()
        os.environ.update(original_env)
    return result


def _finance_secret_dir() -> Path:
    path = get_hermes_home() / "finance" / "secrets"
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def _fernet_key_path() -> Path:
    override = os.environ.get("HERMES_FINANCE_TOKEN_KEY_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return _finance_secret_dir() / "plaid_token.key"


def _load_or_create_fernet() -> Fernet:
    path = _fernet_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        key = path.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        path.write_bytes(key + b"\n")
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return Fernet(key)


def encrypt_access_token(token: str) -> str:
    if not token or not token.strip():
        raise PlaidSecurityError("Cannot encrypt an empty Plaid access token.")
    encrypted = _load_or_create_fernet().encrypt(token.encode("utf-8"))
    return encrypted.decode("ascii")


def decrypt_access_token(encrypted_token: str) -> str:
    return _load_or_create_fernet().decrypt(encrypted_token.encode("ascii")).decode("utf-8")


def _registry_institution_id(environment: str, institution_id: str) -> str:
    env = (environment or "sandbox").strip().lower() or "sandbox"
    raw = (institution_id or env).strip()
    return raw if raw.startswith(f"{env}:") else f"{env}:{raw}"


def _display_institution_id(registry_id: str) -> str:
    if ":" in registry_id:
        return registry_id.split(":", 1)[1]
    return registry_id


def _validate_plaid_environment(environment: str) -> str:
    env = (environment or "sandbox").strip().lower() or "sandbox"
    if env not in PLAID_BASE_URLS:
        raise PlaidSecurityError("PLAID_ENV must be sandbox or production.")
    return env


def token_namespace_dir(environment: str, *, registry_path: Path | None = None) -> Path:
    """Return the environment-specific token namespace directory.

    Default layout under the active Hermes profile:

        $HERMES_HOME/finance/sandbox/access_tokens.json
        $HERMES_HOME/finance/production/access_tokens.json

    Tests may pass a registry path to keep token files beside a temporary
    registry database without changing the registry schema.
    """
    env = _validate_plaid_environment(environment)
    finance_root = registry_path.parent if registry_path is not None else get_hermes_home() / "finance"
    path = finance_root / env
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def token_store_path(environment: str, *, registry_path: Path | None = None) -> Path:
    return token_namespace_dir(environment, registry_path=registry_path) / "access_tokens.json"


def _read_token_store(environment: str, *, registry_path: Path | None = None) -> list[dict[str, Any]]:
    path = token_store_path(environment, registry_path=registry_path)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PlaidSecurityError(f"Plaid token store is not valid JSON: {path}") from exc
    if isinstance(raw, dict):
        records = raw.get("tokens", [])
    elif isinstance(raw, list):
        records = raw
    else:
        records = []
    if not isinstance(records, list):
        raise PlaidSecurityError(f"Plaid token store has invalid format: {path}")
    return [record for record in records if isinstance(record, dict)]


def _write_token_store(environment: str, records: list[dict[str, Any]], *, registry_path: Path | None = None) -> None:
    env = _validate_plaid_environment(environment)
    path = token_store_path(env, registry_path=registry_path)
    payload = {"environment": env, "updated_at": int(time.time()), "tokens": records}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _token_record_for_row(row: sqlite3.Row, environment: str) -> dict[str, Any]:
    registry_id = str(row["institution_id"] or "")
    return {
        "environment": environment,
        "institution_id": registry_id,
        "display_institution_id": _display_institution_id(registry_id),
        "institution_name": row["institution_name"],
        "item_id": row["item_id"],
        "products": json.loads(row["products"] or "[]"),
        "access_token": decrypt_access_token(row["encrypted_access_token"]),
        "storage": "legacy_registry",
    }


def store_access_token(*, access_token: str, item_id: str | None = None, institution_id: str = "sandbox", institution_name: str = "Plaid Sandbox", products: list[str] | None = None, environment: str = "sandbox", path: Path | None = None) -> None:
    """Store an encrypted Plaid access token in the environment namespace.

    Access tokens live outside the Finance Registry so Sandbox and Production
    cannot overwrite each other and registry schemas remain unchanged.
    """
    env = _validate_plaid_environment(environment)
    encrypted = encrypt_access_token(access_token)
    display_id = _display_institution_id(institution_id or env)
    now = int(time.time())
    records = _read_token_store(env, registry_path=path)
    next_records: list[dict[str, Any]] = []
    replaced = False
    for record in records:
        if str(record.get("institution_id") or "") == display_id:
            created_at = int(record.get("created_at") or now)
            next_records.append(
                {
                    "institution_id": display_id,
                    "institution_name": institution_name,
                    "item_id": item_id or record.get("item_id"),
                    "encrypted_access_token": encrypted,
                    "products": products or list(DEFAULT_PRODUCTS),
                    "created_at": created_at,
                    "updated_at": now,
                }
            )
            replaced = True
        else:
            next_records.append(record)
    if not replaced:
        next_records.append(
            {
                "institution_id": display_id,
                "institution_name": institution_name,
                "item_id": item_id,
                "encrypted_access_token": encrypted,
                "products": products or list(DEFAULT_PRODUCTS),
                "created_at": now,
                "updated_at": now,
            }
        )
    next_records.sort(key=lambda r: int(r.get("updated_at") or 0), reverse=True)
    _write_token_store(env, next_records, registry_path=path)


def _legacy_registry_token_rows(environment: str, *, institution_id: str | None = None, path: Path | None = None) -> list[sqlite3.Row]:
    env = _validate_plaid_environment(environment)
    conn = _connect(path)
    try:
        ensure_schema(conn)
        if institution_id:
            lookup = _registry_institution_id(env, institution_id)
            candidates = [lookup]
            if env == "sandbox":
                candidates.append(institution_id)
            placeholders = ", ".join("?" for _ in candidates)
            return conn.execute(
                f"SELECT institution_id, institution_name, item_id, encrypted_access_token, products FROM finance_institutions WHERE provider='plaid' AND institution_id IN ({placeholders}) AND status='active' AND encrypted_access_token IS NOT NULL ORDER BY updated_at DESC",
                candidates,
            ).fetchall()
        pattern = f"{env}:%"
        if env == "sandbox":
            return conn.execute(
                "SELECT institution_id, institution_name, item_id, encrypted_access_token, products FROM finance_institutions WHERE provider='plaid' AND status='active' AND encrypted_access_token IS NOT NULL AND (institution_id LIKE ? OR institution_id NOT LIKE '%:%') ORDER BY updated_at DESC",
                (pattern,),
            ).fetchall()
        return conn.execute(
            "SELECT institution_id, institution_name, item_id, encrypted_access_token, products FROM finance_institutions WHERE provider='plaid' AND status='active' AND encrypted_access_token IS NOT NULL AND institution_id LIKE ? ORDER BY updated_at DESC",
            (pattern,),
        ).fetchall()
    finally:
        conn.close()


def load_access_token(*, institution_id: str | None = None, environment: str | None = None, path: Path | None = None) -> str:
    env = _validate_plaid_environment(environment or os.environ.get("PLAID_ENV", "sandbox"))
    records = _read_token_store(env, registry_path=path)
    if institution_id:
        display_id = _display_institution_id(institution_id)
        records = [record for record in records if str(record.get("institution_id") or "") == display_id]
    records.sort(key=lambda r: int(r.get("updated_at") or 0), reverse=True)
    for record in records:
        encrypted = str(record.get("encrypted_access_token") or "")
        if encrypted:
            return decrypt_access_token(encrypted)

    legacy_rows = _legacy_registry_token_rows(env, institution_id=institution_id, path=path)
    if legacy_rows:
        return decrypt_access_token(legacy_rows[0]["encrypted_access_token"])
    raise PlaidConfigurationError(f"No encrypted Plaid access token is stored for {env}. Run hermes finance plaid exchange-token first.")


def list_stored_access_tokens(*, environment: str | None = None, path: Path | None = None) -> list[dict[str, Any]]:
    environments = [_validate_plaid_environment(environment)] if environment else sorted(PLAID_BASE_URLS)
    result: list[dict[str, Any]] = []
    for env in environments:
        for record in _read_token_store(env, registry_path=path):
            encrypted = str(record.get("encrypted_access_token") or "")
            if not encrypted:
                continue
            institution_id = str(record.get("institution_id") or env)
            result.append(
                {
                    "environment": env,
                    "institution_id": institution_id,
                    "display_institution_id": _display_institution_id(institution_id),
                    "institution_name": record.get("institution_name"),
                    "item_id": record.get("item_id"),
                    "products": record.get("products") or [],
                    "access_token": decrypt_access_token(encrypted),
                    "storage": "file_namespace",
                    "token_store": str(token_store_path(env, registry_path=path)),
                }
            )
        # Legacy registry fallback keeps pre-namespace sandbox rows readable. It
        # never lets production fall back to unprefixed sandbox rows.
        result.extend(_token_record_for_row(row, env) for row in _legacy_registry_token_rows(env, path=path))
    return result


def remove_stored_access_tokens(*, institution_id: str | None = None, environment: str | None = None, path: Path | None = None) -> int:
    env = _validate_plaid_environment(environment or os.environ.get("PLAID_ENV", "sandbox"))
    display_id = _display_institution_id(institution_id) if institution_id else None
    records = _read_token_store(env, registry_path=path)
    kept = [record for record in records if display_id and str(record.get("institution_id") or "") != display_id]
    removed = len(records) - len(kept)
    if removed or records:
        _write_token_store(env, kept, registry_path=path)

    # Also clean legacy registry token references for backward compatibility.
    conn = _connect(path)
    try:
        ensure_schema(conn)
        params: list[Any] = [int(time.time())]
        where = "provider='plaid' AND encrypted_access_token IS NOT NULL"
        if institution_id:
            where += " AND institution_id=?"
            params.append(_registry_institution_id(env, institution_id))
        else:
            where += " AND institution_id LIKE ?"
            params.append(f"{env}:%")
        cur = conn.execute(f"UPDATE finance_institutions SET encrypted_access_token=NULL, status='removed', updated_at=? WHERE {where}", params)
        conn.commit()
        removed += int(cur.rowcount or 0)
    finally:
        conn.close()
    return removed


class PlaidConnector:
    def __init__(self, config: PlaidConfig | None = None, *, transport: Transport | None = None):
        self.config = config or plaid_config_from_env()
        self.transport = transport

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        payload = {"client_id": self.config.client_id, "secret": self.config.secret, **payload}
        if self.transport is not None:
            return self.transport(endpoint, payload)
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.config.base_url + endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw)
            except json.JSONDecodeError:
                detail = {"error_message": raw}
            msg = str(detail.get("error_message") or detail.get("display_message") or raw)
            raise RuntimeError(f"Plaid request failed for {endpoint}: {msg}") from exc

    def create_link_token(self, *, user_id: str = "hermes-finance") -> dict[str, Any]:
        return self._post(
            "/link/token/create",
            {
                "client_name": "Hermes Finance Registry",
                "country_codes": list(self.config.country_codes),
                "language": "en",
                "user": {"client_user_id": user_id},
                "products": list(self.config.products),
            },
        )

    def exchange_public_token(self, public_token: str, *, store: bool = True, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not public_token or not public_token.strip():
            raise PlaidConfigurationError("Plaid public token is required.")
        result = self._post("/item/public_token/exchange", {"public_token": public_token})
        access_token = result.get("access_token")
        metadata = metadata or {}
        raw_institution = metadata.get("institution")
        institution: dict[str, Any] = raw_institution if isinstance(raw_institution, dict) else {}
        institution_id = str(institution.get("institution_id") or metadata.get("institution_id") or "sandbox")
        institution_name = str(institution.get("name") or metadata.get("institution_name") or "Plaid Sandbox")
        if store and access_token:
            store_access_token(
                access_token=access_token,
                item_id=result.get("item_id"),
                institution_id=institution_id,
                institution_name=institution_name,
                products=list(self.config.products),
                environment=self.config.environment,
            )
        safe = dict(result)
        if "access_token" in safe:
            safe["access_token"] = "[ENCRYPTED_AND_STORED]" if store else "[REDACTED]"
        safe["environment"] = self.config.environment
        safe["institution"] = {"institution_id": institution_id, "name": institution_name}
        return safe

    def fetch_accounts(self, access_token: str) -> dict[str, Any]:
        return self._post("/accounts/get", {"access_token": access_token})

    def fetch_balances(self, access_token: str) -> dict[str, Any]:
        return self._post("/accounts/balance/get", {"access_token": access_token})

    def fetch_transactions(self, access_token: str, *, start_date: str, end_date: str) -> dict[str, Any]:
        return self._post("/transactions/get", {"access_token": access_token, "start_date": start_date, "end_date": end_date})

    def fetch_liabilities(self, access_token: str) -> dict[str, Any]:
        return self._post("/liabilities/get", {"access_token": access_token})

    def fetch_investments(self, access_token: str) -> dict[str, Any]:
        return self._post("/investments/holdings/get", {"access_token": access_token})

    def disconnect(self, access_token: str | None = None, *, institution_id: str | None = None) -> dict[str, Any]:
        token = access_token or load_access_token(institution_id=institution_id, environment=self.config.environment)
        result = self._post("/item/remove", {"access_token": token})
        removed = remove_stored_access_tokens(institution_id=institution_id, environment=self.config.environment)
        return {"plaid": result, "stored_tokens_removed": removed}

    def _fetch_registry_payload(self, token: str, *, institution_hint: dict[str, Any] | None = None) -> dict[str, Any]:
        import datetime as dt

        accounts_payload = self.fetch_accounts(token)
        balances_payload = self.fetch_balances(token)
        end_date = dt.date.today()
        start_date = end_date - dt.timedelta(days=90)
        tx_payload = self.fetch_transactions(token, start_date=start_date.isoformat(), end_date=end_date.isoformat())
        liabilities_payload = self.fetch_liabilities(token) if "liabilities" in self.config.products else {}
        investments_payload = self.fetch_investments(token) if "investments" in self.config.products else {}
        accounts = balances_payload.get("accounts") or accounts_payload.get("accounts") or []
        item = accounts_payload.get("item") or balances_payload.get("item") or {}
        hint = institution_hint or {}
        institution_id = item.get("institution_id") or hint.get("display_institution_id") or self.config.environment
        registry_institution_id = _registry_institution_id(self.config.environment, str(institution_id))
        return {
            "products": list(self.config.products),
            "institution": {
                "institution_id": registry_institution_id,
                "name": item.get("institution_name") or hint.get("institution_name") or f"Plaid {self.config.environment.capitalize()}",
                "item_id": item.get("item_id") or hint.get("item_id"),
            },
            "accounts": accounts,
            "transactions": tx_payload.get("transactions") or [],
            "liabilities": liabilities_payload.get("liabilities") or {},
            "holdings": investments_payload.get("holdings") or [],
            "securities": investments_payload.get("securities") or [],
        }

    def sync_to_finance_registry(self, *, access_token: str | None = None, path: Path | None = None) -> dict[str, Any]:
        sync_run_id = start_finance_sync_run(provider="plaid", environment=self.config.environment, path=path)
        total_counts = {"institutions": 0, "accounts": 0, "transactions": 0, "balances": 0, "liabilities": 0, "investments": 0}
        failures: list[str] = []
        tokens = [{"access_token": access_token, "institution_id": None}] if access_token else list_stored_access_tokens(environment=self.config.environment, path=path)
        if not tokens:
            finish_finance_sync_run(sync_run_id, status="failed", message="No encrypted Plaid access token is stored.", path=path)
            raise PlaidConfigurationError("No encrypted Plaid access token is stored. Run hermes finance plaid exchange-token first.")
        for token_info in tokens:
            token = str(token_info.get("access_token") or "")
            try:
                registry_payload = self._fetch_registry_payload(token, institution_hint=token_info)
                counts = upsert_plaid_registry_data(registry_payload, sync_run_id=sync_run_id, path=path)
                for key, value in counts.items():
                    total_counts[key] = total_counts.get(key, 0) + int(value or 0)
            except Exception as exc:
                failures.append(exc.__class__.__name__)
                record_finance_sync_error(sync_run_id, exc.__class__.__name__, str(exc), path=path)
        if failures and total_counts["accounts"] == 0:
            message = "Plaid sync failed; no registry changes were applied."
            finish_finance_sync_run(sync_run_id, status="failed", message=message, counts=total_counts, path=path)
            raise RuntimeError(message)
        status = "partial" if failures else "success"
        message = f"Plaid {self.config.environment} sync {status}"
        finish_finance_sync_run(sync_run_id, status=status, message=message, counts=total_counts, path=path)
        return {"status": status, "sync_run_id": sync_run_id, "counts": total_counts, "failures": failures, "registry": str(path or finance_registry_path())}


def create_link_token(**kwargs: Any) -> dict[str, Any]:
    return PlaidConnector().create_link_token(**kwargs)


def exchange_public_token(public_token: str, **kwargs: Any) -> dict[str, Any]:
    return PlaidConnector().exchange_public_token(public_token, **kwargs)


def fetch_accounts(access_token: str) -> dict[str, Any]:
    return PlaidConnector().fetch_accounts(access_token)


def fetch_balances(access_token: str) -> dict[str, Any]:
    return PlaidConnector().fetch_balances(access_token)


def fetch_transactions(access_token: str, *, start_date: str, end_date: str) -> dict[str, Any]:
    return PlaidConnector().fetch_transactions(access_token, start_date=start_date, end_date=end_date)


def fetch_liabilities(access_token: str) -> dict[str, Any]:
    return PlaidConnector().fetch_liabilities(access_token)


def fetch_investments(access_token: str) -> dict[str, Any]:
    return PlaidConnector().fetch_investments(access_token)


def sync_to_finance_registry(**kwargs: Any) -> dict[str, Any]:
    return PlaidConnector().sync_to_finance_registry(**kwargs)


__all__ = [
    "PlaidConfig",
    "PlaidConnector",
    "PlaidConfigurationError",
    "PlaidSecurityError",
    "create_link_token",
    "decrypt_access_token",
    "encrypt_access_token",
    "exchange_public_token",
    "fetch_accounts",
    "fetch_balances",
    "fetch_investments",
    "fetch_liabilities",
    "fetch_transactions",
    "latest_finance_sync_status",
    "list_stored_access_tokens",
    "load_access_token",
    "plaid_config_from_env",
    "remove_stored_access_tokens",
    "store_access_token",
    "sync_to_finance_registry",
    "token_namespace_dir",
    "token_store_path",
    "validate_production_config",
]
