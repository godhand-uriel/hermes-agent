from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_PAGE = REPO_ROOT / "web" / "src" / "pages" / "ReportsPage.tsx"
KANBAN_PLUGIN = REPO_ROOT / "plugins" / "kanban" / "dashboard" / "dist" / "index.js"


def _reports_source() -> str:
    return REPORTS_PAGE.read_text(encoding="utf-8")


def _command_center_source() -> str:
    src = _reports_source()
    return src[src.index("function ExecutiveCommandCenterShell"):src.index("export default function ReportsPage")]


def test_dashboard_workspace_navigation_opens_named_sections_not_sessions():
    src = _command_center_source()
    for label in [
        'label: "Dashboard"',
        'label: "Mission Control"',
        'label: "Finance"',
        'label: "Ventures"',
        'label: "BureauOS"',
        'label: "Parlay Analyzer"',
        'label: "TrustBase"',
        'label: "Career Development"',
        'label: "Research"',
        'label: "Knowledge Vault"',
        'label: "Artist Management"',
        'label: "Engineering Brand"',
        'label: "Hermes Operations"',
        'label: "Settings"',
    ]:
        assert label in src
    assert "Open ${item.label} workspace" in src
    assert "openWorkspace(item.target)" in src
    assert 'href="/sessions"' not in src
    assert "href={`/sessions" not in src


def test_dashboard_workspace_buttons_route_to_real_sections_or_drawers():
    src = _command_center_source()
    for expected in [
        "dashboard-top",
        "mission-control",
        "finance-command",
        "venture-portfolio",
        "bureauos",
        "career-development",
        "research-center",
        "knowledge-vault",
        "engineering-brand",
        "artist-management",
        "hermes-operations",
        "setActiveDrawer({ type: \"task\"",
        "setActiveDrawer({ type: \"venture\"",
        "setActiveDrawer({ type: \"diagnostics\"",
    ]:
        assert expected in src
    assert "Open Workspace" not in src


def test_dashboard_task_report_board_and_profile_cards_have_explicit_destinations():
    src = _reports_source()
    assert "kanbanTaskHref(task.id)" in src
    assert "reportDetailHref" in src
    assert "boardHref(project.project)" in src
    assert "profileHref(task.assignee)" in src
    assert "generatedReportDetailHref(entry.type)" in src


def test_kanban_plugin_accepts_task_and_board_deep_links():
    src = KANBAN_PLUGIN.read_text(encoding="utf-8")
    assert "readDeepLinkParams" in src
    assert "taskParam" in src
    assert "setSelectedTaskId(taskParam)" in src
    assert "boardParam" in src
