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
    try:
        db_path.chmod(0o600)
    except OSError:
        pass
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

    cash_position = _number(snapshot.get("cash_position"), None)
    assets = (cash_position if cash_position is not None else checking_balance + savings_balance + emergency_fund + car_fund) + brokerage_value
    net_worth = _number(snapshot.get("net_worth"), None)
    if net_worth is None:
        net_worth = assets - debt_total

    monthly_burn = monthly_expenses or 0.0
    liquid_runway_base = cash_position if cash_position is not None else checking_balance + savings_balance + emergency_fund
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
    normalized_points = _normalized_history_points(metric, limit=limit, path=path)
    if normalized_points:
        return normalized_points
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
    "configure_finance_sync_schedule",
    "dashboard_financial_metrics",
    "enqueue_finance_sync",
    "finance_command_center_contract",
    "finance_history",
    "finance_registry_path",
    "finance_sync_schedule",
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
        CREATE TABLE IF NOT EXISTS finance_sync_schedule (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            cadence TEXT NOT NULL DEFAULT 'manual',
            enabled INTEGER NOT NULL DEFAULT 0,
            retry_max_attempts INTEGER NOT NULL DEFAULT 3,
            retry_backoff_base_seconds INTEGER NOT NULL DEFAULT 60,
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS finance_sync_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL DEFAULT 'plaid',
            institution_id TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            next_attempt_at INTEGER NOT NULL,
            last_error TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
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


def _sanitize_finance_error_message(error_message: str) -> str:
    sanitized = str(error_message)
    for env_key in ("PLAID_SECRET", "PLAID_CLIENT_ID"):
        value = os.environ.get(env_key, "").strip()
        if value:
            sanitized = sanitized.replace(value, "[REDACTED]")
    lowered = sanitized.lower()
    for marker in ("access-", "public-"):
        if marker in lowered:
            # Avoid persisting Plaid token-like substrings; keep the operator-safe class only.
            return "Provider request failed; sensitive token value redacted."
    return sanitized


def record_finance_sync_error(sync_run_id: int | None, error_type: str, error_message: str, *, provider: str = "plaid", path: Path | None = None) -> None:
    sanitized = _sanitize_finance_error_message(error_message)
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


def _sync_duration_seconds(row: sqlite3.Row) -> float | None:
    started = row["started_at"]
    completed = row["completed_at"]
    if not started or not completed:
        return None
    return round(max(0, int(completed) - int(started)), 2)


def _sync_health(status: str | None, *, completed_at: int | None = None) -> str:
    normalized = (status or "").lower()
    if normalized == "success":
        if completed_at and int(time.time()) - int(completed_at) > 86400:
            return "warning"
        return "healthy"
    if normalized == "running":
        return "warning"
    if normalized in {"failed", "error"}:
        return "error"
    return "warning"


def recent_finance_sync_runs(*, limit: int = 10, path: Path | None = None) -> list[dict[str, Any]]:
    conn = _connect(path)
    try:
        ensure_schema(conn)
        rows = conn.execute(
            "SELECT * FROM finance_sync_runs ORDER BY started_at DESC, id DESC LIMIT ?",
            (max(1, min(int(limit or 10), 50)),),
        ).fetchall()
        errors = conn.execute(
            "SELECT sync_run_id, error_type, error_message FROM finance_sync_errors ORDER BY created_at DESC, id DESC"
        ).fetchall()
        errors_by_run: dict[int, list[str]] = {}
        for error_row in errors:
            run_id = error_row["sync_run_id"]
            if run_id is None:
                continue
            errors_by_run.setdefault(int(run_id), []).append(str(error_row["error_message"]))
        return [
            {
                "id": row["id"],
                "provider": row["provider"],
                "environment": row["environment"],
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "duration_seconds": _sync_duration_seconds(row),
                "accounts_count": row["accounts_count"],
                "transactions_count": row["transactions_count"],
                "liabilities_count": row["liabilities_count"],
                "investments_count": row["investments_count"],
                "status": row["status"],
                "errors": errors_by_run.get(int(row["id"]), []),
            }
            for row in rows
        ]
    finally:
        conn.close()


SYNC_CADENCES: dict[str, int | None] = {
    "manual": None,
    "hourly": 3600,
    "every_6_hours": 21600,
    "every_12_hours": 43200,
    "daily": 86400,
}


def configure_finance_sync_schedule(*, cadence: str = "manual", enabled: bool | None = None, retry_max_attempts: int = 3, retry_backoff_base_seconds: int = 60, path: Path | None = None) -> dict[str, Any]:
    normalized = cadence.strip().lower().replace(" ", "_")
    aliases = {"every_hour": "hourly", "1h": "hourly", "6h": "every_6_hours", "12h": "every_12_hours", "24h": "daily"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in SYNC_CADENCES:
        raise ValueError(f"Unsupported finance sync cadence: {cadence}")
    is_enabled = bool(enabled) if enabled is not None else normalized != "manual"
    now = int(time.time())
    conn = _connect(path)
    try:
        ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO finance_sync_schedule (id, cadence, enabled, retry_max_attempts, retry_backoff_base_seconds, updated_at)
            VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET cadence=excluded.cadence, enabled=excluded.enabled,
                retry_max_attempts=excluded.retry_max_attempts,
                retry_backoff_base_seconds=excluded.retry_backoff_base_seconds,
                updated_at=excluded.updated_at
            """,
            (normalized, 1 if is_enabled else 0, max(1, int(retry_max_attempts)), max(1, int(retry_backoff_base_seconds)), now),
        )
        conn.commit()
    finally:
        conn.close()
    return finance_sync_schedule(path=path)


def finance_sync_schedule(*, path: Path | None = None) -> dict[str, Any]:
    conn = _connect(path)
    try:
        ensure_schema(conn)
        row = conn.execute("SELECT * FROM finance_sync_schedule WHERE id=1").fetchone()
    finally:
        conn.close()
    if row is None:
        return {"cadence": "manual", "enabled": False, "interval_seconds": None, "retry_max_attempts": 3, "retry_backoff_base_seconds": 60}
    cadence = str(row["cadence"] or "manual")
    return {
        "cadence": cadence,
        "enabled": bool(row["enabled"]),
        "interval_seconds": SYNC_CADENCES.get(cadence),
        "retry_max_attempts": int(row["retry_max_attempts"] or 3),
        "retry_backoff_base_seconds": int(row["retry_backoff_base_seconds"] or 60),
        "updated_at": row["updated_at"],
    }


def enqueue_finance_sync(*, institution_id: str | None = None, provider: str = "plaid", path: Path | None = None) -> dict[str, Any]:
    now = int(time.time())
    schedule = finance_sync_schedule(path=path)
    conn = _connect(path)
    try:
        ensure_schema(conn)
        cur = conn.execute(
            "INSERT INTO finance_sync_queue (provider, institution_id, status, attempts, max_attempts, next_attempt_at, created_at, updated_at) VALUES (?, ?, 'queued', 0, ?, ?, ?, ?)",
            (provider, institution_id, int(schedule["retry_max_attempts"]), now, now, now),
        )
        conn.commit()
        return {"id": int(cur.lastrowid or 0), "status": "queued", "next_attempt_at": now, "max_attempts": int(schedule["retry_max_attempts"])}
    finally:
        conn.close()


def latest_finance_sync_status(*, path: Path | None = None) -> dict[str, Any]:
    db_path = path or finance_registry_path()
    conn = _connect(path)
    try:
        ensure_schema(conn)
        run = conn.execute("SELECT * FROM finance_sync_runs ORDER BY started_at DESC, id DESC LIMIT 1").fetchone()
        errors = conn.execute("SELECT error_type, error_message, created_at FROM finance_sync_errors ORDER BY created_at DESC, id DESC LIMIT 5").fetchall()
        base = {
            "registry_source": "Finance Registry",
            "registry_location": str(db_path),
            "model": "Normalized Registry",
            "provider": "Plaid",
            "provider_label": "Plaid Sandbox",
            "environment": "Sandbox",
            "history": recent_finance_sync_runs(limit=10, path=path),
            "schedule": finance_sync_schedule(path=path),
        }
        if run is None:
            return {**base, "configured": False, "last_sync_at": None, "last_successful_sync_at": None, "sync_health": "warning", "status": "never_synced", "errors": []}
        status = run["status"]
        completed = run["completed_at"]
        latest_success = conn.execute("SELECT completed_at FROM finance_sync_runs WHERE status='success' AND completed_at IS NOT NULL ORDER BY completed_at DESC, id DESC LIMIT 1").fetchone()
        environment = str(run["environment"] or "sandbox")
        provider = str(run["provider"] or "plaid")
        display_env = environment.capitalize()
        return {
            **base,
            "configured": True,
            "provider": provider.capitalize() if provider else "Plaid",
            "provider_label": f"Plaid {display_env}" if provider == "plaid" else provider.capitalize(),
            "environment": display_env,
            "status": status,
            "sync_health": _sync_health(status, completed_at=completed),
            "last_sync_at": completed or run["started_at"],
            "last_successful_sync_at": latest_success["completed_at"] if latest_success else None,
            "started_at": run["started_at"],
            "completed_at": completed,
            "duration_seconds": _sync_duration_seconds(run),
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
        current_account_ids: list[str] = []
        for account in data.get("accounts") or []:
            account_id = account.get("account_id")
            if not account_id:
                continue
            current_account_ids.append(str(account_id))
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
        if institution.get("institution_id") and current_account_ids:
            placeholders = ",".join("?" for _ in current_account_ids)
            conn.execute(
                f"UPDATE finance_accounts SET is_active=0, updated_at=? WHERE provider='plaid' AND institution_id=? AND provider_account_id NOT IN ({placeholders})",
                (now, institution.get("institution_id"), *current_account_ids),
            )
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
                balance = loan.get("outstanding_principal_balance") or loan.get("origination_principal_amount") or loan.get("current_balance")
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


def _active_account_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM finance_accounts WHERE is_active = 1").fetchall()


def _latest_investment_value(conn: sqlite3.Connection) -> float:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(investment_holdings), 0) AS value
        FROM finance_investments
        WHERE captured_at = (SELECT MAX(captured_at) FROM finance_investments)
        """
    ).fetchone()
    return float(row["value"] or 0.0) if row is not None else 0.0


def _normalized_cash_bucket(row: sqlite3.Row) -> str | None:
    subtype = str(row["account_subtype"] or "").lower()
    fund = str(row["fund_category"] or "").lower()
    name = str(row["account_name"] or "").lower()
    if fund == "emergency" or "emergency" in name:
        return "emergency"
    if fund == "car" or "car fund" in name:
        return "car"
    if subtype == "checking":
        return "checking"
    if subtype in {"savings", "money market", "cash management", "cd", "hsa"}:
        return "savings"
    return None


def _normalized_liability_total(accounts: list[sqlite3.Row], liabilities: list[sqlite3.Row]) -> float:
    """Return outstanding debt without double-counting liability detail rows.

    Plaid account balances are the most complete normalized source for loans in
    the registry. Liability rows add payment/APR detail and are used only for
    accounts that do not have an active credit/loan account balance.
    """
    account_debt_by_id: dict[str, float] = {}
    for row in accounts:
        if row["account_type"] in {"credit", "loan"}:
            account_debt_by_id[str(row["provider_account_id"])] = abs(float(row["current_balance"] or 0.0))
    extra_detail_debt = 0.0
    for row in liabilities:
        account_id = str(row["provider_account_id"] or "")
        if account_id in account_debt_by_id:
            continue
        extra_detail_debt += abs(float(row["loan_balance"] or row["credit_card_balance"] or 0.0))
    return sum(account_debt_by_id.values()) + extra_detail_debt


def _normalized_credit_utilization(accounts: list[sqlite3.Row]) -> float | None:
    balance = 0.0
    limit = 0.0
    for row in accounts:
        if row["account_type"] != "credit":
            continue
        current = abs(float(row["current_balance"] or 0.0))
        available = float(row["available_balance"] or 0.0)
        balance += current
        limit += current + max(available, 0.0)
    return None if limit <= 0 else round((balance / limit) * 100.0, 2)


def _normalized_monthly_income_expenses(conn: sqlite3.Connection) -> tuple[float, float]:
    import datetime as _dt

    latest = conn.execute("SELECT MAX(transaction_date) AS latest FROM finance_transactions WHERE pending_status = 0").fetchone()
    latest_date = _dt.date.today()
    if latest and latest["latest"]:
        try:
            latest_date = _dt.date.fromisoformat(str(latest["latest"]))
        except ValueError:
            latest_date = _dt.date.today()
    cutoff = (latest_date - _dt.timedelta(days=30)).isoformat()
    row = conn.execute(
        """
        SELECT
          COALESCE(SUM(CASE WHEN amount < 0 AND LOWER(COALESCE(category, '') || ' ' || COALESCE(name, '') || ' ' || COALESCE(merchant_name, '')) NOT LIKE '%transfer%' THEN -amount ELSE 0 END), 0) AS income,
          COALESCE(SUM(CASE WHEN amount > 0 AND LOWER(COALESCE(category, '') || ' ' || COALESCE(name, '') || ' ' || COALESCE(merchant_name, '')) NOT LIKE '%transfer%' THEN amount ELSE 0 END), 0) AS expenses
        FROM finance_transactions
        WHERE pending_status = 0 AND transaction_date >= ?
        """,
        (cutoff,),
    ).fetchone()
    return (round(float(row["income"] or 0.0), 2), round(float(row["expenses"] or 0.0), 2))


def _normalized_finance_aggregate(conn: sqlite3.Connection) -> dict[str, Any]:
    accounts = _active_account_rows(conn)
    liabilities = conn.execute("SELECT * FROM finance_liabilities").fetchall()
    cash_position = checking = savings = emergency = car = 0.0
    investment_accounts = 0.0
    for row in accounts:
        balance = float(row["current_balance"] or 0.0)
        if row["account_type"] == "depository":
            cash_position += balance
            bucket = _normalized_cash_bucket(row)
            if bucket == "checking":
                checking += balance
            elif bucket == "emergency":
                emergency += balance
                savings += balance
            elif bucket == "car":
                car += balance
                savings += balance
            elif bucket == "savings":
                savings += balance
        elif row["account_type"] == "investment":
            investment_accounts += balance
    brokerage_value = _latest_investment_value(conn) or investment_accounts
    debt_total = _normalized_liability_total(accounts, liabilities)
    income, expenses = _normalized_monthly_income_expenses(conn)
    net_worth = cash_position + brokerage_value - debt_total
    credit_utilization = _normalized_credit_utilization(accounts)
    return {
        "annual_income": round(income * 12.0, 2) if income else None,
        "monthly_income": income,
        "monthly_expenses": expenses,
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
        "debt_original_total": round(debt_total, 2),
        "net_worth": round(net_worth, 2),
        "last_finance_sync": None,
        "sync_health": None,
        "credit_utilization_percent": credit_utilization,
    }


def _normalized_history_points(metric: str, *, limit: int, path: Path | None = None) -> list[dict[str, Any]]:
    if metric not in TREND_METRICS:
        raise ValueError(f"Unsupported finance trend metric: {metric}")
    conn = _connect(path)
    try:
        ensure_schema(conn)
        if not _has_normalized_finance_data(conn):
            return []
        rows = conn.execute(
            """
            SELECT b.sync_run_id, COALESCE(sr.completed_at, MAX(b.captured_at)) AS captured_at,
                   SUM(CASE WHEN a.account_type='depository' THEN b.current_balance ELSE 0 END) AS cash_position,
                   SUM(CASE WHEN a.account_type IN ('credit','loan') THEN ABS(b.current_balance) ELSE 0 END) AS debt_total
            FROM finance_balances b
            JOIN finance_accounts a ON a.provider_account_id = b.provider_account_id
            LEFT JOIN finance_sync_runs sr ON sr.id = b.sync_run_id
            GROUP BY b.sync_run_id
            ORDER BY captured_at DESC, b.sync_run_id DESC
            LIMIT ?
            """,
            (max(1, min(int(limit or 90), 3650)),),
        ).fetchall()
        inv_rows = conn.execute(
            """
            SELECT sync_run_id, SUM(investment_holdings) AS brokerage_value
            FROM finance_investments
            GROUP BY sync_run_id
            """
        ).fetchall()
        inv_by_run = {row["sync_run_id"]: float(row["brokerage_value"] or 0.0) for row in inv_rows}
        tx_rows = conn.execute("SELECT transaction_date, amount, category, name, merchant_name FROM finance_transactions WHERE pending_status = 0").fetchall()
    finally:
        conn.close()
    import datetime as _dt
    txns = []
    for row in tx_rows:
        try:
            text = f"{row['category'] or ''} {row['name'] or ''} {row['merchant_name'] or ''}".lower()
            txns.append((_dt.date.fromisoformat(str(row["transaction_date"])), float(row["amount"] or 0.0), text))
        except ValueError:
            continue
    points: list[dict[str, Any]] = []
    for row in reversed(rows):
        captured = int(row["captured_at"] or 0)
        run_id = row["sync_run_id"]
        cash = float(row["cash_position"] or 0.0)
        debt = float(row["debt_total"] or 0.0)
        brokerage = inv_by_run.get(run_id, 0.0)
        value: float | None
        if metric == "cash_position":
            value = cash
        elif metric == "debt_total":
            value = debt
        elif metric == "brokerage_value":
            value = brokerage
        elif metric == "net_worth":
            value = cash + brokerage - debt
        elif metric in {"monthly_expenses", "net_cash_flow"}:
            end = _dt.datetime.fromtimestamp(captured).date() if captured else _dt.date.today()
            start = end - _dt.timedelta(days=30)
            income = sum(abs(amount) for date, amount, text in txns if start <= date <= end and amount < 0 and "transfer" not in text)
            expenses = sum(amount for date, amount, text in txns if start <= date <= end and amount > 0 and "transfer" not in text)
            value = expenses if metric == "monthly_expenses" else income - expenses
        elif metric == "emergency_fund" or metric == "car_fund":
            value = 0.0
        else:
            value = None
        points.append({"captured_at": captured, "value": None if value is None else round(float(value), 2)})
    return points


def normalized_finance_snapshot(*, path: Path | None = None) -> dict[str, Any] | None:
    conn = _connect(path)
    try:
        ensure_schema(conn)
        if not _has_normalized_finance_data(conn):
            return None
        snapshot = _normalized_finance_aggregate(conn)
        latest_sync = latest_finance_sync_status(path=path)
        snapshot["last_finance_sync"] = latest_sync.get("last_sync_at")
        snapshot["sync_health"] = latest_sync.get("sync_health")
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
            "executive_dashboard": executive_finance_dashboard(normalized, contract={"sync": sync}, path=path),
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
        "executive_dashboard": executive_finance_dashboard(snapshot, contract={"sync": latest_finance_sync_status(path=path)}, path=path),
    }



