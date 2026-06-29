"""Source-backed finance registry for the Hermes OS Executive dashboard.

The registry is intentionally small and local-first: a SQLite database under
``$HERMES_HOME/finance/registry.db`` stores point-in-time snapshots. Dashboard
widgets and trend endpoints read this module instead of hard-coded frontend or
API placeholders.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Iterable

from hermes_cli.config import get_hermes_home

FINANCE_EMPTY_MESSAGE = "Source not initialized"
FINANCE_SETUP_ACTION = {
    "label": "Initialize finance source",
    "method": "POST",
    "endpoint": "/api/finance/seed-defaults",
}

MONEY_FIELDS: tuple[str, ...] = (
    "annual_income",
    "monthly_income",
    "monthly_expenses",
    "emergency_fund",
    "emergency_fund_target",
    "car_fund",
    "car_fund_target",
    "brokerage_value",
    "brokerage_contributions",
    "checking_balance",
    "savings_balance",
    "debt_total",
    "net_worth",
    "runway_months",
    "savings_rate_percent",
    "debt_payoff_progress_percent",
    "brokerage_growth_percent",
    "net_cash_flow",
)

TREND_METRICS: frozenset[str] = frozenset(
    {
        "net_worth",
        "emergency_fund",
        "car_fund",
        "brokerage_value",
        "brokerage_growth_percent",
        "monthly_income",
        "monthly_expenses",
        "runway_months",
        "debt_total",
        "savings_rate_percent",
        "debt_payoff_progress_percent",
        "net_cash_flow",
    }
)

WIDGET_ORDER: tuple[tuple[str, str, str], ...] = (
    ("net_worth", "Net Worth", "currency"),
    ("emergency_fund", "Emergency Fund", "currency"),
    ("car_fund", "Car Fund", "currency"),
    ("brokerage", "Brokerage", "currency"),
    ("monthly_income", "Monthly Income", "currency"),
    ("monthly_expenses", "Monthly Expenses", "currency"),
    ("runway", "Runway", "months"),
    ("debt", "Debt", "currency"),
    ("savings_rate", "Savings Rate", "percent"),
)

DEFAULT_SEED: dict[str, Any] = {
    "annual_income": 52000.0,
    "monthly_income": round(52000.0 / 12.0, 2),
    "monthly_expenses": 215.0,
    "expense_accounts": [
        {"name": "Electric", "amount": 100.0, "cadence": "monthly"},
        {"name": "Internet", "amount": 70.0, "cadence": "monthly"},
        {"name": "Phone", "amount": 45.0, "cadence": "monthly"},
    ],
    "housing": {"status": "HUD-VASH currently covering rent", "monthly_rent": 0.0},
    "transportation": {"status": "No vehicle yet", "monthly_vehicle_cost": 0.0},
    "emergency_fund": 0.0,
    "emergency_fund_target": 1000.0,
    "car_fund": 0.0,
    "car_fund_target": 5000.0,
    "brokerage_value": 0.0,
    "brokerage_contributions": 0.0,
    "checking_balance": 0.0,
    "savings_balance": 0.0,
    "debt_total": 0.0,
    "debt_accounts": [],
    "debt_original_total": 0.0,
    "notes": ["Debt account registry initialized; add accounts as balances become available."],
}


def finance_registry_path() -> Path:
    configured = os.environ.get("HERMES_FINANCE_REGISTRY_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    return get_hermes_home() / "finance" / "registry.db"


@dataclass(frozen=True)
class FinanceSourceState:
    initialized: bool
    path: Path
    latest: dict[str, Any] | None


def _connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or finance_registry_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='finance_snapshots'"
    ).fetchone()
    return row is not None


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS finance_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            captured_at INTEGER NOT NULL,
            annual_income REAL,
            monthly_income REAL,
            monthly_expenses REAL,
            emergency_fund REAL,
            emergency_fund_target REAL,
            car_fund REAL,
            car_fund_target REAL,
            brokerage_value REAL,
            brokerage_contributions REAL,
            checking_balance REAL,
            savings_balance REAL,
            debt_total REAL,
            debt_accounts TEXT NOT NULL DEFAULT '[]',
            debt_original_total REAL,
            net_worth REAL,
            runway_months REAL,
            savings_rate_percent REAL,
            debt_payoff_progress_percent REAL,
            brokerage_growth_percent REAL,
            net_cash_flow REAL,
            payload TEXT NOT NULL
        )
        """
    )
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(finance_snapshots)").fetchall()}
    for column in ("savings_rate_percent", "debt_payoff_progress_percent", "brokerage_growth_percent", "net_cash_flow"):
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE finance_snapshots ADD COLUMN {column} REAL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_finance_snapshots_captured_at ON finance_snapshots(captured_at)")
    conn.commit()


def _number(value: Any, default: float | None = 0.0) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _sum_accounts(accounts: Any) -> float:
    if not isinstance(accounts, list):
        return 0.0
    total = 0.0
    for account in accounts:
        if isinstance(account, dict):
            total += float(_number(account.get("amount", account.get("balance", account.get("current_balance"))), 0.0) or 0.0)
    return total


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if denominator is None or denominator <= 0 or numerator is None:
        return None
    return round((numerator / denominator) * 100.0, 2)


def _round_money(value: float | None) -> float | None:
    return None if value is None else round(float(value), 2)


