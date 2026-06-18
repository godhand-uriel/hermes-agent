from pathlib import Path


REPORTS_PAGE = Path(__file__).resolve().parents[2] / "web" / "src" / "pages" / "ReportsPage.tsx"


def source() -> str:
    return REPORTS_PAGE.read_text(encoding="utf-8")


def test_command_brief_is_first_dashboard_section() -> None:
    text = source()
    command_brief = text.index('title="Command Brief"')
    filter_card = text.index("Project filter")
    hermes_ops = text.index('title="Hermes Operations"')

    assert command_brief < filter_card
    assert command_brief < hermes_ops


def test_required_executive_areas_are_present() -> None:
    text = source()
    for title in [
        "Command Brief",
        "Career Development",
        "BureauOS",
        "Engineering Brand",
        "Artist Management",
        "Venture Portfolio",
        "Reports",
        "Hermes Operations",
    ]:
        assert f'title="{title}"' in text


def test_raw_task_metrics_are_scoped_to_hermes_operations() -> None:
    text = source()
    dashboard_render = text[text.index("      {dashboard && ("):]
    operations_start = dashboard_render.index('title="Hermes Operations"')
    before_operations = dashboard_render[:operations_start]

    for task_metric in [
        "Completed tasks",
        "Review required",
        "Active projects",
        "Weekly report files",
        "Deployments",
        "GitHub updates",
    ]:
        assert task_metric not in before_operations


def test_empty_placeholder_sections_are_hidden_from_executive_dashboard() -> None:
    text = source()

    assert "shouldShowDeploymentStatus" in text
    assert "shouldShowGithubActivity" in text
    assert "shouldShowReportLibrary" in text
    assert "dashboard.engineeringMetrics.deploymentStatus.length > 0" in text
    assert "dashboard.engineeringMetrics.githubActivity.length > 0" in text
    assert "dashboard.weeklyReports.completionReports.length > 0" in text


def test_venture_portfolio_copy_uses_registered_venture_language() -> None:
    text = source()

    assert "Registered ventures" in text
    assert "Portfolio registry" in text
    assert "No registered ventures" in text
    assert "No active projects" not in text