def _timestamp_to_iso(value: int | None) -> str | None:
    if not value:
        return None
    import datetime as _dt
    return _dt.datetime.fromtimestamp(int(value), tz=_dt.timezone.utc).isoformat()


def _change_from_history(metric: str, *, days: int, current: float | None, path: Path | None = None) -> float | None:
    if current is None:
        return None
    try:
        points = finance_history(metric, limit=max(days + 2, 3), path=path)
    except Exception:
        return None
    if len(points) < 2:
        return None
    import time as _time
    cutoff = int(_time.time()) - days * 86400
    baseline = None
    for point in points:
        if int(point.get("captured_at") or 0) <= cutoff and point.get("value") is not None:
            baseline = float(point["value"])
    if baseline is None:
        for point in points[:-1]:
            if point.get("value") is not None:
                baseline = float(point["value"])
                break
    if baseline is None:
        return None
    return round(float(current) - baseline, 2)


def _status_for_percent(value: float | None, *, good: float, warn: float, invert: bool = False) -> str:
    if value is None:
        return "Unknown"
    if invert:
        if value <= good:
            return "Safe"
        if value <= warn:
            return "Watch"
        return "High"
    if value >= good:
        return "Excellent"
    if value >= warn:
        return "Good"
    if value > 0:
        return "Building"
    return "Critical"


