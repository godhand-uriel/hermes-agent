import json
import os
from pathlib import Path

import pytest

from hermes_cli import kanban_db as kb


SCOPED = [
    "command-center-board",
    "career-development-board",
    "engineering-brand-board",
    "artist-management-board",
    "venture-portfolio-board",
    "research-office-board",
]


@pytest.fixture
def kanban_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("HERMES_KANBAN_HOME", str(home))
    monkeypatch.delenv("HERMES_KANBAN_DB", raising=False)
    monkeypatch.delenv("HERMES_KANBAN_BOARD", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return home


def _target():
    from hermes_cli.kanban_notification_watchdog import CommandCenterTarget

    return CommandCenterTarget(
        platform="telegram",
        chat_id="-100command",
        thread_id="42",
        user_id="u-command",
    )


def _config(**kwargs):
    from hermes_cli.kanban_notification_watchdog import WatchdogConfig

    data = {
        "scoped_boards": list(SCOPED),
        "command_center_profile": "command_center",
        "target": _target(),
        "mode": "repair-safe",
    }
    data.update(kwargs)
    return WatchdogConfig(**data)


def test_repair_safe_adds_missing_command_center_subscriptions_and_ignores_worker_db_pin(kanban_home, monkeypatch):
    from hermes_cli import kanban_notification_watchdog as wd

    kb.create_board("command-center-board")
    kb.create_board("career-development-board")
    with kb.connect_closing(board="command-center-board") as conn:
        t1 = kb.create_task(conn, title="command task", assignee="command_center")
    with kb.connect_closing(board="career-development-board") as conn:
        t2 = kb.create_task(conn, title="career task", assignee="career")

    pinned = kanban_home / "wrong-pinned-worker.db"
    monkeypatch.setenv("HERMES_KANBAN_DB", str(pinned))

    report = wd.run_watchdog(_config(), audit=True)

    assert report.status == "repaired"
    assert report.active_task_count == 2
    assert report.covered_task_count == 2
    assert report.coverage_percent == 100.0
    assert {r.action for r in report.remediations} == {"add_missing_subscription"}
    assert len(report.remediations) == 2
    assert not pinned.exists(), "multi-board watchdog must not follow worker-pinned HERMES_KANBAN_DB"

    monkeypatch.delenv("HERMES_KANBAN_DB", raising=False)
    for board, task_id in (("command-center-board", t1), ("career-development-board", t2)):
        with kb.connect_closing(board=board) as conn:
            subs = kb.list_notify_subs(conn, task_id)
        assert len(subs) == 1
        assert subs[0]["platform"] == "telegram"
        assert subs[0]["chat_id"] == "-100command"
        assert subs[0]["thread_id"] == "42"
        assert subs[0]["user_id"] == "u-command"
        assert subs[0]["notifier_profile"] == "command_center"

    audit_db = kanban_home / "notification_watchdog" / "remediations.db"
    assert audit_db.exists()


def test_detect_mode_reports_missing_stale_orphaned_and_duplicate_without_mutating(kanban_home):
    from hermes_cli import kanban_notification_watchdog as wd

    kb.create_board("command-center-board")
    with kb.connect_closing(board="command-center-board") as conn:
        missing = kb.create_task(conn, title="missing", assignee="a")
        wrong_owner = kb.create_task(conn, title="wrong owner", assignee="a")
        canonical = _target()
        kb.add_notify_sub(
            conn,
            task_id=wrong_owner,
            platform=canonical.platform,
            chat_id=canonical.chat_id,
            thread_id=canonical.thread_id,
            notifier_profile="other_profile",
        )
        stale_cursor = kb.create_task(conn, title="stale cursor", assignee="a")
        kb.add_notify_sub(
            conn,
            task_id=stale_cursor,
            platform=canonical.platform,
            chat_id=canonical.chat_id,
            thread_id=canonical.thread_id,
            notifier_profile="command_center",
        )
        conn.execute(
            "UPDATE kanban_notify_subs SET last_event_id = 999 WHERE task_id = ?",
            (stale_cursor,),
        )
        duplicate = kb.create_task(conn, title="duplicate", assignee="a")
        kb.add_notify_sub(
            conn,
            task_id=duplicate,
            platform=canonical.platform,
            chat_id=canonical.chat_id,
            thread_id=canonical.thread_id,
            notifier_profile="command_center",
        )
        kb.add_notify_sub(
            conn,
            task_id=duplicate,
            platform="telegram",
            chat_id="-100old",
            thread_id="old-topic",
            notifier_profile="command_center",
        )
        kb.add_notify_sub(
            conn,
            task_id="t_orphaned",
            platform="telegram",
            chat_id="-100command",
            thread_id="42",
            notifier_profile="command_center",
        )

    report = wd.run_watchdog(_config(mode="detect"), audit=True)

    finding_types = {f.finding_type for f in report.findings}
    assert "missing_subscription" in finding_types
    assert "stale_owner" in finding_types
    assert "stale_cursor" in finding_types
    assert "duplicate_subscription" in finding_types
    assert "orphaned_subscription" in finding_types
    assert report.remediations == []
    assert report.status in {"uncovered", "blocked"}

    with kb.connect_closing(board="command-center-board") as conn:
        assert kb.list_notify_subs(conn, missing) == []
        owner_sub = kb.list_notify_subs(conn, wrong_owner)[0]
        assert owner_sub["notifier_profile"] == "other_profile"


def test_repair_safe_backfills_empty_owner_and_resets_impossible_cursor(kanban_home):
    from hermes_cli import kanban_notification_watchdog as wd

    kb.create_board("command-center-board")
    with kb.connect_closing(board="command-center-board") as conn:
        t = kb.create_task(conn, title="legacy row", assignee="a")
        kb.add_notify_sub(
            conn,
            task_id=t,
            platform="telegram",
            chat_id="-100command",
            thread_id="42",
            notifier_profile=None,
        )
        conn.execute("UPDATE kanban_notify_subs SET last_event_id = 999 WHERE task_id = ?", (t,))

    report = wd.run_watchdog(_config(), audit=True)

    assert report.status == "repaired"
    assert {r.action for r in report.remediations} == {"backfill_owner", "reset_stale_cursor"}
    with kb.connect_closing(board="command-center-board") as conn:
        sub = kb.list_notify_subs(conn, t)[0]
    assert sub["notifier_profile"] == "command_center"
    assert sub["last_event_id"] == 1  # create_task appends one created event


def test_watchdog_json_report_contains_required_subscription_coverage_fields(kanban_home, capsys):
    from hermes_cli import kanban_notification_watchdog as wd

    kb.create_board("command-center-board")
    with kb.connect_closing(board="command-center-board") as conn:
        kb.create_task(conn, title="missing", assignee="a")

    exit_code = wd.main([
        "run",
        "--mode",
        "detect",
        "--target-chat-id",
        "-100command",
        "--target-thread-id",
        "42",
        "--json",
    ])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["title"] == "SUBSCRIPTION COVERAGE REPORT"
    assert payload["coverage_percent"] == 0.0
    assert payload["total_active_tasks"] == 1
    assert payload["tasks_missing_subscriptions"] == 1
    assert payload["remediations_performed"] == 0
    assert payload["unresolved_issues"] >= 1


def test_repair_cleanup_removes_obvious_orphans_and_noncanonical_duplicates(kanban_home):
    from hermes_cli import kanban_notification_watchdog as wd

    kb.create_board("command-center-board")
    with kb.connect_closing(board="command-center-board") as conn:
        duplicate = kb.create_task(conn, title="duplicate", assignee="a")
        kb.add_notify_sub(
            conn,
            task_id=duplicate,
            platform="telegram",
            chat_id="-100command",
            thread_id="42",
            notifier_profile="command_center",
        )
        kb.add_notify_sub(
            conn,
            task_id=duplicate,
            platform="telegram",
            chat_id="-100old",
            thread_id="old-topic",
            notifier_profile="command_center",
        )
        done = kb.create_task(conn, title="done", assignee="a")
        kb.complete_task(conn, done, summary="done")
        kb.add_notify_sub(
            conn,
            task_id=done,
            platform="telegram",
            chat_id="-100command",
            thread_id="42",
            notifier_profile="command_center",
        )
        max_done_event = conn.execute("SELECT MAX(id) AS max_id FROM task_events WHERE task_id = ?", (done,)).fetchone()["max_id"]
        conn.execute("UPDATE kanban_notify_subs SET last_event_id = ? WHERE task_id = ?", (max_done_event, done))
        kb.add_notify_sub(
            conn,
            task_id="t_orphaned",
            platform="telegram",
            chat_id="-100command",
            thread_id="42",
            notifier_profile="command_center",
        )

    report = wd.run_watchdog(_config(mode="repair-cleanup"), audit=True)

    assert report.status == "repaired"
    assert {"remove_noncanonical_duplicate", "remove_absent_task_orphan", "remove_final_task_subscription"}.issubset(
        {r.action for r in report.remediations if r.success}
    )
    with kb.connect_closing(board="command-center-board") as conn:
        dup_subs = kb.list_notify_subs(conn, duplicate)
        done_subs = kb.list_notify_subs(conn, done)
        orphan_subs = kb.list_notify_subs(conn, "t_orphaned")
    assert [(s["chat_id"], s["thread_id"]) for s in dup_subs] == [("-100command", "42")]
    assert done_subs == []
    assert orphan_subs == []


def test_run_slash_watchdog_accepts_negative_chat_id_and_ignores_global_board(kanban_home, monkeypatch):
    from hermes_cli import kanban as kc

    kb.create_board("command-center-board")
    kb.create_board("career-development-board")
    kb.create_board("wrong-global-board")
    with kb.connect_closing(board="command-center-board") as conn:
        kb.create_task(conn, title="command", assignee="a")
    with kb.connect_closing(board="career-development-board") as conn:
        kb.create_task(conn, title="career", assignee="a")
    with kb.connect_closing(board="wrong-global-board") as conn:
        wrong_task = kb.create_task(conn, title="wrong", assignee="a")
    monkeypatch.setenv("HERMES_KANBAN_DB", str(kanban_home / "worker-pin.db"))

    out = kc.run_slash(
        "--board wrong-global-board watchdog run --mode repair-safe "
        "--watchdog-board command-center-board --watchdog-board career-development-board "
        "--target-chat-id -100command --target-thread-id 42 --json"
    )

    payload = json.loads(out)
    assert payload["status"] == "repaired"
    assert set(payload["boards"].keys()) == {"command-center-board", "career-development-board"}
    assert payload["total_active_tasks"] == 2
    assert not (kanban_home / "worker-pin.db").exists()
    monkeypatch.delenv("HERMES_KANBAN_DB", raising=False)
    with kb.connect_closing(board="wrong-global-board") as conn:
        assert kb.list_notify_subs(conn, wrong_task) == []