def calculate_finance_metrics(snapshot: dict[str, Any]) -> dict[str, Any]:
    annual_income = _number(snapshot.get("annual_income"), None)
    monthly_income = _number(snapshot.get("monthly_income"), None)
    if monthly_income is None and annual_income is not None:
        monthly_income = annual_income / 12.0

    expense_accounts_total = _sum_accounts(snapshot.get("expense_accounts"))
    monthly_expenses = _number(snapshot.get("monthly_expenses"), None)
    if monthly_expenses is None:
        monthly_expenses = expense_accounts_total

    emergency_fund = _number(snapshot.get("emergency_fund"), 0.0) or 0.0
    emergency_target = _number(snapshot.get("emergency_fund_target"), None)
    car_fund = _number(snapshot.get("car_fund"), 0.0) or 0.0
    car_target = _number(snapshot.get("car_fund_target"), None)
    brokerage_value = _number(snapshot.get("brokerage_value"), 0.0) or 0.0
    brokerage_contributions = _number(snapshot.get("brokerage_contributions"), 0.0) or 0.0
    checking_balance = _number(snapshot.get("checking_balance"), 0.0) or 0.0
    savings_balance = _number(snapshot.get("savings_balance"), 0.0) or 0.0
    debt_accounts_total = _sum_accounts(snapshot.get("debt_accounts"))
    debt_total = _number(snapshot.get("debt_total"), None)
    if debt_total is None:
        debt_total = debt_accounts_total
    debt_total = debt_total or 0.0
    debt_original_total = _number(snapshot.get("debt_original_total"), None)
    if debt_original_total is None and isinstance(snapshot.get("debt_accounts"), list):
        debt_original_total = sum(
            float(_number(account.get("original_amount", account.get("original_balance", account.get("amount"))), 0.0) or 0.0)
            for account in snapshot["debt_accounts"]
            if isinstance(account, dict)
        )

    assets = checking_balance + savings_balance + emergency_fund + car_fund + brokerage_value
    net_worth = _number(snapshot.get("net_worth"), None)
    if net_worth is None:
        net_worth = assets - debt_total

    monthly_burn = monthly_expenses or 0.0
    liquid_runway_base = checking_balance + savings_balance + emergency_fund
    runway_months = _number(snapshot.get("runway_months"), None)
    if runway_months is None:
        runway_months = None if monthly_burn <= 0 else liquid_runway_base / monthly_burn

    savings_rate = None
    if monthly_income and monthly_income > 0 and monthly_expenses is not None:
        savings_rate = ((monthly_income - monthly_expenses) / monthly_income) * 100.0

    debt_payoff_progress = None
    if debt_original_total and debt_original_total > 0:
        debt_payoff_progress = ((debt_original_total - debt_total) / debt_original_total) * 100.0

    brokerage_growth = None
    if brokerage_contributions > 0:
        brokerage_growth = ((brokerage_value - brokerage_contributions) / brokerage_contributions) * 100.0

    return {
        "annual_income": _round_money(annual_income),
        "monthly_income": _round_money(monthly_income),
        "monthly_expenses": _round_money(monthly_expenses),
        "monthly_burn": _round_money(monthly_burn),
        "net_worth": _round_money(net_worth),
        "runway_months": None if runway_months is None else round(float(runway_months), 2),
        "emergency_fund_completion_percent": _ratio(emergency_fund, emergency_target),
        "car_fund_completion_percent": _ratio(car_fund, car_target),
        "investment_allocation_percent": _ratio(brokerage_value, net_worth if net_worth and net_worth > 0 else None),
        "debt_payoff_progress_percent": None if debt_payoff_progress is None else round(debt_payoff_progress, 2),
        "savings_rate_percent": None if savings_rate is None else round(savings_rate, 2),
        "brokerage_growth_percent": None if brokerage_growth is None else round(brokerage_growth, 2),
        "net_cash_flow": _round_money((monthly_income or 0.0) - (monthly_expenses or 0.0)) if monthly_income is not None and monthly_expenses is not None else None,
    }


def normalize_finance_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    snapshot = dict(data)
    if "monthly_expenses" not in snapshot and "expense_accounts" in snapshot:
        snapshot["monthly_expenses"] = _sum_accounts(snapshot.get("expense_accounts"))
    if "monthly_income" not in snapshot and snapshot.get("annual_income") is not None:
        snapshot["monthly_income"] = (_number(snapshot.get("annual_income"), 0.0) or 0.0) / 12.0
    if not isinstance(snapshot.get("debt_accounts"), list):
        snapshot["debt_accounts"] = []
    metrics = calculate_finance_metrics(snapshot)
    snapshot.update({key: value for key, value in metrics.items() if key in MONEY_FIELDS})
    snapshot["metrics"] = metrics
    return snapshot


def insert_finance_snapshot(data: dict[str, Any], *, captured_at: int | None = None, path: Path | None = None) -> dict[str, Any]:
    captured = int(captured_at or time.time())
    snapshot = normalize_finance_snapshot(data)
    conn = _connect(path)
    try:
        ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO finance_snapshots (
                captured_at, annual_income, monthly_income, monthly_expenses,
                emergency_fund, emergency_fund_target, car_fund, car_fund_target,
                brokerage_value, brokerage_contributions, checking_balance,
                savings_balance, debt_total, debt_accounts, debt_original_total,
                net_worth, runway_months, savings_rate_percent,
                debt_payoff_progress_percent, brokerage_growth_percent, net_cash_flow, payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                captured,
                snapshot.get("annual_income"),
                snapshot.get("monthly_income"),
                snapshot.get("monthly_expenses"),
                snapshot.get("emergency_fund"),
                snapshot.get("emergency_fund_target"),
                snapshot.get("car_fund"),
                snapshot.get("car_fund_target"),
                snapshot.get("brokerage_value"),
                snapshot.get("brokerage_contributions"),
                snapshot.get("checking_balance"),
                snapshot.get("savings_balance"),
                snapshot.get("debt_total"),
                json.dumps(snapshot.get("debt_accounts") or []),
                snapshot.get("debt_original_total"),
                snapshot.get("net_worth"),
                snapshot.get("runway_months"),
                snapshot.get("savings_rate_percent"),
                snapshot.get("debt_payoff_progress_percent"),
                snapshot.get("brokerage_growth_percent"),
                snapshot.get("net_cash_flow"),
                json.dumps(snapshot, sort_keys=True),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"captured_at": captured, **snapshot}


