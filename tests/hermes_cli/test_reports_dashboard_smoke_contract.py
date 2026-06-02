from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_PAGE = REPO_ROOT / "web" / "src" / "pages" / "ReportsPage.tsx"


def source() -> str:
    return REPORTS_PAGE.read_text(encoding="utf-8")


def test_reports_dashboard_first_load_empty_loading_and_error_states_are_visible() -> None:
    text = source()

    assert "Loading BureauOS Executive Dashboard V3" in text
    assert "Dashboard data failed to load" in text
    assert "buildFallbackDashboard(createEmptyReports(project, query))" in text
    assert "No dashboard data matched" in text
    assert "Try removing filters, completing kanban tasks" in text


def test_reports_dashboard_smoke_sections_include_executive_command_center() -> None:
    text = source()
    command_brief = text.index('title="Command Brief"')
    filter_controls = text.index("Project filter")

    assert command_brief < filter_controls
    for section in [
        "Command Brief",
        "Career Development",
        "BureauOS",
        "Engineering Brand",
        "Artist Management",
        "Venture Portfolio",
        "Reports",
        "Hermes Operations",
    ]:
        assert f'title="{section}"' in text

    for target in [
        "#career-development",
        "#bureauos",
        "#engineering-brand",
        "#artist-management",
        "#venture-portfolio",
        "#hermes-operations",
    ]:
        assert target in text


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


def test_reports_dashboard_filter_action_is_disabled_while_loading() -> None:
    text = source()

    assert "onClick={load} disabled={loading}" in text
    assert "Refresh" in text
    assert "Apply" in text
