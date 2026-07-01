from __future__ import annotations

import io
import os
import sqlite3
from pathlib import Path

import pytest

from hermes_cli.finance_registry import (
    dashboard_financial_metrics,
    ensure_schema,
    finance_command_center_contract,
    insert_finance_snapshot,
    upsert_plaid_registry_data,
)
from hermes_cli.plaid_connector import (
    PlaidConfig,
    PlaidConfigurationError,
    PlaidConnector,
    decrypt_access_token,
    encrypt_access_token,
    list_stored_access_tokens,
    load_access_token,
    plaid_config_from_env,
    store_access_token,
    token_store_path,
)


def _conn(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def test_normalized_schema_migration_preserves_legacy_snapshots(tmp_path):
    path = tmp_path / "finance.db"
    insert_finance_snapshot({"annual_income": 12000, "monthly_expenses": 100, "checking_balance": 25}, path=path)

    conn = _conn(path)
    try:
        ensure_schema(conn)
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "finance_snapshots" in tables
        for table in {
            "finance_institutions",
            "finance_accounts",
            "finance_transactions",
            "finance_balances",
            "finance_liabilities",
            "finance_investments",
            "finance_sync_runs",
            "finance_sync_errors",
            "finance_registry_migrations",
        }:
            assert table in tables
        assert conn.execute("SELECT COUNT(*) AS count FROM finance_snapshots").fetchone()["count"] == 1
    finally:
        conn.close()

    contract = finance_command_center_contract(path=path)
    assert contract["initialized"] is True
    assert contract["source"]["model"] == "snapshot"


def test_plaid_registry_mapping_and_duplicate_transaction_prevention(tmp_path):
    path = tmp_path / "finance.db"
    payload = {
        "institution": {"institution_id": "ins_sandbox", "name": "Sandbox Bank", "item_id": "item_1"},
        "accounts": [
            {"account_id": "acc_checking", "name": "Checking", "type": "depository", "subtype": "checking", "mask": "0000", "balances": {"current": 1000, "available": 900, "iso_currency_code": "USD"}},
            {"account_id": "acc_credit", "name": "Card", "type": "credit", "subtype": "credit card", "mask": "1111", "balances": {"current": 250, "available": 750, "iso_currency_code": "USD"}},
            {"account_id": "acc_brokerage", "name": "Brokerage", "type": "investment", "subtype": "brokerage", "mask": "2222", "balances": {"current": 500, "available": None, "iso_currency_code": "USD"}},
        ],
        "transactions": [
            {"transaction_id": "txn_income", "account_id": "acc_checking", "date": "2999-01-01", "name": "Payroll", "merchant_name": "Employer", "amount": -2000, "category": ["Payroll"], "pending": False},
            {"transaction_id": "txn_spend", "account_id": "acc_checking", "date": "2999-01-02", "name": "Grocery", "merchant_name": "Market", "amount": 125, "category": ["Food"], "pending": False},
        ],
        "liabilities": {"credit": [{"account_id": "acc_credit", "last_statement_balance": 250, "minimum_payment_amount": 25, "next_payment_due_date": "2999-02-01"}]},
        "holdings": [{"account_id": "acc_brokerage", "security_id": "sec_vti", "quantity": 2, "institution_price": 300, "institution_value": 600, "iso_currency_code": "USD"}],
        "securities": [{"security_id": "sec_vti", "ticker_symbol": "VTI", "name": "Total Market ETF"}],
    }

    counts1 = upsert_plaid_registry_data(payload, path=path)
    counts2 = upsert_plaid_registry_data(payload, path=path)
    assert counts1["transactions"] == 2
    assert counts2["transactions"] == 2

    conn = _conn(path)
    try:
        assert conn.execute("SELECT COUNT(*) AS count FROM finance_transactions").fetchone()["count"] == 2
        assert conn.execute("SELECT account_mask FROM finance_accounts WHERE provider_account_id='acc_checking'").fetchone()["account_mask"] == "0000"
    finally:
        conn.close()

    # Verify tmp registry via command-center contract.
    contract = finance_command_center_contract(path=path)
    labels = {widget["label"] for widget in contract["widgets"]}
    assert {"Net Worth", "Cash Position", "Total Debt", "Monthly Income", "Monthly Spending", "Brokerage", "Last Finance Sync", "Sync Health"}.issubset(labels)
    assert contract["metrics"]["cash_position"] == 1000
    assert contract["metrics"]["total_debt"] == 250
    assert contract["metrics"]["brokerage_value"] == 600


def test_encrypted_token_storage_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    token = "access-sandbox-secret-token"
    encrypted = encrypt_access_token(token)
    assert encrypted != token
    assert token not in encrypted
    assert decrypt_access_token(encrypted) == token

    path = tmp_path / "registry.db"
    store_access_token(access_token=token, item_id="item_1", institution_id="ins_sandbox", path=path)
    assert load_access_token(institution_id="ins_sandbox", path=path) == token
    token_path = token_store_path("sandbox", registry_path=path)
    assert token_path == tmp_path / "sandbox" / "access_tokens.json"
    stored_payload = token_path.read_text(encoding="utf-8")
    assert token not in stored_payload
    assert "ins_sandbox" in stored_payload


def test_missing_token_handling(tmp_path):
    with pytest.raises(PlaidConfigurationError):
        load_access_token(path=tmp_path / "registry.db")


def test_production_configuration_uses_production_url_without_code_changes(monkeypatch, tmp_path):
    monkeypatch.setenv("PLAID_ENV", "production")
    monkeypatch.setenv("PLAID_CLIENT_ID", "client-prod")
    monkeypatch.setenv("PLAID_SECRET", "secret-prod")
    monkeypatch.setenv("PLAID_PRODUCTS", "assets,balance")
    monkeypatch.setenv("PLAID_COUNTRY_CODES", "US")
    cfg = plaid_config_from_env()
    assert cfg.environment == "production"
    assert cfg.base_url == "https://production.plaid.com"
    assert cfg.products == ("assets", "balance")

    registry = tmp_path / "registry.db"
    store_access_token(access_token="access-production-token", item_id="item_prod", institution_id="ins_prod", institution_name="Production Bank", environment="production", path=registry)
    store_access_token(access_token="access-sandbox-token", item_id="item_sandbox", institution_id="ins_prod", institution_name="Sandbox Bank", environment="sandbox", path=registry)
    conn = _conn(registry)
    try:
        ensure_schema(conn)
    finally:
        conn.close()
    conn = _conn(registry)
    try:
        conn.execute(
            "INSERT INTO finance_institutions (provider, institution_id, institution_name, item_id, encrypted_access_token, status, products, created_at, updated_at) VALUES ('plaid', 'legacy_ins', 'Legacy Sandbox Bank', 'item_legacy', ?, 'active', '[]', 1, 1)",
            (encrypt_access_token("access-sandbox-legacy-token"),),
        )
        conn.commit()
    finally:
        conn.close()
    prod_tokens = list_stored_access_tokens(environment="production", path=registry)
    sandbox_tokens = list_stored_access_tokens(environment="sandbox", path=registry)
    assert [row["institution_id"] for row in prod_tokens] == ["ins_prod"]
    assert {row["institution_id"] for row in sandbox_tokens} == {"ins_prod", "legacy_ins"}
    assert load_access_token(institution_id="ins_prod", environment="production", path=registry) == "access-production-token"
    assert load_access_token(institution_id="ins_prod", environment="sandbox", path=registry) == "access-sandbox-token"
    with pytest.raises(PlaidConfigurationError):
        load_access_token(institution_id="legacy_ins", environment="production", path=registry)


def test_sandbox_token_storage_is_not_overwritten_by_production_token(tmp_path):
    registry = tmp_path / "registry.db"
    store_access_token(access_token="sandbox-token", item_id="sandbox_item", institution_id="shared_ins", institution_name="Sandbox Bank", environment="sandbox", path=registry)
    store_access_token(access_token="production-token", item_id="production_item", institution_id="shared_ins", institution_name="Production Bank", environment="production", path=registry)

    assert load_access_token(institution_id="shared_ins", environment="sandbox", path=registry) == "sandbox-token"
    assert load_access_token(institution_id="shared_ins", environment="production", path=registry) == "production-token"
    assert {row["institution_id"] for row in list_stored_access_tokens(environment="sandbox", path=registry)} == {"shared_ins"}
    assert {row["institution_id"] for row in list_stored_access_tokens(environment="production", path=registry)} == {"shared_ins"}
    assert (tmp_path / "sandbox" / "access_tokens.json").exists()
    assert (tmp_path / "production" / "access_tokens.json").exists()
    assert "production-token" not in (tmp_path / "sandbox" / "access_tokens.json").read_text(encoding="utf-8")
    assert "sandbox-token" not in (tmp_path / "production" / "access_tokens.json").read_text(encoding="utf-8")


def test_plaid_sandbox_configuration_uses_explicit_products_and_default_country_codes(monkeypatch):
    monkeypatch.setenv("PLAID_ENV", "sandbox")
    monkeypatch.setenv("PLAID_CLIENT_ID", "client-sandbox")
    monkeypatch.setenv("PLAID_SECRET", "secret-sandbox")
    monkeypatch.setenv("PLAID_PRODUCTS", "assets,balance")
    monkeypatch.delenv("PLAID_COUNTRY_CODES", raising=False)

    cfg = plaid_config_from_env()

    assert cfg.environment == "sandbox"
    assert cfg.base_url == "https://sandbox.plaid.com"
    assert cfg.products == ("assets", "balance")
    assert cfg.country_codes == ("US",)


def test_plaid_rejects_wrong_environment(monkeypatch):
    monkeypatch.setenv("PLAID_ENV", "development")
    monkeypatch.setenv("PLAID_CLIENT_ID", "client")
    monkeypatch.setenv("PLAID_SECRET", "secret")

    with pytest.raises(Exception, match="PLAID_ENV must be sandbox or production"):
        plaid_config_from_env()


def test_plaid_production_validation_requires_all_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("PLAID_ENV", "production")
    monkeypatch.setenv("PLAID_CLIENT_ID", "client-prod")
    monkeypatch.delenv("PLAID_SECRET", raising=False)
    monkeypatch.delenv("PLAID_PRODUCTS", raising=False)
    monkeypatch.delenv("PLAID_COUNTRY_CODES", raising=False)

    with pytest.raises(PlaidConfigurationError) as excinfo:
        plaid_config_from_env()

    message = str(excinfo.value)
    assert "PLAID_SECRET" in message
    assert "PLAID_PRODUCTS" in message
    assert "PLAID_COUNTRY_CODES" in message
    assert "client-prod" not in message


def test_plaid_env_file_loader_requires_private_permissions(monkeypatch, tmp_path):
    env_file = tmp_path / ".env.production"
    env_file.write_text("PLAID_ENV=production\nPLAID_CLIENT_ID=file-client\nPLAID_SECRET=file-secret\nPLAID_PRODUCTS=assets,balance\nPLAID_COUNTRY_CODES=US\n", encoding="utf-8")
    env_file.chmod(0o600)
    monkeypatch.delenv("PLAID_ENV", raising=False)
    monkeypatch.delenv("PLAID_CLIENT_ID", raising=False)
    monkeypatch.delenv("PLAID_SECRET", raising=False)
    monkeypatch.setenv("HERMES_PLAID_ENV_FILE", str(env_file))
    cfg = plaid_config_from_env()
    assert cfg.environment == "production"
    assert cfg.client_id == "file-client"
    assert cfg.products == ("assets", "balance")


def test_plaid_auto_loads_private_production_env_from_hermes_home(monkeypatch, tmp_path):
    env_file = tmp_path / ".env.production"
    env_file.write_text("PLAID_ENV=production\nPLAID_CLIENT_ID=file-client\nPLAID_SECRET=file-secret\nPLAID_PRODUCTS=assets,balance\nPLAID_COUNTRY_CODES=US\n", encoding="utf-8")
    env_file.chmod(0o600)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("PLAID_ENV", "production")
    monkeypatch.delenv("HERMES_PLAID_ENV_FILE", raising=False)
    monkeypatch.delenv("PLAID_CLIENT_ID", raising=False)
    monkeypatch.delenv("PLAID_SECRET", raising=False)
    monkeypatch.delenv("PLAID_PRODUCTS", raising=False)
    monkeypatch.delenv("PLAID_COUNTRY_CODES", raising=False)

    cfg = plaid_config_from_env()

    assert cfg.environment == "production"
    assert cfg.client_id == "file-client"
    assert cfg.products == ("assets", "balance")


def test_plaid_requested_production_env_overrides_stale_sandbox_process_env(monkeypatch, tmp_path):
    env_file = tmp_path / ".env.production"
    env_file.write_text("PLAID_ENV=production\nPLAID_CLIENT_ID=file-client\nPLAID_SECRET=file-secret\nPLAID_PRODUCTS=assets,balance\nPLAID_COUNTRY_CODES=US\n", encoding="utf-8")
    env_file.chmod(0o600)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_PLAID_REQUESTED_ENV", "production")
    monkeypatch.setenv("PLAID_ENV", "sandbox")
    monkeypatch.setenv("PLAID_CLIENT_ID", "stale-sandbox-client")
    monkeypatch.setenv("PLAID_SECRET", "stale-sandbox-secret")
    monkeypatch.setenv("PLAID_PRODUCTS", "transactions")
    monkeypatch.delenv("HERMES_PLAID_ENV_FILE", raising=False)

    cfg = plaid_config_from_env()

    assert cfg.environment == "production"
    assert cfg.client_id == "file-client"
    assert cfg.products == ("assets", "balance")


def test_plaid_production_requested_sandbox_resolved_raises_mismatch(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_PLAID_REQUESTED_ENV", "production")
    monkeypatch.setenv("PLAID_ENV", "sandbox")
    monkeypatch.setenv("PLAID_CLIENT_ID", "stale-sandbox-client")
    monkeypatch.setenv("PLAID_SECRET", "stale-sandbox-secret")
    monkeypatch.setenv("PLAID_PRODUCTS", "transactions")
    monkeypatch.setenv("PLAID_COUNTRY_CODES", "US")
    monkeypatch.delenv("HERMES_PLAID_ENV_FILE", raising=False)

    with pytest.raises(Exception, match="production_environment_mismatch"):
        plaid_config_from_env()


def test_plaid_link_token_uses_sandbox_when_explicitly_sandbox(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    calls: list[tuple[str, dict[str, object]]] = []

    def transport(endpoint, payload):
        calls.append((endpoint, payload))
        return {"link_token": "link-sandbox", "request_id": "req-sandbox"}

    connector = PlaidConnector(PlaidConfig(client_id="client", secret="secret", environment="sandbox", products=("assets", "balance")), transport=transport)
    result = connector.create_link_token()

    assert result["link_token"] == "link-sandbox"
    assert calls[0][0] == "/link/token/create"
    assert calls[0][1]["products"] == ["assets", "balance"]
    assert connector.safe_diagnostics()["plaid_base_url"] == "https://sandbox.plaid.com"


def test_plaid_runtime_status_is_safe_and_reports_namespace(monkeypatch, tmp_path):
    from hermes_cli.plaid_connector import plaid_runtime_status

    env_file = tmp_path / ".env.production"
    env_file.write_text("PLAID_ENV=production\nPLAID_CLIENT_ID=file-client\nPLAID_SECRET=file-secret\nPLAID_PRODUCTS=assets,balance\nPLAID_COUNTRY_CODES=US\n", encoding="utf-8")
    env_file.chmod(0o600)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("PLAID_ENV", "production")
    monkeypatch.delenv("HERMES_PLAID_ENV_FILE", raising=False)
    monkeypatch.delenv("PLAID_CLIENT_ID", raising=False)
    monkeypatch.delenv("PLAID_SECRET", raising=False)
    monkeypatch.delenv("PLAID_PRODUCTS", raising=False)
    monkeypatch.delenv("PLAID_COUNTRY_CODES", raising=False)

    status = plaid_runtime_status(path=tmp_path / "registry.db")

    assert status["environment"] == "production"
    assert status["env_source_path"] == str(env_file)
    assert status["token_namespace"]["path"].endswith("production")
    assert status["products"] == ["assets", "balance"]
    assert status["product_diagnostics"]["invalid_link_products"] == ["balance"]
    assert status["product_diagnostics"]["asset_report_flow_requested"] is True
    assert status["link_token_request"] == {
        "method": "POST",
        "endpoint": "/link/token/create",
        "base_url": "https://production.plaid.com",
        "body": {
            "client_name": "Hermes Finance Registry",
            "country_codes": ["US"],
            "language": "en",
            "user": {"client_user_id": "hermes-finance"},
            "products": ["assets", "balance"],
        },
        "excluded_secret_fields": ["client_id", "secret"],
    }
    assert "file-secret" not in str(status)


def test_plaid_link_token_failure_diagnostics_include_exact_safe_request_shape(monkeypatch, tmp_path):
    from hermes_cli.plaid_connector import PlaidAPIError

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    def transport(endpoint, payload):
        raise PlaidAPIError(endpoint, {"http_status": 400, "error_code": "INVALID_PRODUCT", "error_message": "bad product"})

    connector = PlaidConnector(PlaidConfig(client_id="client", secret="secret", environment="production", products=("assets", "balance")), transport=transport)

    with pytest.raises(PlaidAPIError) as err:
        connector.create_link_token(user_id="diagnostic-user")

    diagnostics = err.value.diagnostics
    assert diagnostics["link_token_request"]["body"] == {
        "client_name": "Hermes Finance Registry",
        "country_codes": ["US"],
        "language": "en",
        "user": {"client_user_id": "diagnostic-user"},
        "products": ["assets", "balance"],
    }
    assert diagnostics["link_token_request"]["excluded_secret_fields"] == ["client_id", "secret"]
    assert diagnostics["product_diagnostics"]["invalid_link_products"] == ["balance"]
    assert "client_id" in diagnostics["link_token_request"]["excluded_secret_fields"]
    assert "secret" in diagnostics["link_token_request"]["excluded_secret_fields"]
    assert "client=client" not in str(diagnostics)
    assert "secret=secret" not in str(diagnostics)


def test_plaid_production_config_dry_run_reports_safe_status(monkeypatch, tmp_path):
    from hermes_cli.plaid_connector import validate_production_config

    env_file = tmp_path / ".env.production"
    env_file.write_text("PLAID_ENV=production\nPLAID_CLIENT_ID=file-client\nPLAID_SECRET=file-secret\nPLAID_PRODUCTS=assets,balance\nPLAID_COUNTRY_CODES=US\n", encoding="utf-8")
    env_file.chmod(0o600)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("PLAID_CLIENT_ID", raising=False)
    monkeypatch.delenv("PLAID_SECRET", raising=False)
    monkeypatch.delenv("PLAID_PRODUCTS", raising=False)
    monkeypatch.delenv("PLAID_COUNTRY_CODES", raising=False)

    result = validate_production_config(env_file=env_file, path=tmp_path / "registry.db")

    assert result["environment"] == "production"
    assert result["credentials_loaded"] is True
    assert result["keys"]["PLAID_SECRET"] == {"present": True, "length": len("file-secret"), "placeholder": False}
    assert result["products_valid"] is True
    assert result["country_codes_valid"] is True
    assert result["sandbox_tokens_remain_separate"] is True
    assert result["production_token_namespace_empty"] is True
    assert result["production_access_token_exists"] is False
    assert "file-secret" not in str(result)


def test_plaid_api_exception_parsing_filters_to_safe_fields(monkeypatch):
    from hermes_cli.plaid_connector import _safe_plaid_error_from_exception

    monkeypatch.setenv("PLAID_CLIENT_ID", "client-secret-value")
    monkeypatch.setenv("PLAID_SECRET", "plaid-secret-value")

    class ApiException(Exception):
        status = 400
        body = '{"error_type":"INVALID_REQUEST","error_code":"INVALID_FIELD","error_message":"bad client-secret-value plaid-secret-value","request_id":"req-safe","documentation_url":"https://plaid.com/docs/errors/","access_token":"access-leak","public_token":"public-leak","link_token":"link-leak"}'

    safe = _safe_plaid_error_from_exception(ApiException("boom"))

    assert safe == {
        "http_status": 400,
        "error_type": "INVALID_REQUEST",
        "error_code": "INVALID_FIELD",
        "error_message": "bad [REDACTED] [REDACTED]",
        "request_id": "req-safe",
        "documentation_url": "https://plaid.com/docs/errors/",
    }
    assert "access-leak" not in str(safe)
    assert "public-leak" not in str(safe)
    assert "link-leak" not in str(safe)


def test_plaid_http_error_becomes_safe_plaid_api_error(monkeypatch):
    from urllib.error import HTTPError

    from hermes_cli.plaid_connector import PlaidAPIError

    def transport_error(req, timeout=30):
        body = b'{"error_type":"API_ERROR","error_code":"PRODUCT_NOT_ENABLED","error_message":"Product is not enabled","request_id":"req-http"}'
        raise HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(body))

    monkeypatch.setattr("hermes_cli.plaid_connector.request.urlopen", transport_error)
    connector = PlaidConnector(PlaidConfig(client_id="client", secret="secret", environment="production"))

    with pytest.raises(PlaidAPIError) as err:
        connector.create_link_token()

    assert err.value.safe_error == {
        "http_status": 400,
        "error_type": "API_ERROR",
        "error_code": "PRODUCT_NOT_ENABLED",
        "error_message": "Product is not enabled",
        "request_id": "req-http",
    }
    assert err.value.diagnostics["plaid_base_url"] == "https://production.plaid.com"
    assert "client" not in str(err.value.safe_error)
    assert "secret" not in str(err.value.safe_error)


def test_plaid_sandbox_sync_with_mock_transport(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    calls: list[str] = []

    def transport(endpoint, payload):
        calls.append(endpoint)
        assert payload["client_id"] == "client"
        assert payload["secret"] == "secret"
        if endpoint == "/accounts/get":
            return {"item": {"institution_id": "ins_sandbox", "item_id": "item_1", "institution_name": "Sandbox Bank"}, "accounts": []}
        if endpoint == "/accounts/balance/get":
            return {"accounts": [{"account_id": "acc_checking", "name": "Checking", "type": "depository", "subtype": "checking", "mask": "0000", "balances": {"current": 100, "available": 90, "iso_currency_code": "USD"}}]}
        if endpoint == "/transactions/get":
            return {"transactions": [{"transaction_id": "txn_1", "account_id": "acc_checking", "date": "2999-01-01", "amount": 10, "name": "Coffee", "merchant_name": "Cafe", "pending": False}]}
        if endpoint == "/liabilities/get":
            return {"liabilities": {"credit": []}}
        if endpoint == "/investments/holdings/get":
            return {"holdings": [], "securities": []}
        raise AssertionError(endpoint)

    connector = PlaidConnector(PlaidConfig(client_id="client", secret="secret", products=("balance",)), transport=transport)
    result = connector.sync_to_finance_registry(access_token="access-sandbox", path=tmp_path / "registry.db")
    assert result["status"] == "success"
    assert result["counts"]["accounts"] == 1
    assert "/accounts/balance/get" in calls
    assert "/transactions/get" not in calls

    contract = finance_command_center_contract(path=tmp_path / "registry.db")
    assert contract["source"]["model"] == "normalized"
    assert contract["sync"]["sync_health"] == "healthy"


def test_plaid_sync_failure_records_error(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    def transport(endpoint, payload):
        raise RuntimeError("sandbox failed")

    connector = PlaidConnector(PlaidConfig(client_id="client", secret="secret"), transport=transport)
    with pytest.raises(RuntimeError):
        connector.sync_to_finance_registry(access_token="access-sandbox", path=tmp_path / "registry.db")

    from hermes_cli.finance_registry import latest_finance_sync_status

    status = latest_finance_sync_status(path=tmp_path / "registry.db")
    assert status["sync_health"] == "error"
    assert status["errors"]
