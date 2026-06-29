from pathlib import Path

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]

from hermes_cli.finance_registry import (
    FINANCE_EMPTY_MESSAGE,
    calculate_finance_metrics,
    finance_command_center_contract,
    finance_history,
    insert_finance_snapshot,
    seed_default_finance_registry,
)


def test_finance_metrics_engine_calculates_core_metrics():
    metrics = calculate_finance_metrics(
        {
            "annual_income": 52000,
            "monthly_expenses": 215,
            "emergency_fund": 410,
            "emergency_fund_target": 1000,
            "car_fund": 1000,
            "car_fund_target": 5000,
            "brokerage_value": 500,
            "checking_balance": 250,
            "savings_balance": 250,
            "debt_total": 200,
            "debt_original_total": 1000,
        }
    )

    assert metrics["monthly_income"] == 4333.33
    assert metrics["monthly_burn"] == 215
    assert metrics["net_worth"] == 2210
    assert metrics["runway_months"] == 4.23
    assert metrics["emergency_fund_completion_percent"] == 41
    assert metrics["car_fund_completion_percent"] == 20
    assert metrics["investment_allocation_percent"] == 22.62
    assert metrics["debt_payoff_progress_percent"] == 80
    assert metrics["savings_rate_percent"] == 95.04


def test_finance_registry_empty_state_uses_source_not_initialized(tmp_path):
    path = tmp_path / "finance.db"

    contract = finance_command_center_contract(path=path)

    assert contract["initialized"] is False
    assert contract["empty_message"] == FINANCE_EMPTY_MESSAGE
    assert contract["setup_action"]["endpoint"] == "/api/finance/seed-defaults"
    assert contract["widgets"]
    assert {widget["value"] for widget in contract["widgets"]} == {FINANCE_EMPTY_MESSAGE}
    assert "Awaiting" not in str(contract)
    assert "No Data" not in str(contract)
    assert "Not Configured" not in str(contract)


def test_finance_registry_seed_and_history_are_source_backed(tmp_path):
    path = tmp_path / "finance.db"

    seed_default_finance_registry(path=path)
    insert_finance_snapshot(
        {
            "annual_income": 52000,
            "monthly_expenses": 215,
            "emergency_fund": 100,
            "emergency_fund_target": 1000,
            "car_fund": 25,
            "car_fund_target": 5000,
            "brokerage_value": 10,
            "checking_balance": 50,
            "savings_balance": 60,
            "debt_total": 0,
        },
        captured_at=9999999999,
        path=path,
    )

    contract = finance_command_center_contract(path=path)
    widgets = {widget["label"]: widget for widget in contract["widgets"]}

    assert contract["initialized"] is True
    assert contract["source"]["type"] == "finance_registry"
    assert widgets["Net Worth"]["value"] == 245
    assert widgets["Emergency Fund"]["detail"] == "10% of $1,000 target"
    assert widgets["Runway"]["detail"] == "Liquid assets / monthly burn"
    history_values = [point["value"] for point in finance_history("net_worth", path=path)]
    assert 245.0 in history_values
    assert len(history_values) == 2


def test_finance_command_center_frontend_uses_source_initialized_empty_state():
    source = (REPO_ROOT / "web" / "src" / "pages" / "ReportsPage.tsx").read_text(encoding="utf-8")
    finance_section = source[
        source.index('eyebrow="Finance" title="Finance Command Center"'):
        source.index('eyebrow="Career" title="Career Command"')
    ]

    assert "No Metrics Yet" not in finance_section
    assert "Awaiting" not in finance_section
    assert "No Data Yet" not in finance_section
    assert "Not Configured" not in finance_section
    assert "Finance Registry via Dashboard API" in finance_section