def seed_default_finance_registry(*, path: Path | None = None) -> dict[str, Any]:
    return insert_finance_snapshot(DEFAULT_SEED, path=path)


def _row_to_snapshot(row: sqlite3.Row) -> dict[str, Any]:
    payload = json.loads(row["payload"] or "{}")
    payload["captured_at"] = int(row["captured_at"])
    payload["id"] = int(row["id"])
    # Keep indexed values authoritative if payload is from an older schema.
    for field in MONEY_FIELDS:
        if field in row.keys():
            payload[field] = row[field]
    try:
        payload["debt_accounts"] = json.loads(row["debt_accounts"] or "[]")
    except json.JSONDecodeError:
        payload["debt_accounts"] = []
    payload["metrics"] = calculate_finance_metrics(payload)
    return payload


def latest_finance_snapshot(*, path: Path | None = None) -> FinanceSourceState:
    db_path = path or finance_registry_path()
    if not db_path.exists():
        return FinanceSourceState(False, db_path, None)
    conn = _connect(db_path)
    try:
        ensure_schema(conn)
        if not _table_exists(conn):
            return FinanceSourceState(False, db_path, None)
        row = conn.execute(
            "SELECT * FROM finance_snapshots ORDER BY captured_at DESC, id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return FinanceSourceState(False, db_path, None)
        return FinanceSourceState(True, db_path, _row_to_snapshot(row))
    finally:
        conn.close()


def finance_history(metric: str, *, limit: int = 90, path: Path | None = None) -> list[dict[str, Any]]:
    if metric not in TREND_METRICS:
        raise ValueError(f"Unsupported finance trend metric: {metric}")
    state = latest_finance_snapshot(path=path)
    if not state.initialized:
        return []
    conn = _connect(state.path)
    try:
        rows = conn.execute(
            f"SELECT id, captured_at, {metric}, payload FROM finance_snapshots ORDER BY captured_at DESC, id DESC LIMIT ?",
            (max(1, min(int(limit or 90), 3650)),),
        ).fetchall()
    finally:
        conn.close()
    points: list[dict[str, Any]] = []
    for row in reversed(rows):
        value = row[metric]
        if value is None:
            payload = json.loads(row["payload"] or "{}")
            value = calculate_finance_metrics(payload).get(metric)
        points.append({"captured_at": int(row["captured_at"]), "value": value})
    return points


def _metric_detail(snapshot: dict[str, Any], key: str) -> str | None:
    metrics = snapshot.get("metrics") or {}
    if key == "emergency_fund":
        pct = metrics.get("emergency_fund_completion_percent")
        target = snapshot.get("emergency_fund_target")
        return None if pct is None else f"{pct:.0f}% of ${target:,.0f} target"
    if key == "car_fund":
        pct = metrics.get("car_fund_completion_percent")
        target = snapshot.get("car_fund_target")
        return None if pct is None else f"{pct:.0f}% of ${target:,.0f} target"
    if key == "brokerage":
        allocation = metrics.get("investment_allocation_percent")
        return None if allocation is None else f"{allocation:.0f}% of net worth"
    if key == "runway":
        return "Liquid assets / monthly burn"
    if key == "debt":
        payoff = metrics.get("debt_payoff_progress_percent")
        return "No debt accounts registered" if payoff is None else f"{payoff:.0f}% paid off"
    if key == "savings_rate":
        return "Monthly income minus expenses"
    return None


def finance_widgets_from_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = snapshot.get("metrics") or calculate_finance_metrics(snapshot)
    values = {
        "net_worth": metrics.get("net_worth"),
        "emergency_fund": snapshot.get("emergency_fund"),
        "car_fund": snapshot.get("car_fund"),
        "brokerage": snapshot.get("brokerage_value"),
        "monthly_income": metrics.get("monthly_income"),
        "monthly_expenses": metrics.get("monthly_expenses"),
        "runway": metrics.get("runway_months"),
        "debt": snapshot.get("debt_total"),
        "savings_rate": metrics.get("savings_rate_percent"),
    }
    widgets = []
    for key, label, unit in WIDGET_ORDER:
        widgets.append(
            {
                "key": key,
                "label": label,
                "value": values.get(key),
                "unit": unit,
                "detail": _metric_detail(snapshot, key),
                "source": "finance_registry",
            }
        )
    return widgets


def finance_empty_contract() -> dict[str, Any]:
    return {
        "initialized": False,
        "status": "uninitialized",
        "empty_message": FINANCE_EMPTY_MESSAGE,
        "setup_action": FINANCE_SETUP_ACTION,
        "source": {"type": "finance_registry", "configured": False, "path": str(finance_registry_path())},
        "widgets": [
            {"key": key, "label": label, "value": FINANCE_EMPTY_MESSAGE, "unit": unit, "detail": "Use setup action to initialize source.", "source": "finance_registry"}
            for key, label, unit in WIDGET_ORDER
        ],
        "metrics": {},
        "snapshot": None,
    }


def finance_command_center_contract(*, path: Path | None = None) -> dict[str, Any]:
    state = latest_finance_snapshot(path=path)
    if not state.initialized or not state.latest:
        contract = finance_empty_contract()
        contract["source"]["path"] = str(state.path)
        return contract
    snapshot = state.latest
    return {
        "initialized": True,
        "status": "available",
        "empty_message": None,
        "setup_action": None,
        "source": {"type": "finance_registry", "configured": True, "path": str(state.path), "captured_at": snapshot.get("captured_at")},
        "widgets": finance_widgets_from_snapshot(snapshot),
        "metrics": snapshot.get("metrics") or calculate_finance_metrics(snapshot),
        "snapshot": snapshot,
    }


def dashboard_financial_metrics(*, ai_usage_cost_usd: dict[str, Any] | None = None) -> dict[str, Any]:
    contract = finance_command_center_contract()
    if not contract["initialized"]:
        seed_default_finance_registry()
        contract = finance_command_center_contract()
    if not contract["initialized"]:
        return {
            "metrics": [
                {"label": widget["label"], "value": FINANCE_EMPTY_MESSAGE, "detail": widget.get("detail"), "source": "finance_registry"}
                for widget in contract["widgets"]
            ],
            "widgets": contract["widgets"],
            "finance_command_center": contract,
            "ai_usage_cost_usd": ai_usage_cost_usd or {"estimated": 0, "actual": 0},
            "revenue_usd": None,
            "burn_usd": None,
            "notes": [FINANCE_EMPTY_MESSAGE],
            "source": contract["source"],
            "setup_action": FINANCE_SETUP_ACTION,
        }
    metrics = contract["metrics"]
    widgets = contract["widgets"]
    return {
        "metrics": [
            {"label": widget["label"], "value": widget["value"], "detail": widget.get("detail"), "source": widget.get("source")}
            for widget in widgets
        ],
        "widgets": widgets,
        "finance_command_center": contract,
        "ai_usage_cost_usd": ai_usage_cost_usd or {"estimated": 0, "actual": 0},
        "revenue_usd": metrics.get("monthly_income"),
        "burn_usd": metrics.get("monthly_burn"),
        "notes": ["Finance metrics are calculated from the finance registry snapshot."],
        "source": contract["source"],
        "setup_action": None,
    }


__all__ = [
    "DEFAULT_SEED",
    "FINANCE_EMPTY_MESSAGE",
    "TREND_METRICS",
    "calculate_finance_metrics",
    "dashboard_financial_metrics",
    "finance_command_center_contract",
    "finance_history",
    "finance_registry_path",
    "insert_finance_snapshot",
    "seed_default_finance_registry",
]


# ---------------------------------------------------------------------------
# Normalized Finance Registry schema and metrics (Plaid/read-only ready)
# ---------------------------------------------------------------------------

NORMALIZED_FINANCE_MIGRATIONS: tuple[tuple[str, str], ...] = (
    (
        "001_normalized_finance_registry",
        """
        CREATE TABLE IF NOT EXISTS finance_registry_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration_id TEXT NOT NULL UNIQUE,
            applied_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS finance_institutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL DEFAULT 'plaid',
            institution_id TEXT NOT NULL,
            institution_name TEXT,
            item_id TEXT,
            encrypted_access_token TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            products TEXT NOT NULL DEFAULT '[]',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            last_sync_at INTEGER,
            UNIQUE(provider, institution_id)
        );
        CREATE TABLE IF NOT EXISTS finance_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL DEFAULT 'plaid',
            provider_account_id TEXT NOT NULL,
            institution_id TEXT,
            account_name TEXT,
            account_type TEXT,
            account_subtype TEXT,
            account_mask TEXT,
            current_balance REAL,
            available_balance REAL,
            iso_currency_code TEXT,
            fund_category TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            UNIQUE(provider, provider_account_id)
        );
        CREATE TABLE IF NOT EXISTS finance_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL DEFAULT 'plaid',
            transaction_id TEXT NOT NULL,
            provider_account_id TEXT NOT NULL,
            transaction_date TEXT NOT NULL,
            merchant_name TEXT,
            name TEXT,
            amount REAL NOT NULL,
            category TEXT,
            pending_status INTEGER NOT NULL DEFAULT 0,
            iso_currency_code TEXT,
            raw_hash TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            UNIQUE(provider, transaction_id)
        );
        CREATE TABLE IF NOT EXISTS finance_balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL DEFAULT 'plaid',
            provider_account_id TEXT NOT NULL,
            captured_at INTEGER NOT NULL,
            current_balance REAL,
            available_balance REAL,
            iso_currency_code TEXT,
            sync_run_id INTEGER,
            UNIQUE(provider, provider_account_id, captured_at)
        );
        CREATE TABLE IF NOT EXISTS finance_liabilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL DEFAULT 'plaid',
            provider_account_id TEXT NOT NULL,
            liability_type TEXT,
            loan_balance REAL,
            credit_card_balance REAL,
            apr_percent REAL,
            minimum_payment_amount REAL,
            next_payment_due_date TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            UNIQUE(provider, provider_account_id)
        );
        CREATE TABLE IF NOT EXISTS finance_investments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL DEFAULT 'plaid',
            provider_account_id TEXT NOT NULL,
            security_id TEXT,
            ticker_symbol TEXT,
            security_name TEXT,
            quantity REAL,
            price REAL,
            investment_holdings REAL,
            iso_currency_code TEXT,
            captured_at INTEGER NOT NULL,
            sync_run_id INTEGER,
            UNIQUE(provider, provider_account_id, security_id, captured_at)
        );
        CREATE TABLE IF NOT EXISTS finance_sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL DEFAULT 'plaid',
            environment TEXT NOT NULL DEFAULT 'sandbox',
            started_at INTEGER NOT NULL,
            completed_at INTEGER,
            status TEXT NOT NULL,
            accounts_count INTEGER NOT NULL DEFAULT 0,
            transactions_count INTEGER NOT NULL DEFAULT 0,
            liabilities_count INTEGER NOT NULL DEFAULT 0,
            investments_count INTEGER NOT NULL DEFAULT 0,
            message TEXT
        );
        CREATE TABLE IF NOT EXISTS finance_sync_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_run_id INTEGER,
            provider TEXT NOT NULL DEFAULT 'plaid',
            error_type TEXT NOT NULL,
            error_message TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        """,
    ),
)


def _apply_normalized_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS finance_registry_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration_id TEXT NOT NULL UNIQUE,
            applied_at INTEGER NOT NULL
        )
        """
    )
    applied = {
        row["migration_id"]
        for row in conn.execute("SELECT migration_id FROM finance_registry_migrations").fetchall()
    }
    now = int(time.time())
    for migration_id, sql in NORMALIZED_FINANCE_MIGRATIONS:
        conn.executescript(sql)
        if migration_id not in applied:
            conn.execute(
                "INSERT OR IGNORE INTO finance_registry_migrations (migration_id, applied_at) VALUES (?, ?)",
                (migration_id, now),
            )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_finance_accounts_provider_account ON finance_accounts(provider, provider_account_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_finance_transactions_date ON finance_transactions(transaction_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_finance_balances_account_time ON finance_balances(provider_account_id, captured_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_finance_sync_runs_started ON finance_sync_runs(started_at)")


def ensure_schema(conn: sqlite3.Connection) -> None:  # type: ignore[no-redef]
    """Ensure legacy snapshot storage plus normalized finance tables exist.

    This preserves all existing ``finance_snapshots`` rows and adds normalized
    tables used by read-only Plaid ingestion. The function is intentionally
    idempotent so old registries can be opened by newer Hermes versions.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS finance_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            captured_at INTEGER NOT NULL,
            annual_income REAL,
            monthly_income REAL,
            monthly_expenses REAL,
            emergency_fund REAL,
            emergency_fund_target REAL,
            car_fund REAL,
            car_fund_target REAL,
            brokerage_value REAL,
            brokerage_contributions REAL,
            checking_balance REAL,
            savings_balance REAL,
            debt_total REAL,
            debt_accounts TEXT NOT NULL DEFAULT '[]',
            debt_original_total REAL,
            net_worth REAL,
            runway_months REAL,
            savings_rate_percent REAL,
            debt_payoff_progress_percent REAL,
            brokerage_growth_percent REAL,
            net_cash_flow REAL,
            payload TEXT NOT NULL
        )
        """
    )
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(finance_snapshots)").fetchall()}
    for column in ("savings_rate_percent", "debt_payoff_progress_percent", "brokerage_growth_percent", "net_cash_flow"):
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE finance_snapshots ADD COLUMN {column} REAL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_finance_snapshots_captured_at ON finance_snapshots(captured_at)")
    _apply_normalized_migrations(conn)
    conn.commit()


def start_finance_sync_run(*, provider: str = "plaid", environment: str = "sandbox", path: Path | None = None) -> int:
    conn = _connect(path)
    try:
        ensure_schema(conn)
        cur = conn.execute(
            "INSERT INTO finance_sync_runs (provider, environment, started_at, status) VALUES (?, ?, ?, ?)",
            (provider, environment, int(time.time()), "running"),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def finish_finance_sync_run(sync_run_id: int, *, status: str, message: str | None = None, counts: dict[str, int] | None = None, path: Path | None = None) -> None:
    counts = counts or {}
    conn = _connect(path)
    try:
        ensure_schema(conn)
        conn.execute(
            """
            UPDATE finance_sync_runs
            SET completed_at = ?, status = ?, accounts_count = ?, transactions_count = ?, liabilities_count = ?, investments_count = ?, message = ?
            WHERE id = ?
            """,
            (
                int(time.time()), status,
                int(counts.get("accounts", 0)), int(counts.get("transactions", 0)),
                int(counts.get("liabilities", 0)), int(counts.get("investments", 0)),
                message, int(sync_run_id),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def record_finance_sync_error(sync_run_id: int | None, error_type: str, error_message: str, *, provider: str = "plaid", path: Path | None = None) -> None:
    sanitized = str(error_message).replace(os.environ.get("PLAID_SECRET", "__no_secret__"), "[REDACTED]")
    conn = _connect(path)
    try:
        ensure_schema(conn)
        conn.execute(
            "INSERT INTO finance_sync_errors (sync_run_id, provider, error_type, error_message, created_at) VALUES (?, ?, ?, ?, ?)",
            (sync_run_id, provider, error_type, sanitized[:1000], int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def latest_finance_sync_status(*, path: Path | None = None) -> dict[str, Any]:
    conn = _connect(path)
    try:
        ensure_schema(conn)
        run = conn.execute("SELECT * FROM finance_sync_runs ORDER BY started_at DESC, id DESC LIMIT 1").fetchone()
        errors = conn.execute("SELECT error_type, error_message, created_at FROM finance_sync_errors ORDER BY created_at DESC, id DESC LIMIT 5").fetchall()
        if run is None:
            return {"configured": False, "last_sync_at": None, "sync_health": "never_synced", "errors": []}
        status = run["status"]
        health = "healthy" if status == "success" else ("running" if status == "running" else "degraded")
        return {
            "configured": True,
            "provider": run["provider"],
            "environment": run["environment"],
            "status": status,
            "sync_health": health,
            "last_sync_at": run["completed_at"] or run["started_at"],
            "started_at": run["started_at"],
            "completed_at": run["completed_at"],
            "accounts_count": run["accounts_count"],
            "transactions_count": run["transactions_count"],
            "liabilities_count": run["liabilities_count"],
            "investments_count": run["investments_count"],
            "message": run["message"],
            "errors": [dict(row) for row in errors],
        }
    finally:
        conn.close()


def upsert_plaid_registry_data(data: dict[str, Any], *, sync_run_id: int | None = None, path: Path | None = None) -> dict[str, int]:
    """Upsert sanitized, read-only Plaid data into normalized registry tables.

    The caller must pass only safe Plaid fields. This function stores account
    masks but never full account/routing numbers, usernames, passwords, SSNs,
    or raw provider payloads.
    """
    now = int(time.time())
    counts = {"institutions": 0, "accounts": 0, "transactions": 0, "balances": 0, "liabilities": 0, "investments": 0}
    conn = _connect(path)
    try:
        ensure_schema(conn)
        institution = data.get("institution") or {}
        if institution.get("institution_id"):
            conn.execute(
                """
                INSERT INTO finance_institutions (provider, institution_id, institution_name, item_id, status, products, created_at, updated_at, last_sync_at)
                VALUES ('plaid', ?, ?, ?, 'active', ?, ?, ?, ?)
                ON CONFLICT(provider, institution_id) DO UPDATE SET
                    institution_name=excluded.institution_name,
                    item_id=COALESCE(excluded.item_id, finance_institutions.item_id),
                    updated_at=excluded.updated_at,
                    last_sync_at=excluded.last_sync_at
                """,
                (institution.get("institution_id"), institution.get("name"), institution.get("item_id"), json.dumps(data.get("products") or []), now, now, now),
            )
            counts["institutions"] += 1
        for account in data.get("accounts") or []:
            account_id = account.get("account_id")
            if not account_id:
                continue
            balances = account.get("balances") or {}
            conn.execute(
                """
                INSERT INTO finance_accounts (provider, provider_account_id, institution_id, account_name, account_type, account_subtype, account_mask, current_balance, available_balance, iso_currency_code, fund_category, created_at, updated_at)
                VALUES ('plaid', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, provider_account_id) DO UPDATE SET
                    institution_id=excluded.institution_id,
                    account_name=excluded.account_name,
                    account_type=excluded.account_type,
                    account_subtype=excluded.account_subtype,
                    account_mask=excluded.account_mask,
                    current_balance=excluded.current_balance,
                    available_balance=excluded.available_balance,
                    iso_currency_code=excluded.iso_currency_code,
                    fund_category=COALESCE(finance_accounts.fund_category, excluded.fund_category),
                    updated_at=excluded.updated_at,
                    is_active=1
                """,
                (
                    account_id, institution.get("institution_id"), account.get("name"), account.get("type"),
                    account.get("subtype"), account.get("mask"), _number(balances.get("current"), None),
                    _number(balances.get("available"), None), balances.get("iso_currency_code") or account.get("iso_currency_code"),
                    account.get("fund_category"), now, now,
                ),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO finance_balances (provider, provider_account_id, captured_at, current_balance, available_balance, iso_currency_code, sync_run_id)
                VALUES ('plaid', ?, ?, ?, ?, ?, ?)
                """,
                (account_id, now, _number(balances.get("current"), None), _number(balances.get("available"), None), balances.get("iso_currency_code") or account.get("iso_currency_code"), sync_run_id),
            )
            counts["accounts"] += 1
            counts["balances"] += 1
        for txn in data.get("transactions") or []:
            transaction_id = txn.get("transaction_id")
            account_id = txn.get("account_id")
            if not transaction_id or not account_id:
                continue
            category = txn.get("category")
            if isinstance(category, list):
                category = ":".join(str(part) for part in category if part)
            personal = txn.get("personal_finance_category") or {}
            if not category and isinstance(personal, dict):
                category = personal.get("primary") or personal.get("detailed")
            safe_hash_src = json.dumps({k: txn.get(k) for k in ("transaction_id", "account_id", "date", "amount", "name", "merchant_name", "pending")}, sort_keys=True)
            import hashlib
            conn.execute(
                """
                INSERT INTO finance_transactions (provider, transaction_id, provider_account_id, transaction_date, merchant_name, name, amount, category, pending_status, iso_currency_code, raw_hash, created_at, updated_at)
                VALUES ('plaid', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, transaction_id) DO UPDATE SET
                    provider_account_id=excluded.provider_account_id,
                    transaction_date=excluded.transaction_date,
                    merchant_name=excluded.merchant_name,
                    name=excluded.name,
                    amount=excluded.amount,
                    category=excluded.category,
                    pending_status=excluded.pending_status,
                    iso_currency_code=excluded.iso_currency_code,
                    raw_hash=excluded.raw_hash,
                    updated_at=excluded.updated_at
                """,
                (
                    transaction_id, account_id, txn.get("date") or txn.get("authorized_date") or "1970-01-01",
                    txn.get("merchant_name"), txn.get("name"), _number(txn.get("amount"), 0.0) or 0.0,
                    category, 1 if txn.get("pending") else 0, txn.get("iso_currency_code"), hashlib.sha256(safe_hash_src.encode()).hexdigest(), now, now,
                ),
            )
            counts["transactions"] += 1
        liabilities = data.get("liabilities") or {}
        for cc in liabilities.get("credit") or []:
            account_id = cc.get("account_id")
            if not account_id:
                continue
            conn.execute(
                """
                INSERT INTO finance_liabilities (provider, provider_account_id, liability_type, loan_balance, credit_card_balance, apr_percent, minimum_payment_amount, next_payment_due_date, created_at, updated_at)
                VALUES ('plaid', ?, 'credit_card', NULL, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, provider_account_id) DO UPDATE SET
                    credit_card_balance=excluded.credit_card_balance,
                    apr_percent=excluded.apr_percent,
                    minimum_payment_amount=excluded.minimum_payment_amount,
                    next_payment_due_date=excluded.next_payment_due_date,
                    updated_at=excluded.updated_at
                """,
                (account_id, _number(cc.get("last_statement_balance", cc.get("balance")), None), _extract_apr(cc), _number(cc.get("minimum_payment_amount"), None), cc.get("next_payment_due_date"), now, now),
            )
            counts["liabilities"] += 1
        for loan_key in ("student", "mortgage"):
            for loan in liabilities.get(loan_key) or []:
                account_id = loan.get("account_id")
                if not account_id:
                    continue
                balance = loan.get("outstanding_principal_balance") if loan_key == "student" else loan.get("current_late_fee", loan.get("outstanding_principal_balance"))
                conn.execute(
                    """
                    INSERT INTO finance_liabilities (provider, provider_account_id, liability_type, loan_balance, credit_card_balance, apr_percent, minimum_payment_amount, next_payment_due_date, created_at, updated_at)
                    VALUES ('plaid', ?, ?, ?, NULL, ?, ?, ?, ?, ?)
                    ON CONFLICT(provider, provider_account_id) DO UPDATE SET
                        liability_type=excluded.liability_type,
                        loan_balance=excluded.loan_balance,
                        apr_percent=excluded.apr_percent,
                        minimum_payment_amount=excluded.minimum_payment_amount,
                        next_payment_due_date=excluded.next_payment_due_date,
                        updated_at=excluded.updated_at
                    """,
                    (account_id, loan_key, _number(balance, None), _extract_apr(loan), _number(loan.get("minimum_payment_amount"), None), loan.get("next_payment_due_date"), now, now),
                )
                counts["liabilities"] += 1
        securities = {s.get("security_id"): s for s in (data.get("securities") or []) if s.get("security_id")}
        for holding in data.get("holdings") or data.get("investment_holdings") or []:
            account_id = holding.get("account_id")
            security_id = holding.get("security_id") or "cash"
            if not account_id:
                continue
            sec = securities.get(security_id, {})
            quantity = _number(holding.get("quantity"), 0.0) or 0.0
            price = _number(holding.get("institution_price"), _number(holding.get("price"), 0.0)) or 0.0
            value = _number(holding.get("institution_value"), quantity * price) or 0.0
            conn.execute(
                """
                INSERT OR IGNORE INTO finance_investments (provider, provider_account_id, security_id, ticker_symbol, security_name, quantity, price, investment_holdings, iso_currency_code, captured_at, sync_run_id)
                VALUES ('plaid', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (account_id, security_id, sec.get("ticker_symbol"), sec.get("name"), quantity, price, value, holding.get("iso_currency_code") or sec.get("iso_currency_code"), now, sync_run_id),
            )
            counts["investments"] += 1
        conn.commit()
        return counts
    finally:
        conn.close()


def _extract_apr(record: dict[str, Any]) -> float | None:
    aprs = record.get("aprs")
    if isinstance(aprs, list) and aprs:
        return _number(aprs[0].get("apr_percentage"), None)
    return _number(record.get("apr_percent"), None)


def _has_normalized_finance_data(conn: sqlite3.Connection) -> bool:
    try:
        row = conn.execute("SELECT COUNT(*) AS count FROM finance_accounts").fetchone()
        return bool(row and int(row["count"] or 0) > 0)
    except sqlite3.Error:
        return False


def normalized_finance_snapshot(*, path: Path | None = None) -> dict[str, Any] | None:
    conn = _connect(path)
    try:
        ensure_schema(conn)
        if not _has_normalized_finance_data(conn):
            return None
        accounts = conn.execute("SELECT * FROM finance_accounts WHERE is_active = 1").fetchall()
        txns = conn.execute("SELECT * FROM finance_transactions WHERE pending_status = 0").fetchall()
        liabilities = conn.execute("SELECT * FROM finance_liabilities").fetchall()
        holdings_row = conn.execute("SELECT COALESCE(SUM(investment_holdings), 0) AS value FROM finance_investments WHERE captured_at = (SELECT MAX(captured_at) FROM finance_investments)").fetchone()
        cash_position = 0.0
        checking = 0.0
        savings = 0.0
        emergency = 0.0
        car = 0.0
        investment_accounts = 0.0
        credit_loan_accounts = 0.0
        for row in accounts:
            balance = float(row["current_balance"] or 0.0)
            atype = row["account_type"]
            subtype = row["account_subtype"]
            fund = row["fund_category"]
            if atype == "depository":
                cash_position += balance
                if subtype == "checking":
                    checking += balance
                elif subtype == "savings":
                    savings += balance
                if fund == "emergency":
                    emergency += balance
                elif fund == "car":
                    car += balance
            elif atype == "investment":
                investment_accounts += balance
            elif atype in {"credit", "loan"}:
                credit_loan_accounts += abs(balance)
        holdings_value = float(holdings_row["value"] or 0.0) if holdings_row is not None else 0.0
        brokerage_value = holdings_value if holdings_value > 0 else investment_accounts
        explicit_debt = 0.0
        for row in liabilities:
            explicit_debt += abs(float(row["loan_balance"] or row["credit_card_balance"] or 0.0))
        debt_total = explicit_debt if explicit_debt > 0 else credit_loan_accounts
        import datetime as _dt
        cutoff = (_dt.date.today() - _dt.timedelta(days=30)).isoformat()
        income = 0.0
        spending = 0.0
        for row in txns:
            if str(row["transaction_date"]) < cutoff:
                continue
            amount = float(row["amount"] or 0.0)
            # Plaid transaction amounts are positive for outflows and negative for inflows.
            if amount < 0:
                income += abs(amount)
            elif amount > 0:
                spending += amount
        latest_sync = latest_finance_sync_status(path=path)
        snapshot = {
            "snapshot_source": "normalized_registry",
            "annual_income": round(income * 12.0, 2) if income else None,
            "monthly_income": round(income, 2),
            "monthly_expenses": round(spending, 2),
            "emergency_fund": round(emergency, 2),
            "emergency_fund_target": 1000.0,
            "car_fund": round(car, 2),
            "car_fund_target": 5000.0,
            "brokerage_value": round(brokerage_value, 2),
            "brokerage_contributions": 0.0,
            "checking_balance": round(checking, 2),
            "savings_balance": round(savings, 2),
            "cash_position": round(cash_position, 2),
            "debt_total": round(debt_total, 2),
            "debt_accounts": [],
            "debt_original_total": debt_total,
            "last_finance_sync": latest_sync.get("last_sync_at"),
            "sync_health": latest_sync.get("sync_health"),
        }
        snapshot = normalize_finance_snapshot(snapshot)
        snapshot["metrics"]["cash_position"] = snapshot["cash_position"]
        snapshot["metrics"]["total_debt"] = snapshot["debt_total"]
        snapshot["metrics"]["monthly_spending"] = snapshot["monthly_expenses"]
        snapshot["metrics"]["brokerage_value"] = snapshot["brokerage_value"]
        snapshot["metrics"]["last_finance_sync"] = snapshot["last_finance_sync"]
        snapshot["metrics"]["sync_health"] = snapshot["sync_health"]
        return snapshot
    finally:
        conn.close()


def finance_widgets_from_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:  # type: ignore[no-redef]
    metrics = snapshot.get("metrics") or calculate_finance_metrics(snapshot)
    values = {
        "net_worth": metrics.get("net_worth"),
        "cash_position": metrics.get("cash_position", snapshot.get("cash_position")),
        "emergency_fund": snapshot.get("emergency_fund"),
        "car_fund": snapshot.get("car_fund"),
        "brokerage": snapshot.get("brokerage_value"),
        "monthly_income": metrics.get("monthly_income"),
        "monthly_expenses": metrics.get("monthly_expenses"),
        "monthly_spending": metrics.get("monthly_spending", metrics.get("monthly_expenses")),
        "runway": metrics.get("runway_months"),
        "debt": snapshot.get("debt_total"),
        "total_debt": metrics.get("total_debt", snapshot.get("debt_total")),
        "savings_rate": metrics.get("savings_rate_percent"),
        "last_finance_sync": metrics.get("last_finance_sync", snapshot.get("last_finance_sync")),
        "sync_health": metrics.get("sync_health", snapshot.get("sync_health")),
    }
    order = list(WIDGET_ORDER) + [
        ("cash_position", "Cash Position", "currency"),
        ("total_debt", "Total Debt", "currency"),
        ("monthly_spending", "Monthly Spending", "currency"),
        ("last_finance_sync", "Last Finance Sync", "timestamp"),
        ("sync_health", "Sync Health", "status"),
    ]
    seen: set[str] = set()
    widgets = []
    for key, label, unit in order:
        if key in seen:
            continue
        seen.add(key)
        widgets.append({"key": key, "label": label, "value": values.get(key), "unit": unit, "detail": _metric_detail(snapshot, key), "source": "finance_registry"})
    return widgets


def finance_command_center_contract(*, path: Path | None = None) -> dict[str, Any]:  # type: ignore[no-redef]
    normalized = normalized_finance_snapshot(path=path)
    if normalized is not None:
        db_path = path or finance_registry_path()
        sync = latest_finance_sync_status(path=path)
        return {
            "initialized": True,
            "status": "available",
            "empty_message": None,
            "setup_action": None,
            "source": {"type": "finance_registry", "configured": True, "path": str(db_path), "captured_at": int(time.time()), "model": "normalized", "last_finance_sync": sync.get("last_sync_at"), "sync_health": sync.get("sync_health")},
            "widgets": finance_widgets_from_snapshot(normalized),
            "metrics": normalized.get("metrics") or calculate_finance_metrics(normalized),
            "snapshot": normalized,
            "sync": sync,
        }
    state = latest_finance_snapshot(path=path)
    if not state.initialized or not state.latest:
        contract = finance_empty_contract()
        contract["source"]["path"] = str(state.path)
        return contract
    snapshot = state.latest
    return {
        "initialized": True,
        "status": "available",
        "empty_message": None,
        "setup_action": None,
        "source": {"type": "finance_registry", "configured": True, "path": str(state.path), "captured_at": snapshot.get("captured_at"), "model": "snapshot"},
        "widgets": finance_widgets_from_snapshot(snapshot),
        "metrics": snapshot.get("metrics") or calculate_finance_metrics(snapshot),
        "snapshot": snapshot,
        "sync": latest_finance_sync_status(path=path),
    }


def dashboard_financial_metrics(*, ai_usage_cost_usd: dict[str, Any] | None = None) -> dict[str, Any]:  # type: ignore[no-redef]
    contract = finance_command_center_contract()
    if not contract["initialized"]:
        seed_default_finance_registry()
        contract = finance_command_center_contract()
    if not contract["initialized"]:
        return {
            "metrics": [{"label": widget["label"], "value": FINANCE_EMPTY_MESSAGE, "detail": widget.get("detail"), "source": "finance_registry"} for widget in contract["widgets"]],
            "widgets": contract["widgets"],
            "finance_command_center": contract,
            "ai_usage_cost_usd": ai_usage_cost_usd or {"estimated": 0, "actual": 0},
            "revenue_usd": None,
            "burn_usd": None,
            "notes": [FINANCE_EMPTY_MESSAGE],
            "source": contract["source"],
            "setup_action": FINANCE_SETUP_ACTION,
        }
    metrics = contract["metrics"]
    widgets = contract["widgets"]
    return {
        "metrics": [{"label": widget["label"], "value": widget["value"], "detail": widget.get("detail"), "source": widget.get("source")} for widget in widgets],
        "widgets": widgets,
        "finance_command_center": contract,
        "ai_usage_cost_usd": ai_usage_cost_usd or {"estimated": 0, "actual": 0},
        "revenue_usd": metrics.get("monthly_income"),
        "burn_usd": metrics.get("monthly_burn"),
        "notes": ["Finance metrics are calculated from the normalized finance registry when available; Plaid is never queried by the dashboard."],
        "source": contract["source"],
        "setup_action": None,
        "last_finance_sync": contract.get("sync", {}).get("last_sync_at"),
        "sync_health": contract.get("sync", {}).get("sync_health"),
    }
