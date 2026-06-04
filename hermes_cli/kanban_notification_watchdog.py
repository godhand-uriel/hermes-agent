"""Kanban notification subscription coverage watchdog.

Deterministic scanner/remediator for command_center Telegram notification
coverage across a fixed set of Kanban boards.  The module is intentionally
independent from the gateway so it can run from CLI/cron without model calls.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sqlite3
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from hermes_cli import kanban_db as kb

DEFAULT_SCOPED_BOARDS = [
    "command-center-board",
    "career-development-board",
    "engineering-brand-board",
    "artist-management-board",
    "venture-portfolio-board",
    "research-office-board",
]

ACTIVE_STATUSES = {"triage", "todo", "scheduled", "ready", "running", "blocked", "review"}
FINAL_STATUSES = {"done", "archived"}
VALID_MODES = {"detect", "dry-run", "repair-safe", "repair-cleanup"}
REQUIRED_TABLES = {
    "tasks": {"id", "title", "assignee", "status", "current_run_id", "created_at", "started_at", "completed_at"},
    "task_events": {"id", "task_id", "kind", "created_at"},
    "kanban_notify_subs": {"task_id", "platform", "chat_id", "thread_id", "user_id", "notifier_profile", "created_at", "last_event_id"},
}


@dataclass(frozen=True)
class CommandCenterTarget:
    platform: str = "telegram"
    chat_id: str = ""
    thread_id: str = ""
    user_id: Optional[str] = None
    source: str = "explicit"

    def normalized(self) -> "CommandCenterTarget":
        return CommandCenterTarget(
            platform=(self.platform or "telegram").strip().lower(),
            chat_id=str(self.chat_id or "").strip(),
            thread_id=str(self.thread_id or "").strip(),
            user_id=(str(self.user_id).strip() if self.user_id else None),
            source=self.source,
        )


@dataclass
class WatchdogConfig:
    scoped_boards: list[str] = field(default_factory=lambda: list(DEFAULT_SCOPED_BOARDS))
    command_center_profile: str = "command_center"
    target: Optional[CommandCenterTarget] = None
    mode: str = "detect"
    allow_inferred_target_for_writes: bool = False
    global_orphan_scan: bool = False
    audit_db_path: Optional[Path] = None


@dataclass
class Finding:
    board_slug: str
    finding_type: str
    severity: str
    status: str
    task_id: Optional[str] = None
    board_db_path: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Remediation:
    board_slug: str
    task_id: Optional[str]
    finding_type: str
    action: str
    mode: str
    success: bool
    before: Optional[dict[str, Any]] = None
    after: Optional[dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class BoardReport:
    slug: str
    db_path: Optional[str]
    status: str = "unknown"
    active_task_count: int = 0
    covered_task_count: int = 0
    missing_task_count: int = 0
    findings_count: int = 0
    remediations_count: int = 0


@dataclass
class WatchdogRun:
    run_id: str
    started_at: int
    finished_at: Optional[int]
    mode: str
    command_center_profile: str
    target: Optional[CommandCenterTarget]
    status: str
    coverage_percent: float
    active_task_count: int
    covered_task_count: int
    findings: list[Finding] = field(default_factory=list)
    remediations: list[Remediation] = field(default_factory=list)
    boards: dict[str, BoardReport] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def missing_subscription_count(self) -> int:
        return sum(1 for f in self.findings if f.finding_type == "missing_subscription")

    @property
    def unresolved_issues_count(self) -> int:
        return sum(1 for f in self.findings if f.status != "resolved") + sum(1 for r in self.remediations if not r.success)

    def to_report_dict(self) -> dict[str, Any]:
        return {
            "title": "SUBSCRIPTION COVERAGE REPORT",
            "run_id": self.run_id,
            "status": self.status,
            "mode": self.mode,
            "coverage_percent": self.coverage_percent,
            "total_active_tasks": self.active_task_count,
            "covered_tasks": self.covered_task_count,
            "tasks_missing_subscriptions": self.missing_subscription_count,
            "remediations_performed": sum(1 for r in self.remediations if r.success),
            "unresolved_issues": self.unresolved_issues_count,
            "command_center_profile": self.command_center_profile,
            "canonical_target": asdict(self.target) if self.target else None,
            "boards": {slug: asdict(report) for slug, report in self.boards.items()},
            "findings": [
                {
                    "board_slug": f.board_slug,
                    "board_db_path": f.board_db_path,
                    "task_id": f.task_id,
                    "severity": f.severity,
                    "finding_type": f.finding_type,
                    "status": f.status,
                    "details": f.details,
                }
                for f in self.findings
            ],
            "remediations": [asdict(r) for r in self.remediations],
        }

    def format_text(self) -> str:
        lines = [
            "SUBSCRIPTION COVERAGE REPORT",
            f"Status: {self.status}",
            f"Mode: {self.mode}",
            f"Coverage: {self.covered_task_count}/{self.active_task_count} active tasks ({self.coverage_percent:.1f}%)",
            f"Tasks missing subscriptions: {self.missing_subscription_count}",
            f"Remediations performed: {sum(1 for r in self.remediations if r.success)}",
            f"Unresolved issues: {self.unresolved_issues_count}",
        ]
        if self.target:
            lines.append(f"Target: {self.target.platform}:{self.target.chat_id}:{self.target.thread_id}")
        lines.append("")
        lines.append("Boards:")
        for board in self.boards.values():
            lines.append(
                f"- {board.slug}: {board.status}, active={board.active_task_count}, "
                f"covered={board.covered_task_count}, missing={board.missing_task_count}, "
                f"findings={board.findings_count}, remediations={board.remediations_count}"
            )
        if self.findings:
            lines.append("")
            lines.append("Findings:")
            for f in self.findings[:50]:
                task = f" task={f.task_id}" if f.task_id else ""
                lines.append(f"- {f.severity} {f.board_slug}{task}: {f.finding_type} ({f.status})")
            if len(self.findings) > 50:
                lines.append(f"... {len(self.findings) - 50} more findings omitted")
        return "\n".join(lines) + "\n"


@contextlib.contextmanager
def _without_kanban_board_env():
    saved = {name: os.environ.get(name) for name in ("HERMES_KANBAN_DB", "HERMES_KANBAN_BOARD")}
    try:
        for name in saved:
            os.environ.pop(name, None)
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _board_db_path(slug: str) -> Path:
    with _without_kanban_board_env():
        return kb.kanban_db_path(board=slug)


def _board_exists(slug: str) -> bool:
    with _without_kanban_board_env():
        return kb.board_exists(slug)


def _connect_board(slug: str, *, write: bool = False) -> sqlite3.Connection:
    path = _board_db_path(slug)
    if write:
        conn = sqlite3.connect(path, timeout=30)
    else:
        uri = f"file:{path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _schema_findings(conn: sqlite3.Connection, slug: str, path: Path) -> list[Finding]:
    findings: list[Finding] = []
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    for table, required_cols in REQUIRED_TABLES.items():
        if table not in tables:
            findings.append(Finding(slug, "schema_missing", "critical", "open", board_db_path=str(path), details={"table": table}))
            continue
        missing = sorted(required_cols - _columns(conn, table))
        if missing:
            findings.append(
                Finding(slug, "schema_missing", "critical", "open", board_db_path=str(path), details={"table": table, "missing_columns": missing})
            )
    return findings


def _max_event_id(conn: sqlite3.Connection, task_id: str) -> int:
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS max_id FROM task_events WHERE task_id = ?", (task_id,)).fetchone()
    return int(row["max_id"] or 0)


def _load_target_from_config(config: WatchdogConfig) -> Optional[CommandCenterTarget]:
    if config.target:
        target = config.target.normalized()
        return target if target.chat_id else None
    # Explicit watchdog config is the preferred non-interactive source.
    try:
        from hermes_cli.config import load_config

        raw = load_config().get("notification_watchdog", {}) or {}
        t = raw.get("telegram_target") or {}
        if isinstance(t, dict) and t.get("chat_id"):
            return CommandCenterTarget(
                platform=str(t.get("platform") or "telegram"),
                chat_id=str(t.get("chat_id") or ""),
                thread_id=str(t.get("thread_id") or ""),
                user_id=t.get("user_id"),
                source="config",
            ).normalized()
    except Exception:
        pass
    # Gateway home channel fallback: deterministic and operator-configured.
    try:
        from gateway.config import load_gateway_config

        gw_cfg = load_gateway_config()
        for platform, pcfg in sorted(gw_cfg.platforms.items(), key=lambda item: getattr(item[0], "value", str(item[0]))):
            platform_name = getattr(platform, "value", str(platform))
            if platform_name != "telegram" or not pcfg or not pcfg.home_channel:
                continue
            hc = pcfg.home_channel
            if hc.chat_id:
                return CommandCenterTarget(
                    platform="telegram",
                    chat_id=str(hc.chat_id),
                    thread_id=str(hc.thread_id or ""),
                    user_id=None,
                    source="gateway_home_channel",
                ).normalized()
    except Exception:
        pass
    # Existing known-good subscription fallback. It is safe for detection, but
    # repair writes require explicit opt-in because this destination was inferred.
    try:
        inferred = _infer_target_from_existing_subscriptions(config)
        if inferred and (config.mode in {"detect", "dry-run"} or config.allow_inferred_target_for_writes):
            return inferred
    except Exception:
        pass
    return None


def _infer_target_from_existing_subscriptions(config: WatchdogConfig) -> Optional[CommandCenterTarget]:
    counts: dict[tuple[str, str], int] = {}
    for slug in config.scoped_boards:
        normed = kb._normalize_board_slug(slug)
        if not normed or not _board_db_path(normed).exists():
            continue
        try:
            conn = _connect_board(normed, write=False)
        except Exception:
            continue
        try:
            rows = conn.execute(
                """
                SELECT chat_id, thread_id, COUNT(*) AS n
                FROM kanban_notify_subs
                WHERE platform = 'telegram'
                  AND notifier_profile = ?
                  AND COALESCE(chat_id, '') != ''
                GROUP BY chat_id, thread_id
                """,
                (config.command_center_profile,),
            ).fetchall()
            for row in rows:
                key = (str(row["chat_id"]), str(row["thread_id"] or ""))
                counts[key] = counts.get(key, 0) + int(row["n"] or 0)
        except Exception:
            continue
        finally:
            conn.close()
    if not counts:
        return None
    chat_id, thread_id = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
    return CommandCenterTarget(platform="telegram", chat_id=chat_id, thread_id=thread_id, source="existing_subscriptions").normalized()


def _audit_db_path(config: WatchdogConfig) -> Path:
    if config.audit_db_path:
        return Path(config.audit_db_path)
    with _without_kanban_board_env():
        return kb.kanban_home() / "notification_watchdog" / "remediations.db"


def _init_audit_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS notification_watchdog_runs (
          run_id TEXT PRIMARY KEY,
          started_at INTEGER NOT NULL,
          finished_at INTEGER,
          mode TEXT NOT NULL,
          command_center_profile TEXT NOT NULL,
          canonical_platform TEXT NOT NULL,
          canonical_chat_id TEXT,
          canonical_thread_id TEXT NOT NULL DEFAULT '',
          scoped_boards_json TEXT NOT NULL,
          status TEXT NOT NULL,
          coverage_percent REAL NOT NULL DEFAULT 0,
          active_task_count INTEGER NOT NULL DEFAULT 0,
          covered_task_count INTEGER NOT NULL DEFAULT 0,
          findings_count INTEGER NOT NULL DEFAULT 0,
          remediations_attempted INTEGER NOT NULL DEFAULT 0,
          remediations_succeeded INTEGER NOT NULL DEFAULT 0,
          remediations_failed INTEGER NOT NULL DEFAULT 0,
          error TEXT
        );
        CREATE TABLE IF NOT EXISTS notification_watchdog_findings (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id TEXT NOT NULL,
          board_slug TEXT NOT NULL,
          board_db_path TEXT,
          task_id TEXT,
          severity TEXT NOT NULL,
          finding_type TEXT NOT NULL,
          status TEXT NOT NULL,
          details_json TEXT NOT NULL,
          created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notification_watchdog_remediations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id TEXT NOT NULL,
          board_slug TEXT NOT NULL,
          task_id TEXT,
          finding_type TEXT NOT NULL,
          action TEXT NOT NULL,
          mode TEXT NOT NULL,
          before_json TEXT,
          after_json TEXT,
          success INTEGER NOT NULL,
          error TEXT,
          created_at INTEGER NOT NULL
        );
        """
    )
    conn.commit()
    return conn