def test_finance_api_empty_seed_widgets_trends(monkeypatch, tmp_path):
    from hermes_cli import web_server
    from hermes_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN

    db_path = tmp_path / "registry.db"
    monkeypatch.setenv("HERMES_FINANCE_REGISTRY_PATH", str(db_path))
    client = TestClient(web_server.app)
    client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN

    empty = client.get("/api/finance/widgets")
    assert empty.status_code == 200
    empty_body = empty.json()
    assert empty_body["initialized"] is False
    assert empty_body["empty_message"] == FINANCE_EMPTY_MESSAGE
    assert all(widget["value"] == FINANCE_EMPTY_MESSAGE for widget in empty_body["widgets"])

    seeded = client.post("/api/finance/seed-defaults")
    assert seeded.status_code == 200
    seeded_body = seeded.json()
    assert seeded_body["initialized"] is True
    assert seeded_body["metrics"]["monthly_income"] == 4333.33
    assert seeded_body["metrics"]["monthly_burn"] == 215

    dashboard = client.get("/api/dashboard/v2")
    assert dashboard.status_code == 200
    financial = dashboard.json()["financial_metrics"]
    labels = {metric["label"] for metric in financial["metrics"]}
    assert {
        "Net Worth",
        "Emergency Fund",
        "Car Fund",
        "Brokerage",
        "Monthly Income",
        "Monthly Expenses",
        "Runway",
        "Debt",
        "Savings Rate",
    }.issubset(labels)
    assert financial["source"]["type"] == "finance_registry"

    trend = client.get("/api/finance/trends/net_worth")
    assert trend.status_code == 200
    assert trend.json()["points"]

    unknown = client.get("/api/finance/trends/unknown")
    assert unknown.status_code == 404


def test_dashboard_finance_sync_endpoint_runs_registry_sync_and_refreshes(monkeypatch, tmp_path):
    from hermes_cli import web_server
    from hermes_cli.finance_registry import finish_finance_sync_run, finance_registry_path, start_finance_sync_run, upsert_plaid_registry_data
    from hermes_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN

    db_path = tmp_path / "registry.db"
    monkeypatch.setenv("HERMES_FINANCE_REGISTRY_PATH", str(db_path))
    calls = {"count": 0}

    class FakePlaidConnector:
        def sync_to_finance_registry(self):
            calls["count"] += 1
            run_id = start_finance_sync_run(path=finance_registry_path())
            counts = upsert_plaid_registry_data(
                {
                    "institution": {"institution_id": "ins_sandbox", "name": "Plaid Sandbox", "item_id": "item_1"},
                    "accounts": [{"account_id": "acc_checking", "name": "Checking", "type": "depository", "subtype": "checking", "balances": {"current": 12, "available": 12, "iso_currency_code": "USD"}}],
                    "transactions": [{"transaction_id": "txn_1", "account_id": "acc_checking", "date": "2999-01-01", "amount": -48, "name": "Payroll", "pending": False}],
                },
                sync_run_id=run_id,
                path=finance_registry_path(),
            )
            finish_finance_sync_run(run_id, status="success", message="ok", counts=counts, path=finance_registry_path())
            return {"status": "success", "counts": counts}

    monkeypatch.setattr("hermes_cli.plaid_connector.PlaidConnector", FakePlaidConnector)
    client = TestClient(web_server.app)
    client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN

    resp = client.post("/api/dashboard/v2/finance/sync")

    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "Synced Successfully"
    assert body["sync"]["sync_health"] == "healthy"
    assert body["sync"]["accounts_count"] == 1
    assert body["financial_metrics"]["finance_command_center"]["source"]["model"] == "normalized"
    assert calls["count"] == 1


def test_dashboard_finance_sync_endpoint_returns_friendly_errors(monkeypatch, tmp_path):
    from hermes_cli import web_server
    from hermes_cli.plaid_connector import PlaidConfigurationError
    from hermes_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN

    monkeypatch.setenv("HERMES_FINANCE_REGISTRY_PATH", str(tmp_path / "registry.db"))

    class FakePlaidConnector:
        def sync_to_finance_registry(self):
            raise PlaidConfigurationError("No encrypted Plaid access token is stored.")

    monkeypatch.setattr("hermes_cli.plaid_connector.PlaidConnector", FakePlaidConnector)
    client = TestClient(web_server.app)
    client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN

    resp = client.post("/api/dashboard/v2/finance/sync")

    assert resp.status_code == 409
    assert resp.json()["detail"] == {"code": "no_access_token", "message": "Reconnect financial institution."}


