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
}
DEFAULT_PRODUCTS = ("transactions", "liabilities", "investments")
DEFAULT_COUNTRY_CODES = ("US",)
Transport = Callable[[str, dict[str, Any]], dict[str, Any]]


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
        if self.environment != "sandbox":
            raise PlaidSecurityError("Only PLAID_ENV=sandbox is allowed until sandbox sync, encryption, mapping, and tests are complete.")
        return PLAID_BASE_URLS[self.environment]


def plaid_config_from_env() -> PlaidConfig:
    env = os.environ.get("PLAID_ENV", "sandbox").strip().lower() or "sandbox"
    if env != "sandbox":
        raise PlaidSecurityError("Production Plaid access is disabled for this implementation. Set PLAID_ENV=sandbox.")
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


def store_access_token(*, access_token: str, item_id: str | None = None, institution_id: str = "sandbox", institution_name: str = "Plaid Sandbox", products: list[str] | None = None, path: Path | None = None) -> None:
    encrypted = encrypt_access_token(access_token)
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
            (institution_id, institution_name, item_id, encrypted, json.dumps(products or list(DEFAULT_PRODUCTS)), now, now),
        )
        conn.commit()
    finally:
        conn.close()


def load_access_token(*, institution_id: str | None = None, path: Path | None = None) -> str:
    conn = _connect(path)
    try:
        ensure_schema(conn)
        if institution_id:
            row = conn.execute(
                "SELECT encrypted_access_token FROM finance_institutions WHERE provider='plaid' AND institution_id=? AND status='active'",
                (institution_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT encrypted_access_token FROM finance_institutions WHERE provider='plaid' AND status='active' AND encrypted_access_token IS NOT NULL ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        if not row or not row["encrypted_access_token"]:
            raise PlaidConfigurationError("No encrypted Plaid access token is stored. Run hermes finance plaid exchange-token first.")
        return decrypt_access_token(row["encrypted_access_token"])
    finally:
        conn.close()


def remove_stored_access_tokens(*, path: Path | None = None) -> int:
    conn = _connect(path)
    try:
        ensure_schema(conn)
        cur = conn.execute("UPDATE finance_institutions SET encrypted_access_token=NULL, status='removed', updated_at=? WHERE provider='plaid' AND encrypted_access_token IS NOT NULL", (int(time.time()),))
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

    def create_link_token(self, *, user_id: str = "hermes-finance-sandbox") -> dict[str, Any]:
        return self._post(
            "/link/token/create",
            {
                "client_name": "Hermes Finance Registry Sandbox",
                "country_codes": list(self.config.country_codes),
                "language": "en",
                "user": {"client_user_id": user_id},
                "products": list(self.config.products),
            },
        )

    def exchange_public_token(self, public_token: str, *, store: bool = True) -> dict[str, Any]:
        result = self._post("/item/public_token/exchange", {"public_token": public_token})
        access_token = result.get("access_token")
        if store and access_token:
            store_access_token(
                access_token=access_token,
                item_id=result.get("item_id"),
                institution_id="sandbox",
                institution_name="Plaid Sandbox",
                products=list(self.config.products),
            )
        safe = dict(result)
        if "access_token" in safe:
            safe["access_token"] = "[ENCRYPTED_AND_STORED]" if store else "[REDACTED]"
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

    def disconnect(self, access_token: str | None = None) -> dict[str, Any]:
        token = access_token or load_access_token()
        result = self._post("/item/remove", {"access_token": token})
        removed = remove_stored_access_tokens()
        return {"plaid": result, "stored_tokens_removed": removed}

    def sync_to_finance_registry(self, *, access_token: str | None = None, path: Path | None = None) -> dict[str, Any]:
        import datetime as dt

        token = access_token or load_access_token(path=path)
        sync_run_id = start_finance_sync_run(provider="plaid", environment=self.config.environment, path=path)
        try:
            accounts_payload = self.fetch_accounts(token)
            balances_payload = self.fetch_balances(token)
            end_date = dt.date.today()
            start_date = end_date - dt.timedelta(days=90)
            tx_payload = self.fetch_transactions(token, start_date=start_date.isoformat(), end_date=end_date.isoformat())
            liabilities_payload = self.fetch_liabilities(token) if "liabilities" in self.config.products else {}
            investments_payload = self.fetch_investments(token) if "investments" in self.config.products else {}
            accounts = balances_payload.get("accounts") or accounts_payload.get("accounts") or []
            item = accounts_payload.get("item") or balances_payload.get("item") or {}
            institution_id = item.get("institution_id") or "sandbox"
            registry_payload = {
                "products": list(self.config.products),
                "institution": {
                    "institution_id": institution_id,
                    "name": item.get("institution_name") or "Plaid Sandbox",
                    "item_id": item.get("item_id"),
                },
                "accounts": accounts,
                "transactions": tx_payload.get("transactions") or [],
                "liabilities": liabilities_payload.get("liabilities") or {},
                "holdings": investments_payload.get("holdings") or [],
                "securities": investments_payload.get("securities") or [],
            }
            counts = upsert_plaid_registry_data(registry_payload, sync_run_id=sync_run_id, path=path)
            finish_finance_sync_run(sync_run_id, status="success", message="Plaid sandbox sync complete", counts=counts, path=path)
            return {"status": "success", "sync_run_id": sync_run_id, "counts": counts, "registry": str(path or finance_registry_path())}
        except Exception as exc:
            record_finance_sync_error(sync_run_id, exc.__class__.__name__, str(exc), path=path)
            finish_finance_sync_run(sync_run_id, status="failed", message=str(exc)[:1000], path=path)
            raise


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
    "load_access_token",
    "plaid_config_from_env",
    "remove_stored_access_tokens",
    "store_access_token",
    "sync_to_finance_registry",
]
