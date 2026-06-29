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
Transport = Callable[[str, dict[str, Any]], dict[str, Any]]


def _load_plaid_env_file() -> None:
    """Load optional Plaid-only env file without overriding process env.

    Set HERMES_PLAID_ENV_FILE to .env.sandbox or .env.production when running
    locally. Existing process environment values win so deployments can inject
    secrets through their normal secret manager. The file is parsed as simple
    KEY=VALUE lines and is never exposed to the frontend.
    """
    env_file = os.environ.get("HERMES_PLAID_ENV_FILE", "").strip()
    if not env_file:
        return
    path = Path(env_file).expanduser()
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
        if key.startswith("PLAID_") and key not in os.environ:
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
    _load_plaid_env_file()
    env = os.environ.get("PLAID_ENV", "sandbox").strip().lower() or "sandbox"
    if env not in PLAID_BASE_URLS:
        raise PlaidSecurityError("PLAID_ENV must be sandbox or production.")
    client_id = os.environ.get("PLAID_CLIENT_ID", "").strip()
    secret = os.environ.get("PLAID_SECRET", "").strip()
    if not client_id or not secret:
        raise PlaidConfigurationError("PLAID_CLIENT_ID and PLAID_SECRET are required in the environment.")
    products = tuple(p.strip() for p in os.environ.get("PLAID_PRODUCTS", ",".join(DEFAULT_PRODUCTS)).split(",") if p.strip())
    country_codes = tuple(c.strip() for c in os.environ.get("PLAID_COUNTRY_CODES", "US").split(",") if c.strip())
    forbidden = {"transfer", "payment_initiation", "processor_payments"}
    if forbidden.intersection({p.lower() for p in products}):
        raise PlaidSecurityError("Money-movement Plaid products are forbidden for the Finance Registry integration.")
    return PlaidConfig(client_id=client_id, secret=secret, environment=env, products=products, country_codes=country_codes)


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


def store_access_token(*, access_token: str, item_id: str | None = None, institution_id: str = "sandbox", institution_name: str = "Plaid Sandbox", products: list[str] | None = None, environment: str = "sandbox", path: Path | None = None) -> None:
    encrypted = encrypt_access_token(access_token)
    environment = (environment or "sandbox").strip().lower() or "sandbox"
    registry_institution_id = _registry_institution_id(environment, institution_id)
    now = int(time.time())
    conn = _connect(path)
    try:
        ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO finance_institutions (provider, institution_id, institution_name, item_id, encrypted_access_token, status, products, created_at, updated_at)
            VALUES ('plaid', ?, ?, ?, ?, 'active', ?, ?, ?)
            ON CONFLICT(provider, institution_id) DO UPDATE SET
                institution_name=excluded.institution_name,
                item_id=COALESCE(excluded.item_id, finance_institutions.item_id),
                encrypted_access_token=excluded.encrypted_access_token,
                status='active',
                products=excluded.products,
                updated_at=excluded.updated_at
            """,
            (registry_institution_id, institution_name, item_id, encrypted, json.dumps(products or list(DEFAULT_PRODUCTS)), now, now),
        )
        conn.commit()
    finally:
        conn.close()


def load_access_token(*, institution_id: str | None = None, environment: str | None = None, path: Path | None = None) -> str:
    conn = _connect(path)
    try:
        ensure_schema(conn)
        if institution_id:
            lookup = _registry_institution_id(environment or os.environ.get("PLAID_ENV", "sandbox"), institution_id)
            row = conn.execute(
                "SELECT encrypted_access_token FROM finance_institutions WHERE provider='plaid' AND institution_id IN (?, ?) AND status='active' ORDER BY updated_at DESC LIMIT 1",
                (lookup, institution_id),
            ).fetchone()
        else:
            prefix = f"{(environment or os.environ.get('PLAID_ENV', 'sandbox')).strip().lower()}:%" if environment else "%"
            row = conn.execute(
                "SELECT encrypted_access_token FROM finance_institutions WHERE provider='plaid' AND status='active' AND encrypted_access_token IS NOT NULL AND institution_id LIKE ? ORDER BY updated_at DESC LIMIT 1",
                (prefix,),
            ).fetchone()
        if not row or not row["encrypted_access_token"]:
            raise PlaidConfigurationError("No encrypted Plaid access token is stored. Run hermes finance plaid exchange-token first.")
        return decrypt_access_token(row["encrypted_access_token"])
    finally:
        conn.close()



def list_stored_access_tokens(*, environment: str | None = None, path: Path | None = None) -> list[dict[str, Any]]:
    conn = _connect(path)
    try:
        ensure_schema(conn)
        if environment:
            pattern = f"{environment.strip().lower()}:%"
            rows = conn.execute(
                "SELECT institution_id, institution_name, item_id, encrypted_access_token, products FROM finance_institutions WHERE provider='plaid' AND status='active' AND encrypted_access_token IS NOT NULL AND institution_id LIKE ? ORDER BY updated_at DESC",
                (pattern,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT institution_id, institution_name, item_id, encrypted_access_token, products FROM finance_institutions WHERE provider='plaid' AND status='active' AND encrypted_access_token IS NOT NULL ORDER BY updated_at DESC"
            ).fetchall()
        return [
            {
                "institution_id": row["institution_id"],
                "display_institution_id": _display_institution_id(str(row["institution_id"])),
                "institution_name": row["institution_name"],
                "item_id": row["item_id"],
                "products": json.loads(row["products"] or "[]"),
                "access_token": decrypt_access_token(row["encrypted_access_token"]),
            }
            for row in rows
        ]
    finally:
        conn.close()


def remove_stored_access_tokens(*, institution_id: str | None = None, environment: str | None = None, path: Path | None = None) -> int:
    conn = _connect(path)
    try:
        ensure_schema(conn)
        params: list[Any] = [int(time.time())]
        where = "provider='plaid' AND encrypted_access_token IS NOT NULL"
        if institution_id:
            where += " AND institution_id=?"
            params.append(_registry_institution_id(environment or os.environ.get("PLAID_ENV", "sandbox"), institution_id))
        elif environment:
            where += " AND institution_id LIKE ?"
            params.append(f"{environment.strip().lower()}:%")
        cur = conn.execute(f"UPDATE finance_institutions SET encrypted_access_token=NULL, status='removed', updated_at=? WHERE {where}", params)
        conn.commit()
        return int(cur.rowcount or 0)
    finally:
        conn.close()


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
]
