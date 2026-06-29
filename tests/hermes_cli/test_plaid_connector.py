from __future__ import annotations

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
    load_access_token,
    store_access_token,
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
    conn = _conn(path)
    try:
        stored = conn.execute("SELECT encrypted_access_token FROM finance_institutions WHERE institution_id='ins_sandbox'").fetchone()["encrypted_access_token"]
        assert stored != token
        assert token not in stored
    finally:
        conn.close()


def test_missing_token_handling(tmp_path):
    with pytest.raises(PlaidConfigurationError):
        load_access_token(path=tmp_path / "registry.db")


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

    connector = PlaidConnector(PlaidConfig(client_id="client", secret="secret"), transport=transport)
    result = connector.sync_to_finance_registry(access_token="access-sandbox", path=tmp_path / "registry.db")
    assert result["status"] == "success"
    assert result["counts"]["accounts"] == 1
    assert "/transactions/get" in calls

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
    assert status["sync_health"] == "degraded"
    assert status["errors"]