def _normalize_trend_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"captured_at": point.get("captured_at"), "value": point.get("value")} for point in points[-30:]]


def finance_registry_metadata(*, sync: dict[str, Any] | None = None, path: Path | None = None) -> dict[str, Any]:
    db_path = path or finance_registry_path()
    sync = sync or latest_finance_sync_status(path=path)
    size = db_path.stat().st_size if db_path.exists() else 0
    conn = _connect(path)
    try:
        ensure_schema(conn)
        migration = conn.execute("SELECT migration_id, applied_at FROM finance_registry_migrations ORDER BY applied_at DESC, id DESC LIMIT 1").fetchone()
        version = conn.execute("SELECT COUNT(*) AS count FROM finance_registry_migrations").fetchone()
    finally:
        conn.close()
    return {
        "registry_version": int(version["count"] or 0) if version else 0,
        "last_migration": dict(migration) if migration else None,
        "last_sync": sync.get("last_sync_at"),
        "provider": sync.get("provider") or "Plaid",
        "environment": sync.get("environment") or "Sandbox",
        "registry_location": str(db_path),
        "database_size_bytes": size,
        "synchronization_duration": sync.get("duration_seconds"),
        "synchronization_status": sync.get("status") or "never_synced",
    }


def connected_finance_institutions(*, path: Path | None = None) -> list[dict[str, Any]]:
    conn = _connect(path)
    try:
        ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT i.*, COUNT(a.id) AS account_count,
                   GROUP_CONCAT(DISTINCT a.account_subtype) AS account_subtypes,
                   GROUP_CONCAT(DISTINCT a.account_type) AS account_types
            FROM finance_institutions i
            LEFT JOIN finance_accounts a ON a.institution_id = i.institution_id AND a.is_active = 1
            GROUP BY i.id
            ORDER BY COALESCE(i.last_sync_at, i.updated_at, i.created_at) DESC, i.institution_name
            """
        ).fetchall()
    finally:
        conn.close()
    institutions = []
    has_connected_accounts = any(int(row["account_count"] or 0) > 0 for row in rows)
    for row in rows:
        if has_connected_accounts and int(row["account_count"] or 0) <= 0:
            continue
        subtypes = [item for item in str(row["account_subtypes"] or "").split(",") if item]
        types = [item for item in str(row["account_types"] or "").split(",") if item]
        institutions.append({
            "institution_logo": None,
            "institution_name": row["institution_name"] or row["institution_id"],
            "institution_id": row["institution_id"],
            "connected_account_count": int(row["account_count"] or 0),
            "last_synchronized": row["last_sync_at"],
            "connection_status": row["status"] or "active",
            "account_types": subtypes or types,
        })
    return institutions


def recent_finance_activity(*, path: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    conn = _connect(path)
    try:
        ensure_schema(conn)
        txns = conn.execute(
            """
            SELECT t.*, a.account_name, a.account_type, a.account_subtype
            FROM finance_transactions t
            LEFT JOIN finance_accounts a ON a.provider_account_id = t.provider_account_id
            WHERE t.pending_status = 0
            ORDER BY t.transaction_date DESC, t.id DESC
            LIMIT 50
            """
        ).fetchall()
        investments = conn.execute(
            """
            SELECT * FROM finance_investments
            ORDER BY captured_at DESC, id DESC
            LIMIT 10
            """
        ).fetchall()
    finally:
        conn.close()
    income: list[dict[str, Any]] = []
    expenses: list[dict[str, Any]] = []
    transfers: list[dict[str, Any]] = []
    debt_payments: list[dict[str, Any]] = []
    for row in txns:
        amount = float(row["amount"] or 0.0)
        item = {"date": row["transaction_date"], "name": row["merchant_name"] or row["name"], "amount": round(amount, 2), "account": row["account_name"], "category": row["category"]}
        category = str(row["category"] or "").lower()
        name = str(item["name"] or "").lower()
        if amount < 0 and len(income) < 5:
            income.append({**item, "amount": round(abs(amount), 2)})
        elif "transfer" in category or "transfer" in name:
            if len(transfers) < 5:
                transfers.append(item)
        elif "loan" in category or "credit card" in category or "payment" in name:
            if len(debt_payments) < 5:
                debt_payments.append(item)
        elif amount > 0:
            expenses.append(item)
    expenses = sorted(expenses, key=lambda item: float(item.get("amount") or 0.0), reverse=True)[:5]
    investment_activity = [
        {"date": row["captured_at"], "name": row["ticker_symbol"] or row["security_name"] or "Holding", "amount": row["investment_holdings"], "account": row["provider_account_id"]}
        for row in investments
    ]
    return {"latest_income": income, "largest_recent_expenses": expenses, "recent_transfers": transfers, "investment_activity": investment_activity, "debt_payments": debt_payments}


def executive_financial_health(snapshot: dict[str, Any], *, path: Path | None = None) -> dict[str, Any]:
    metrics = snapshot.get("metrics") or calculate_finance_metrics(snapshot)
    net_worth = _number(metrics.get("net_worth"), 0.0) or 0.0
    cash = _number(snapshot.get("cash_position", (snapshot.get("checking_balance") or 0) + (snapshot.get("savings_balance") or 0) + (snapshot.get("emergency_fund") or 0)), 0.0) or 0.0
    monthly_expenses = _number(metrics.get("monthly_expenses"), 0.0) or 0.0
    monthly_income = _number(metrics.get("monthly_income"), 0.0) or 0.0
    debt = _number(snapshot.get("debt_total"), 0.0) or 0.0
    ef_pct = metrics.get("emergency_fund_completion_percent")
    savings_rate = metrics.get("savings_rate_percent")
    cash_flow = metrics.get("net_cash_flow")
    runway = metrics.get("runway_months")
    net_worth_monthly_change = _change_from_history("net_worth", days=30, current=net_worth, path=path)
    debt_ratio = None if net_worth + debt <= 0 else (debt / (net_worth + debt)) * 100.0
    liquidity = None if monthly_expenses <= 0 else cash / monthly_expenses
    credit_util = snapshot.get("credit_utilization_percent")
    component_scores = {
        "emergency_fund": min(100.0, float(ef_pct or 0.0)),
        "debt_ratio": 100.0 if debt_ratio is None else max(0.0, 100.0 - debt_ratio),
        "cash_flow": 100.0 if (cash_flow or 0) > 0 else 40.0 if (cash_flow or 0) == 0 else 10.0,
        "savings_rate": max(0.0, min(100.0, float(savings_rate or 0.0) * 2.5)),
        "credit_utilization": 100.0 if credit_util is None else max(0.0, 100.0 - float(credit_util) * 1.6),
        "liquidity": max(0.0, min(100.0, float(liquidity or runway or 0.0) / 6.0 * 100.0)),
        "net_worth_trend": 85.0 if (net_worth_monthly_change or 0) > 0 else 55.0 if net_worth_monthly_change == 0 else 25.0,
    }
    weights = {"emergency_fund": 0.18, "debt_ratio": 0.16, "cash_flow": 0.18, "savings_rate": 0.14, "credit_utilization": 0.12, "liquidity": 0.12, "net_worth_trend": 0.10}
    score = round(sum(component_scores[key] * weights[key] for key in weights))
    rating = "Excellent" if score >= 85 else "Good" if score >= 70 else "Fair" if score >= 50 else "Poor"
    reasons = []
    if cash_flow is not None:
        reasons.append("positive monthly cash flow" if cash_flow >= 0 else "negative monthly cash flow")
    if ef_pct is not None:
        reasons.append(f"emergency fund is {ef_pct:.0f}% funded")
    if net_worth_monthly_change is not None:
        reasons.append("net worth improved" if net_worth_monthly_change >= 0 else "net worth declined")
    explanation = "Score reflects " + ", ".join(reasons[:3]) + "." if reasons else "Score reflects available registry metrics."
    return {"score": score, "rating": rating, "components": {k: round(v, 1) for k, v in component_scores.items()}, "weights": weights, "explanation": explanation, "changed_because": explanation}


def executive_finance_alerts(snapshot: dict[str, Any], *, activity: dict[str, list[dict[str, Any]]] | None = None) -> list[dict[str, Any]]:
    metrics = snapshot.get("metrics") or calculate_finance_metrics(snapshot)
    alerts: list[dict[str, Any]] = []
    ef_pct = metrics.get("emergency_fund_completion_percent")
    if ef_pct is not None and ef_pct < 100:
        severity = "critical" if ef_pct < 25 else "warning"
        alerts.append({"severity": severity, "title": "Emergency fund below target", "message": f"Emergency fund is {ef_pct:.0f}% funded.", "action": "Prioritize emergency savings."})
    cash_flow = metrics.get("net_cash_flow")
    if cash_flow is not None and cash_flow < 0:
        alerts.append({"severity": "critical", "title": "Negative monthly cash flow", "message": f"Expenses exceed income by ${abs(cash_flow):,.2f}.", "action": "Reduce discretionary spending."})
    debt = _number(snapshot.get("debt_total"), 0.0) or 0.0
    if debt > 0:
        alerts.append({"severity": "warning", "title": "Debt requires monitoring", "message": f"Total debt is ${debt:,.2f}.", "action": "Review payoff plan."})
    activity = activity or {}
    large_expense = next(iter(activity.get("largest_recent_expenses") or []), None)
    if large_expense and float(large_expense.get("amount") or 0.0) >= 500:
        alerts.append({"severity": "warning", "title": "Large transaction posted", "message": f"{large_expense.get('name')} posted for ${float(large_expense.get('amount') or 0):,.2f}.", "action": "Confirm it is expected."})
    latest_income = next(iter(activity.get("latest_income") or []), None)
    if latest_income:
        alerts.append({"severity": "good", "title": "Income received", "message": f"{latest_income.get('name')} deposited ${float(latest_income.get('amount') or 0):,.2f}.", "action": "Allocate to goals."})
    return alerts[:6]


def executive_finance_insights(snapshot: dict[str, Any], *, path: Path | None = None) -> list[str]:
    metrics = snapshot.get("metrics") or calculate_finance_metrics(snapshot)
    insights: list[str] = []
    net_worth = metrics.get("net_worth")
    nw_change = _change_from_history("net_worth", days=30, current=net_worth, path=path) if net_worth is not None else None
    if nw_change is not None:
        insights.append(f"Net Worth {'increased' if nw_change >= 0 else 'decreased'} by ${abs(nw_change):,.2f} over the latest registry trend window.")
    ef_change = _change_from_history("emergency_fund", days=30, current=snapshot.get("emergency_fund"), path=path)
    if ef_change is not None and ef_change != 0:
        insights.append(f"Emergency Fund {'increased' if ef_change >= 0 else 'decreased'} by ${abs(ef_change):,.2f}.")
    spending = metrics.get("monthly_expenses")
    spending_change = _change_from_history("monthly_expenses", days=30, current=spending, path=path) if spending is not None else None
    if spending_change is not None and spending:
        pct = abs(spending_change) / max(abs(float(spending) - spending_change), 1.0) * 100.0
        insights.append(f"You spent {pct:.0f}% {'more' if spending_change > 0 else 'less'} than the prior registry period.")
    ef_pct = metrics.get("emergency_fund_completion_percent")
    cash_flow = metrics.get("net_cash_flow")
    if ef_pct is not None and cash_flow and cash_flow > 0 and ef_pct < 100:
        remaining = max(0.0, float(snapshot.get("emergency_fund_target") or 0.0) - float(snapshot.get("emergency_fund") or 0.0))
        months = int((remaining / cash_flow) + 0.999) if cash_flow else None
        if months:
            insights.append(f"You are projected to reach your Emergency Fund goal in {months} months.")
    if not insights:
        insights.append("Finance insights are ready after the next successful registry sync adds trend data.")
    return insights[:5]


def executive_finance_dashboard(snapshot: dict[str, Any], *, contract: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    metrics = snapshot.get("metrics") or calculate_finance_metrics(snapshot)
    sync = contract.get("sync") or latest_finance_sync_status(path=path)
    activity = recent_finance_activity(path=path)
    health = executive_financial_health(snapshot, path=path)
    cash_available = snapshot.get("cash_position") if snapshot.get("cash_position") is not None else (snapshot.get("checking_balance") or 0.0) + (snapshot.get("savings_balance") or 0.0)
    emergency_pct = metrics.get("emergency_fund_completion_percent")
    credit_util = snapshot.get("credit_utilization_percent")
    net_worth = metrics.get("net_worth")
    kpis = {
        "net_worth": {"current": net_worth, "daily_change": _change_from_history("net_worth", days=1, current=net_worth, path=path), "monthly_change": _change_from_history("net_worth", days=30, current=net_worth, path=path)},
        "cash_available": {"checking": snapshot.get("checking_balance"), "savings": snapshot.get("savings_balance"), "available_cash": round(float(cash_available or 0.0), 2)},
        "monthly_cash_flow": {"income": metrics.get("monthly_income"), "expenses": metrics.get("monthly_expenses"), "cash_flow": metrics.get("net_cash_flow"), "status": "Positive" if (metrics.get("net_cash_flow") or 0) >= 0 else "Negative"},
        "emergency_fund": {"current": snapshot.get("emergency_fund"), "target": snapshot.get("emergency_fund_target"), "progress_percent": emergency_pct, "status": _status_for_percent(emergency_pct, good=100, warn=50)},
        "investment_portfolio": {"current_value": snapshot.get("brokerage_value"), "gain_loss": None, "allocation": metrics.get("investment_allocation_percent")},
        "debt": {"total_debt": snapshot.get("debt_total"), "monthly_reduction": None if _change_from_history("debt_total", days=30, current=snapshot.get("debt_total"), path=path) is None else round(-float(_change_from_history("debt_total", days=30, current=snapshot.get("debt_total"), path=path) or 0.0), 2), "projected_payoff_date": None},
        "monthly_burn": {"average_monthly_spending": metrics.get("monthly_expenses"), "trend": _change_from_history("monthly_expenses", days=30, current=metrics.get("monthly_expenses"), path=path)},
        "credit_utilization": {"current_utilization": credit_util, "status": _status_for_percent(credit_util, good=30, warn=60, invert=True)},
        "savings_rate": {"monthly_percent": metrics.get("savings_rate_percent"), "target_percent": 20},
        "runway": {"months_remaining": metrics.get("runway_months")},
        "next_payday": {"date": snapshot.get("next_payday_date"), "estimated_amount": snapshot.get("next_payday_amount")},
        "last_successful_sync": {"relative_time": sync.get("last_successful_sync_at"), "sync_duration": sync.get("duration_seconds")},
    }
    trends = {
        "net_worth_30_days": {"label": "Net Worth (30 days)", "points": _normalize_trend_points(finance_history("net_worth", limit=30, path=path))},
        "cash_flow_30_days": {"label": "Cash Flow (30 days)", "points": _normalize_trend_points(finance_history("net_cash_flow", limit=30, path=path))},
        "debt_30_days": {"label": "Debt (30 days)", "points": _normalize_trend_points(finance_history("debt_total", limit=30, path=path))},
        "investments_30_days": {"label": "Investments (30 days)", "points": _normalize_trend_points(finance_history("brokerage_value", limit=30, path=path))},
        "emergency_fund_progress": {"label": "Emergency Fund Progress", "points": _normalize_trend_points(finance_history("emergency_fund", limit=30, path=path))},
        "car_fund_progress": {"label": "Car Fund Progress", "points": _normalize_trend_points(finance_history("car_fund", limit=30, path=path))},
    }
    return {
        "kpis": kpis,
        "financial_health": health,
        "alerts": executive_finance_alerts(snapshot, activity=activity),
        "connected_institutions": connected_finance_institutions(path=path),
        "quick_actions": ["Connect Bank", "Sync Now", "Disconnect Bank", "View Accounts", "View Transactions", "Generate Financial Report", "Export CSV"],
        "trends": trends,
        "recent_activity": activity,
        "registry_metadata": finance_registry_metadata(sync=sync, path=path),
        "sync_history": sync.get("history") or [],
        "insights": executive_finance_insights(snapshot, path=path),
        "performance": {"cached_registry_data": True, "frontend_direct_plaid": False, "target_load_ms": 1000},
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
        "executive_dashboard": contract.get("executive_dashboard"),
    }
