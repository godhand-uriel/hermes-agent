from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_PAGE = REPO_ROOT / "web" / "src" / "pages" / "ReportsPage.tsx"
KANBAN_PLUGIN = REPO_ROOT / "plugins" / "kanban" / "dashboard" / "dist" / "index.js"


def _reports_source() -> str:
    return REPORTS_PAGE.read_text(encoding="utf-8")


def test_dashboard_executive_area_cards_route_to_named_sections_not_sessions():
    src = _reports_source()
    expected_targets = {
        "Career Development": "#career-development",
        "BureauOS": "#bureauos",
        "Engineering Brand": "#engineering-brand",
        "Artist Management": "#artist-management",
        "Venture Portfolio": "#venture-portfolio",
        "Hermes Operations": "#hermes-operations",
    }
    for label, target in expected_targets.items():
        assert label in src
        assert target in src
    # The reports dashboard itself must not hard-code Sessions as a fallback for
    # dashboard cards; cards that leave the page should point at explicit pages.
    assert 'href="/sessions"' not in src
    assert "href={`/sessions" not in src


def test_dashboard_task_report_board_and_profile_cards_have_explicit_destinations():
    src = _reports_source()
    assert "kanbanTaskHref(task.id)" in src
    assert "reportDetailHref" in src
    assert "boardHref(project.project)" in src
    assert "profileHref(task.assignee)" in src
    assert "selectedReport" in src


def test_kanban_plugin_accepts_task_and_board_deep_links():
    src = KANBAN_PLUGIN.read_text(encoding="utf-8")
    assert "readDeepLinkParams" in src
    assert "taskParam" in src
    assert "setSelectedTaskId(taskParam)" in src
    assert "boardParam" in src
