from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_PAGE = REPO_ROOT / "web" / "src" / "pages" / "ReportsPage.tsx"


def source() -> str:
    return REPORTS_PAGE.read_text(encoding="utf-8")


def command_center_source() -> str:
    text = source()
    return text[text.index("function ExecutiveCommandCenterShell"):text.index("export default function ReportsPage")]


def test_reports_dashboard_first_load_empty_loading_and_error_states_are_visible() -> None:
    text = source()
    assert "Loading Hermes OS Executive Command Center" in text
    assert "Dashboard data failed to load" in text
    assert "buildFallbackDashboard(createEmptyReports(project, query))" in text
    assert "No Activity Yet" in text
    assert "No Data Yet" in text


def test_reports_dashboard_smoke_sections_include_restored_command_center() -> None:
    text = source()
    command_center = text.index("function ExecutiveCommandCenterShell")
    page_render = text.index("export default function ReportsPage")
    assert command_center < page_render
    for section in [
        "Executive Command Center",
        "Empire Health",
        "Decision Queue",
        "Current Blockers",
        "Mission Control",
        "Finance Command Center",
        "Business Ventures Overview",
        "BureauOS Overview",
        "Venture Pipeline",
        "Career Command",
        "Engineering Brand",
        "Artist Management",
        "Research Center",
        "Knowledge Vault",
        "Hermes Operations",
    ]:
        assert section in text
    rendered = command_center_source()[command_center_source().index("return ("):]
    assert "Project filter" not in rendered
    assert "Command Brief" not in rendered


def test_reports_dashboard_clickable_routes_never_fall_back_to_sessions() -> None:
    text = source()
    assert 'href="/sessions"' not in text
    assert 'to="/sessions"' not in text
    assert "href={`/sessions" not in text
    assert "to={`/sessions" not in text
    assert "kanbanTaskHref(task.id)" in text
    assert "boardHref(project.project)" in text
    assert "profileHref(task.assignee)" in text
    assert "reportDetailHref(report)" in text
    assert "generatedReportDetailHref(entry.type)" in text


def test_reports_dashboard_detail_views_render_readable_reports_not_raw_json_first() -> None:
    text = source()
    readable_detail = text[text.index("function GeneratedReportDetail"):text.index("function ReportFileDetail")]
    assert "buildReadableReport(report)" in readable_detail
    assert "Key wins" in readable_detail
    assert "Risks / blockers" in readable_detail
    assert "Recommendations" in readable_detail
    assert "Next actions" in readable_detail
    assert "Related missions / tasks" in readable_detail
    assert "Developer raw JSON" in readable_detail
    assert readable_detail.index("Key wins") < readable_detail.index("Developer raw JSON")


def test_reports_dashboard_header_shell_is_hidden_for_executive_view() -> None:
    text = source()
    reports_page = text[text.index("export default function ReportsPage"):]
    provider = (REPO_ROOT / "web" / "src" / "contexts" / "PageHeaderProvider.tsx").read_text(encoding="utf-8")
    assert "setTitle(\"\")" in reports_page
    assert "hideHeader = titleOverride === \"\"" in provider
    assert "{!hideHeader ? <header" in provider
    assert "Apply" not in reports_page