def test_dashboard_finance_sync_endpoint_rejects_duplicate_requests(monkeypatch):
    from hermes_cli import web_server
    from hermes_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN

    assert web_server._FINANCE_SYNC_LOCK.acquire(blocking=False) is True
    try:
        client = TestClient(web_server.app)
        client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
        resp = client.post("/api/dashboard/v2/finance/sync")
    finally:
        web_server._FINANCE_SYNC_LOCK.release()

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "sync_running"


def test_finance_plaid_link_token_endpoint_returns_sandbox_token(monkeypatch, tmp_path):
    from hermes_cli import web_server
    from hermes_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN

    monkeypatch.setenv("HERMES_FINANCE_REGISTRY_PATH", str(tmp_path / "registry.db"))

    class FakeConfig:
        environment = "sandbox"

    class FakePlaidConnector:
        config = FakeConfig()

        def create_link_token(self):
            return {"link_token": "link-sandbox-test", "expiration": "2099-01-01T00:00:00Z", "request_id": "req_1"}

    monkeypatch.setattr("hermes_cli.plaid_connector.PlaidConnector", FakePlaidConnector)
    client = TestClient(web_server.app)
    client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN

    resp = client.post("/api/finance/plaid/link-token")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["link_token"] == "link-sandbox-test"
    assert body["environment"] == "Sandbox"
    assert "secret" not in str(body).lower()
    assert "access_token" not in str(body)