def _write_audit(conn: sqlite3.Connection, run: WatchdogRun, scoped_boards: list[str]) -> None:
    target = run.target or CommandCenterTarget()
    now = int(time.time())
    conn.execute(
        """
        INSERT OR REPLACE INTO notification_watchdog_runs
        (run_id, started_at, finished_at, mode, command_center_profile, canonical_platform,
         canonical_chat_id, canonical_thread_id, scoped_boards_json, status, coverage_percent,
         active_task_count, covered_task_count, findings_count, remediations_attempted,
         remediations_succeeded, remediations_failed, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run.run_id,
            run.started_at,
            run.finished_at,
            run.mode,
            run.command_center_profile,
            target.platform,
            target.chat_id,
            target.thread_id,
            json.dumps(scoped_boards),
            run.status,
            run.coverage_percent,
            run.active_task_count,
            run.covered_task_count,
            len(run.findings),
            len(run.remediations),
            sum(1 for r in run.remediations if r.success),
            sum(1 for r in run.remediations if not r.success),
            run.error,
        ),
    )
    for f in run.findings:
        conn.execute(
            """
            INSERT INTO notification_watchdog_findings
            (run_id, board_slug, board_db_path, task_id, severity, finding_type, status, details_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run.run_id, f.board_slug, f.board_db_path, f.task_id, f.severity, f.finding_type, f.status, json.dumps(f.details, sort_keys=True), now),
        )
    for r in run.remediations:
        conn.execute(
            """
            INSERT INTO notification_watchdog_remediations
            (run_id, board_slug, task_id, finding_type, action, mode, before_json, after_json, success, error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                r.board_slug,
                r.task_id,
                r.finding_type,
                r.action,
                r.mode,
                json.dumps(r.before, sort_keys=True) if r.before is not None else None,
                json.dumps(r.after, sort_keys=True) if r.after is not None else None,
                1 if r.success else 0,
                r.error,
                now,
            ),
        )
    conn.commit()


def _find_and_optionally_repair_board(
    *,
    slug: str,
    target: CommandCenterTarget,
    config: WatchdogConfig,
    run: WatchdogRun,
) -> None:
    path = _board_db_path(slug)
    board = BoardReport(slug=slug, db_path=str(path))
    run.boards[slug] = board

    if not _board_exists(slug) and not path.exists():
        finding = Finding(slug, "board_missing", "critical", "open", board_db_path=str(path), details={"policy_scoped": True})
        run.findings.append(finding)
        board.status = "unavailable"
        board.findings_count += 1
        return
    if not path.exists():
        finding = Finding(slug, "db_missing", "critical", "open", board_db_path=str(path))
        run.findings.append(finding)
        board.status = "unavailable"
        board.findings_count += 1
        return

    try:
        conn = _connect_board(slug, write=config.mode in {"repair-safe", "repair-cleanup"})
    except Exception as exc:
        run.findings.append(Finding(slug, "db_unreadable", "critical", "open", board_db_path=str(path), details={"error": str(exc)}))
        board.status = "unavailable"
        board.findings_count += 1
        return

    try:
        schema_findings = _schema_findings(conn, slug, path)
        if schema_findings:
            run.findings.extend(schema_findings)
            board.status = "unavailable"
            board.findings_count += len(schema_findings)
            return

        tasks = [dict(row) for row in conn.execute(
            """
            SELECT id, title, assignee, status, current_run_id, created_at, started_at, completed_at
            FROM tasks
            WHERE status IN ('triage','todo','scheduled','ready','running','blocked','review')
            ORDER BY priority DESC, created_at ASC
            """
        ).fetchall()]
        all_task_status = {row["id"]: row["status"] for row in conn.execute("SELECT id, status FROM tasks").fetchall()}
        run.active_task_count += len(tasks)
        board.active_task_count = len(tasks)
        active_ids = {t["id"] for t in tasks}
        subs = [dict(row) for row in conn.execute("SELECT * FROM kanban_notify_subs").fetchall()]
        subs_by_task: dict[str, list[dict]] = {}
        for sub in subs:
            subs_by_task.setdefault(str(sub.get("task_id") or ""), []).append(sub)

        def _canonical(sub: dict) -> bool:
            return (
                str(sub.get("platform") or "").lower() == target.platform
                and str(sub.get("chat_id") or "") == target.chat_id
                and str(sub.get("thread_id") or "") == target.thread_id
            )

        for task in tasks:
            tid = task["id"]
            task_subs = subs_by_task.get(tid, [])
            canonical_subs = [s for s in task_subs if _canonical(s)]
            healthy = [s for s in canonical_subs if (s.get("notifier_profile") or "") == config.command_center_profile]
            legacy_empty = [s for s in canonical_subs if not (s.get("notifier_profile") or "")]
            wrong_owner = [s for s in canonical_subs if (s.get("notifier_profile") or "") not in {"", config.command_center_profile}]

            if not canonical_subs:
                finding = Finding(slug, "missing_subscription", "high", "open", tid, str(path), {"task_status": task["status"]})
                run.findings.append(finding)
                board.missing_task_count += 1
                if config.mode in {"repair-safe", "repair-cleanup"}:
                    rem = _add_missing(conn, slug, tid, target, config)
                    run.remediations.append(rem)
                    board.remediations_count += 1
                    if rem.success:
                        finding.status = "resolved"
                        healthy = [{"notifier_profile": config.command_center_profile}]
                    else:
                        finding.severity = "critical"
                elif config.mode == "dry-run":
                    run.remediations.append(Remediation(slug, tid, "missing_subscription", "would_add_missing_subscription", config.mode, True))
            elif wrong_owner and not healthy and not legacy_empty:
                run.findings.append(
                    Finding(slug, "stale_owner", "high", "open", tid, str(path), {"owners": sorted({str(s.get("notifier_profile") or "") for s in wrong_owner})})
                )
                board.missing_task_count += 1
            elif legacy_empty and not healthy:
                finding = Finding(slug, "stale_owner", "high", "open", tid, str(path), {"owner": ""})
                run.findings.append(finding)
                if config.mode in {"repair-safe", "repair-cleanup"}:
                    rem = _backfill_owner(conn, slug, tid, target, config)
                    run.remediations.append(rem)
                    board.remediations_count += 1
                    if rem.success:
                        finding.status = "resolved"
                        healthy = [{"notifier_profile": config.command_center_profile}]
                elif config.mode == "dry-run":
                    run.remediations.append(Remediation(slug, tid, "stale_owner", "would_backfill_owner", config.mode, True))

            for sub in canonical_subs:
                max_event = _max_event_id(conn, tid)
                try:
                    cursor = int(sub.get("last_event_id") or 0)
                except Exception:
                    cursor = max_event + 1
                if cursor > max_event:
                    finding = Finding(slug, "stale_cursor", "high", "open", tid, str(path), {"last_event_id": cursor, "max_event_id": max_event})
                    run.findings.append(finding)
                    if config.mode in {"repair-safe", "repair-cleanup"}:
                        rem = _reset_cursor(conn, slug, tid, target, max_event, config, before=sub)
                        run.remediations.append(rem)
                        board.remediations_count += 1
                        if rem.success:
                            finding.status = "resolved"
                    elif config.mode == "dry-run":
                        run.remediations.append(Remediation(slug, tid, "stale_cursor", "would_reset_stale_cursor", config.mode, True, before=sub, after={"last_event_id": max_event}))

            telegram_subs = [s for s in task_subs if str(s.get("platform") or "").lower() == "telegram"]
            noncanonical_telegram = [s for s in telegram_subs if not _canonical(s)]
            if noncanonical_telegram and (healthy or legacy_empty):
                finding = Finding(slug, "duplicate_subscription", "medium", "open", tid, str(path), {"extra_destinations": [_sub_key(s) for s in noncanonical_telegram]})
                run.findings.append(finding)
                if config.mode == "repair-cleanup" and healthy:
                    all_success = True
                    for extra in noncanonical_telegram:
                        rem = _delete_subscription(conn, slug, tid, "duplicate_subscription", "remove_noncanonical_duplicate", config, before=extra)
                        run.remediations.append(rem)
                        board.remediations_count += 1
                        all_success = all_success and rem.success
                    if all_success:
                        finding.status = "resolved"
                elif config.mode == "dry-run" and healthy:
                    for extra in noncanonical_telegram:
                        run.remediations.append(Remediation(slug, tid, "duplicate_subscription", "would_remove_noncanonical_duplicate", config.mode, True, before=extra))

            if healthy:
                run.covered_task_count += 1
                board.covered_task_count += 1

        # orphaned/final subscriptions
        for sub in subs:
            tid = str(sub.get("task_id") or "")
            if tid in active_ids:
                continue
            status = all_task_status.get(tid)
            if status is None:
                finding = Finding(slug, "orphaned_subscription", "medium", "open", tid, str(path), {"subscription": _sub_key(sub)})
                run.findings.append(finding)
                if config.mode == "repair-cleanup":
                    rem = _delete_subscription(conn, slug, tid, "orphaned_subscription", "remove_absent_task_orphan", config, before=sub)
                    run.remediations.append(rem)
                    board.remediations_count += 1
                    if rem.success:
                        finding.status = "resolved"
                elif config.mode == "dry-run":
                    run.remediations.append(Remediation(slug, tid, "orphaned_subscription", "would_remove_absent_task_orphan", config.mode, True, before=sub))
            elif status in FINAL_STATUSES:
                max_event = _max_event_id(conn, tid)
                cursor = int(sub.get("last_event_id") or 0)
                if cursor >= max_event:
                    finding = Finding(slug, "orphaned_subscription", "medium", "open", tid, str(path), {"task_status": status, "subscription": _sub_key(sub)})
                    run.findings.append(finding)
                    if config.mode == "repair-cleanup":
                        rem = _delete_subscription(conn, slug, tid, "orphaned_subscription", "remove_final_task_subscription", config, before=sub)
                        run.remediations.append(rem)
                        board.remediations_count += 1
                        if rem.success:
                            finding.status = "resolved"
                    elif config.mode == "dry-run":
                        run.remediations.append(Remediation(slug, tid, "orphaned_subscription", "would_remove_final_task_subscription", config.mode, True, before=sub))

        board.findings_count = sum(1 for f in run.findings if f.board_slug == slug)
        if board.active_task_count and board.covered_task_count < board.active_task_count:
            board.status = "uncovered"
        elif board.remediations_count:
            board.status = "repaired"
        elif board.findings_count:
            board.status = "degraded"
        else:
            board.status = "ok"
    finally:
        conn.close()


def _sub_key(sub: dict) -> dict[str, Any]:
    return {
        "platform": sub.get("platform"),
        "chat_id": sub.get("chat_id"),
        "thread_id": sub.get("thread_id") or "",
        "notifier_profile": sub.get("notifier_profile") or "",
    }


def _add_missing(conn: sqlite3.Connection, slug: str, task_id: str, target: CommandCenterTarget, config: WatchdogConfig) -> Remediation:
    before = {"subscription": None}
    try:
        kb.add_notify_sub(
            conn,
            task_id=task_id,
            platform=target.platform,
            chat_id=target.chat_id,
            thread_id=target.thread_id,
            user_id=target.user_id,
            notifier_profile=config.command_center_profile,
        )
        after = next((s for s in kb.list_notify_subs(conn, task_id) if _matches_target(s, target)), None)
        return Remediation(slug, task_id, "missing_subscription", "add_missing_subscription", config.mode, True, before, after)
    except Exception as exc:
        return Remediation(slug, task_id, "missing_subscription", "add_missing_subscription", config.mode, False, before, None, str(exc))


def _backfill_owner(conn: sqlite3.Connection, slug: str, task_id: str, target: CommandCenterTarget, config: WatchdogConfig) -> Remediation:
    before = next((s for s in kb.list_notify_subs(conn, task_id) if _matches_target(s, target)), None)
    try:
        with kb.write_txn(conn):
            conn.execute(
                """
                UPDATE kanban_notify_subs SET notifier_profile = ?
                WHERE task_id = ? AND platform = ? AND chat_id = ? AND thread_id = ?
                  AND (notifier_profile IS NULL OR notifier_profile = '')
                """,
                (config.command_center_profile, task_id, target.platform, target.chat_id, target.thread_id),
            )
        after = next((s for s in kb.list_notify_subs(conn, task_id) if _matches_target(s, target)), None)
        return Remediation(slug, task_id, "stale_owner", "backfill_owner", config.mode, True, before, after)
    except Exception as exc:
        return Remediation(slug, task_id, "stale_owner", "backfill_owner", config.mode, False, before, None, str(exc))


def _reset_cursor(conn: sqlite3.Connection, slug: str, task_id: str, target: CommandCenterTarget, max_event_id: int, config: WatchdogConfig, before: dict) -> Remediation:
    try:
        with kb.write_txn(conn):
            conn.execute(
                """
                UPDATE kanban_notify_subs SET last_event_id = ?
                WHERE task_id = ? AND platform = ? AND chat_id = ? AND thread_id = ?
                """,
                (int(max_event_id), task_id, target.platform, target.chat_id, target.thread_id),
            )
        after = next((s for s in kb.list_notify_subs(conn, task_id) if _matches_target(s, target)), None)
        return Remediation(slug, task_id, "stale_cursor", "reset_stale_cursor", config.mode, True, before, after)
    except Exception as exc:
        return Remediation(slug, task_id, "stale_cursor", "reset_stale_cursor", config.mode, False, before, None, str(exc))


def _delete_subscription(
    conn: sqlite3.Connection,
    slug: str,
    task_id: str,
    finding_type: str,
    action: str,
    config: WatchdogConfig,
    *,
    before: dict,
) -> Remediation:
    try:
        platform = str(before.get("platform") or "")
        chat_id = str(before.get("chat_id") or "")
        thread_id = str(before.get("thread_id") or "")
        with kb.write_txn(conn):
            cur = conn.execute(
                """
                DELETE FROM kanban_notify_subs
                WHERE task_id = ? AND platform = ? AND chat_id = ? AND thread_id = ?
                """,
                (task_id, platform, chat_id, thread_id),
            )
        success = bool(cur.rowcount)
        return Remediation(
            slug,
            task_id,
            finding_type,
            action,
            config.mode,
            success,
            before=before,
            after={"deleted": success},
            error=None if success else "subscription row not found",
        )
    except Exception as exc:
        return Remediation(slug, task_id, finding_type, action, config.mode, False, before, None, str(exc))


def _matches_target(sub: dict, target: CommandCenterTarget) -> bool:
    return (
        str(sub.get("platform") or "").lower() == target.platform
        and str(sub.get("chat_id") or "") == target.chat_id
        and str(sub.get("thread_id") or "") == target.thread_id
    )


def _overall_status(run: WatchdogRun) -> str:
    if run.error:
        return "failed"
    if run.target is None:
        return "blocked"
    if run.active_task_count and run.covered_task_count < run.active_task_count:
        return "uncovered"
    if any(r.success for r in run.remediations):
        # Safe repairs are the most actionable run outcome.  Board-level
        # unresolved findings still remain visible in the report's
        # unresolved_issues count, but the operator can tell automatic
        # subscription coverage restoration happened.
        return "repaired"
    unresolved_high = [f for f in run.findings if f.status != "resolved" and f.severity in {"critical", "high"}]
    if unresolved_high:
        # Keep this degraded rather than blocked when active-task coverage is verified;
        # the report still carries critical board/db issues as unresolved issues.
        return "degraded"
    if any(f.status != "resolved" for f in run.findings):
        return "degraded"
    return "healthy"


def run_watchdog(config: Optional[WatchdogConfig] = None, *, audit: bool = True) -> WatchdogRun:
    config = config or WatchdogConfig()
    if config.mode not in VALID_MODES:
        raise ValueError(f"invalid watchdog mode {config.mode!r}: expected one of {sorted(VALID_MODES)}")
    started = int(time.time())
    run = WatchdogRun(
        run_id=f"nw_{started}_{uuid.uuid4().hex[:8]}",
        started_at=started,
        finished_at=None,
        mode=config.mode,
        command_center_profile=config.command_center_profile,
        target=_load_target_from_config(config),
        status="running",
        coverage_percent=0.0,
        active_task_count=0,
        covered_task_count=0,
    )

    audit_conn: Optional[sqlite3.Connection] = None
    if audit:
        audit_conn = _init_audit_db(_audit_db_path(config))

    try:
        if run.target is None:
            for slug in config.scoped_boards:
                run.boards[slug] = BoardReport(slug=slug, db_path=str(_board_db_path(slug)), status="unknown")
                run.findings.append(Finding(slug, "target_unresolved", "critical", "open", board_db_path=str(_board_db_path(slug))))
            return run

        resolved_paths: dict[str, str] = {}
        for slug in config.scoped_boards:
            normed = kb._normalize_board_slug(slug)
            if not normed:
                run.findings.append(Finding(str(slug), "board_missing", "critical", "open", details={"error": "empty slug"}))
                continue
            db_path = str(_board_db_path(normed).resolve())
            if db_path in resolved_paths.values():
                first = next(k for k, v in resolved_paths.items() if v == db_path)
                run.findings.append(Finding(normed, "board_alias_duplicate", "medium", "open", board_db_path=db_path, details={"aliases": [first, normed]}))
            resolved_paths[normed] = db_path
            _find_and_optionally_repair_board(slug=normed, target=run.target, config=config, run=run)
    except Exception as exc:
        run.error = str(exc)
    finally:
        run.finished_at = int(time.time())
        run.coverage_percent = round((run.covered_task_count / run.active_task_count * 100.0), 1) if run.active_task_count else 100.0
        run.status = _overall_status(run)
        if audit_conn is not None:
            try:
                _write_audit(audit_conn, run, config.scoped_boards)
            finally:
                audit_conn.close()
    return run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hermes kanban watchdog", description="Audit/remediate Command Center Kanban notification subscription coverage")
    sub = parser.add_subparsers(dest="action")
    run = sub.add_parser("run", help="Run a subscription coverage audit")
    run.add_argument("--mode", choices=sorted(VALID_MODES), default="detect")
    run.add_argument("--board", action="append", dest="boards", default=None, help="Scoped board slug; repeatable. Defaults to the six Command Center policy boards.")
    run.add_argument("--target-chat-id", default=None, help="Canonical Command Center Telegram chat id")
    run.add_argument("--target-thread-id", default="", help="Canonical Command Center Telegram topic/thread id")
    run.add_argument("--target-user-id", default=None, help="Optional Telegram user id to store on restored rows")
    run.add_argument("--command-center-profile", default="command_center")
    run.add_argument("--no-audit", action="store_true", help="Do not write remediation audit records")
    run.add_argument("--json", action="store_true", help="Emit machine-readable report JSON")
    return parser


def _normalize_negative_option_values(argv: Optional[list[str]]) -> Optional[list[str]]:
    """Allow Telegram chat ids like ``-100...`` as option values.

    argparse treats a value beginning with ``-`` as another option unless the
    user writes ``--target-chat-id=-100...``.  Normalize the common split form
    so the watchdog CLI is pleasant for real Telegram group IDs.
    """
    if argv is None:
        return None
    out: list[str] = []
    i = 0
    value_opts = {"--target-chat-id", "--target-thread-id", "--target-user-id"}
    while i < len(argv):
        item = argv[i]
        if item in value_opts and i + 1 < len(argv) and argv[i + 1].startswith("-") and not argv[i + 1].startswith("--"):
            out.append(f"{item}={argv[i + 1]}")
            i += 2
            continue
        out.append(item)
        i += 1
    return out


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(_normalize_negative_option_values(argv))
    if args.action in {None, "run"}:
        target = None
        if getattr(args, "target_chat_id", None):
            target = CommandCenterTarget(
                platform="telegram",
                chat_id=args.target_chat_id,
                thread_id=getattr(args, "target_thread_id", "") or "",
                user_id=getattr(args, "target_user_id", None),
                source="cli",
            )
        cfg = WatchdogConfig(
            scoped_boards=list(args.boards or DEFAULT_SCOPED_BOARDS),
            command_center_profile=args.command_center_profile,
            target=target,
            mode=args.mode,
        )
        report = run_watchdog(cfg, audit=not bool(getattr(args, "no_audit", False)))
        if getattr(args, "json", False):
            print(json.dumps(report.to_report_dict(), indent=2, ensure_ascii=False))
        else:
            print(report.format_text(), end="")
        return 0 if report.status != "failed" else 1
    parser.print_help()
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