def test_finance_plaid_exchange_public_token_stores_encrypted_and_refreshes_dashboard(monkeypatch, tmp_path):
    from hermes_cli import web_server
    from hermes_cli.finance_registry import finish_finance_sync_run, finance_registry_path, start_finance_sync_run, upsert_plaid_registry_data
    from hermes_cli.plaid_connector import store_access_token
    from hermes_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN

    db_path = tmp_path / "registry.db"
    key_path = tmp_path / "plaid.key"
    raw_access_token = "access-sandbox-secret"
    monkeypatch.setenv("HERMES_FINANCE_REGISTRY_PATH", str(db_path))
    monkeypatch.setenv("HERMES_FINANCE_TOKEN_KEY_PATH", str(key_path))
    calls = {"exchange": 0, "sync": 0}

    class FakePlaidConnector:
        def exchange_public_token(self, public_token, *, metadata=None):
            calls["exchange"] += 1
            assert public_token == "public-sandbox-token"
            store_access_token(
                access_token=raw_access_token,
                item_id="item_1",
                institution_id="ins_1",
                institution_name="Sandbox Bank",
                path=finance_registry_path(),
            )
            return {"access_token": "[ENCRYPTED_AND_STORED]", "item_id": "item_1", "environment": "sandbox"}

        def sync_to_finance_registry(self):
            calls["sync"] += 1
            run_id = start_finance_sync_run(path=finance_registry_path())
            counts = upsert_plaid_registry_data(
                {
                    "institution": {"institution_id": "ins_1", "name": "Sandbox Bank", "item_id": "item_1"},
                    "accounts": [{"account_id": "acc_1", "name": "Checking", "type": "depository", "subtype": "checking", "mask": "0000", "balances": {"current": 10, "available": 10, "iso_currency_code": "USD"}}],
                },
                sync_run_id=run_id,
                path=finance_registry_path(),
            )
            finish_finance_sync_run(run_id, status="success", message="ok", counts=counts, path=finance_registry_path())
            return {"status": "success", "counts": counts}

    monkeypatch.setattr("hermes_cli.plaid_connector.PlaidConnector", FakePlaidConnector)
    client = TestClient(web_server.app)
    client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN

    resp = client.post(
        "/api/finance/plaid/exchange-public-token",
        json={"public_token": "public-sandbox-token", "metadata": {"institution": {"institution_id": "ins_1", "name": "Sandbox Bank"}}},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "Bank connected and synced successfully."
    assert body["sync"]["sync_health"] == "healthy"
    assert body["sync"]["accounts_count"] == 1
    assert body["financial_metrics"]["finance_command_center"]["source"]["model"] == "normalized"
    assert calls == {"exchange": 1, "sync": 1}
    assert raw_access_token not in str(body)

    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        encrypted = conn.execute("SELECT encrypted_access_token FROM finance_institutions WHERE institution_id='ins_1'").fetchone()[0]
    finally:
        conn.close()
    assert encrypted
    assert encrypted != raw_access_token
    assert raw_access_token not in encrypted


def test_finance_plaid_exchange_public_token_returns_friendly_failure(monkeypatch, tmp_path):
    from hermes_cli import web_server
    from hermes_cli.plaid_connector import PlaidConfigurationError
    from hermes_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN

    monkeypatch.setenv("HERMES_FINANCE_REGISTRY_PATH", str(tmp_path / "registry.db"))

    class FakePlaidConnector:
        def exchange_public_token(self, public_token, *, metadata=None):
            raise PlaidConfigurationError("PLAID_CLIENT_ID and PLAID_SECRET are required in the environment.")

    monkeypatch.setattr("hermes_cli.plaid_connector.PlaidConnector", FakePlaidConnector)
    client = TestClient(web_server.app)
    client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN

    resp = client.post("/api/finance/plaid/exchange-public-token", json={"public_token": "public-sandbox-token"})

    assert resp.status_code == 400
    assert resp.json()["detail"] == {"code": "configuration_missing", "message": "Plaid credentials missing."}


def test_normalized_registry_drives_executive_dashboard_kpis_and_api_payload(tmp_path, monkeypatch):
    from hermes_cli.finance_registry import (
        dashboard_financial_metrics,
        ensure_schema,
        finance_command_center_contract,
        finish_finance_sync_run,
        start_finance_sync_run,
        upsert_plaid_registry_data,
    )
    import sqlite3

    path = tmp_path / "registry.db"
    monkeypatch.setenv("HERMES_FINANCE_REGISTRY_PATH", str(path))
    run_id = start_finance_sync_run(path=path)
    counts = upsert_plaid_registry_data(
        {
            "institution": {"institution_id": "ins_live", "name": "Live Registry Bank", "item_id": "item_live"},
            "accounts": [
                {"account_id": "acc_checking", "name": "Checking", "type": "depository", "subtype": "checking", "balances": {"current": 100, "available": 80, "iso_currency_code": "USD"}},
                {"account_id": "acc_savings", "name": "Savings", "type": "depository", "subtype": "savings", "balances": {"current": 200, "available": 200, "iso_currency_code": "USD"}},
                {"account_id": "acc_ef", "name": "Emergency Fund", "type": "depository", "subtype": "money market", "fund_category": "emergency", "balances": {"current": 500, "available": 500, "iso_currency_code": "USD"}},
                {"account_id": "acc_car", "name": "Car Fund", "type": "depository", "subtype": "cash management", "fund_category": "car", "balances": {"current": 400, "available": 400, "iso_currency_code": "USD"}},
                {"account_id": "acc_brokerage", "name": "Brokerage", "type": "investment", "subtype": "brokerage", "balances": {"current": 1000, "iso_currency_code": "USD"}},
                {"account_id": "acc_credit", "name": "Credit Card", "type": "credit", "subtype": "credit card", "balances": {"current": 50, "available": 150, "iso_currency_code": "USD"}},
                {"account_id": "acc_loan", "name": "Student Loan", "type": "loan", "subtype": "student", "balances": {"current": 300, "iso_currency_code": "USD"}},
            ],
            "transactions": [
                {"transaction_id": "txn_income", "account_id": "acc_checking", "date": "2099-06-30", "amount": -1000, "name": "Payroll", "pending": False},
                {"transaction_id": "txn_expense", "account_id": "acc_checking", "date": "2099-06-29", "amount": 400, "name": "Rent", "pending": False},
                {"transaction_id": "txn_transfer", "account_id": "acc_savings", "date": "2099-06-28", "amount": 25, "name": "Transfer to savings", "category": ["Transfer"], "pending": False},
            ],
            "holdings": [{"account_id": "acc_brokerage", "security_id": "sec_vti", "quantity": 10, "institution_price": 100, "institution_value": 1000, "iso_currency_code": "USD"}],
            "securities": [{"security_id": "sec_vti", "ticker_symbol": "VTI", "name": "Total Market ETF"}],
        },
        sync_run_id=run_id,
        path=path,
    )
    finish_finance_sync_run(run_id, status="success", message="ok", counts=counts, path=path)

    # Add an older balance/investment point so trend charts prove normalized history is used, not finance_snapshots.
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        ensure_schema(conn)
        conn.execute("INSERT INTO finance_sync_runs (id, provider, environment, started_at, completed_at, status, accounts_count, transactions_count, liabilities_count, investments_count, message) VALUES (99, 'plaid', 'sandbox', 1, 1, 'success', 7, 3, 0, 1, 'older')")
        for account_id, balance in [("acc_checking", 90), ("acc_savings", 190), ("acc_ef", 450), ("acc_car", 350), ("acc_credit", 40), ("acc_loan", 320)]:
            conn.execute("INSERT INTO finance_balances (provider, provider_account_id, captured_at, current_balance, available_balance, iso_currency_code, sync_run_id) VALUES ('plaid', ?, 1, ?, ?, 'USD', 99)", (account_id, balance, balance))
        conn.execute("INSERT INTO finance_investments (provider, provider_account_id, security_id, ticker_symbol, security_name, quantity, price, investment_holdings, iso_currency_code, captured_at, sync_run_id) VALUES ('plaid', 'acc_brokerage', 'sec_vti_old', 'VTI', 'Total Market ETF', 9, 100, 900, 'USD', 1, 99)")
        conn.commit()
    finally:
        conn.close()

    contract = finance_command_center_contract(path=path)
    metrics = contract["metrics"]
    kpis = contract["executive_dashboard"]["kpis"]

    assert contract["source"]["model"] == "normalized"
    assert metrics["cash_position"] == 1200
    assert metrics["brokerage_value"] == 1000
    assert metrics["total_debt"] == 350
    assert metrics["net_worth"] == 1850
    assert metrics["monthly_income"] == 1000
    assert metrics["monthly_expenses"] == 400
    assert metrics["net_cash_flow"] == 600
    assert metrics["runway_months"] == 3
    assert metrics["savings_rate_percent"] == 60
    assert kpis["cash_available"]["available_cash"] == 1200
    assert kpis["credit_utilization"]["current_utilization"] == 25
    assert kpis["emergency_fund"]["current"] == 500
    assert kpis["emergency_fund"]["progress_percent"] == 50
    assert kpis["debt"]["total_debt"] == 350
    assert contract["executive_dashboard"]["connected_institutions"][0]["institution_name"] == "Live Registry Bank"
    assert contract["executive_dashboard"]["recent_activity"]["latest_income"][0]["name"] == "Payroll"
    assert contract["executive_dashboard"]["recent_activity"]["investment_activity"]
    assert contract["executive_dashboard"]["alerts"]
    assert all("placeholder" not in insight.lower() for insight in contract["executive_dashboard"]["insights"])
    assert len(contract["executive_dashboard"]["trends"]["net_worth_30_days"]["points"]) >= 2

    api_payload = dashboard_financial_metrics()
    api_exec = api_payload["executive_dashboard"]
    assert api_payload["finance_command_center"]["source"]["model"] == "normalized"
    assert api_exec["kpis"]["net_worth"]["current"] == 1850
    assert api_exec["kpis"]["cash_available"]["available_cash"] == 1200
    assert api_exec["connected_institutions"]
    assert api_exec["recent_activity"]["largest_recent_expenses"]


def test_finance_dashboard_source_has_no_legacy_or_mock_finance_dependencies():
    source = (REPO_ROOT / "web" / "src" / "pages" / "ReportsPage.tsx").read_text(encoding="utf-8")
    finance_source = source[
        source.index("function ExecutiveFinanceDashboard"):
        source.index("function FinanceSyncConsole")
    ]
    banned = ["finance_snapshots", "mockFinance", "mockPlaid", "demo", "placeholder"]
    for token in banned:
        assert token not in finance_source
    assert "finance.executiveDashboard" in finance_source
    assert "financeKpi(exec" in finance_source
    assert "exec.connected_institutions" in finance_source
    assert "exec.recent_activity" in finance_source
    assert "exec.trends" in finance_source
