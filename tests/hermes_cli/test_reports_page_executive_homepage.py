from pathlib import Path


REPORTS_PAGE = Path(__file__).resolve().parents[2] / "web" / "src" / "pages" / "ReportsPage.tsx"
APP_PAGE = Path(__file__).resolve().parents[2] / "web" / "src" / "App.tsx"


def source() -> str:
    return REPORTS_PAGE.read_text(encoding="utf-8")


def app_source() -> str:
    return APP_PAGE.read_text(encoding="utf-8")


def command_center_source() -> str:
    text = source()
    return text[text.index("function ExecutiveCommandCenterShell"):text.index("export default function ReportsPage")]


def rendered_shell_source() -> str:
    command_center = command_center_source()
    return command_center[command_center.index("return ("):]


def homepage_render_source() -> str:
    text = source()
    start = text.index("      {dashboard && <ExecutiveCommandCenterShell dashboard={dashboard} />}")
    end = text.index('      <div className="sr-only"><PluginSlot name="reports:bottom" /></div>')
    return text[start:end]


def test_homepage_renders_single_command_center_shell_not_legacy_report_shell() -> None:
    homepage = homepage_render_source()
    assert homepage.count("<ExecutiveCommandCenterShell dashboard={dashboard} />") == 1
    for forbidden in ["<DashboardSection", "Project filter", "Search reports and tasks", "Report Library"]:
        assert forbidden not in homepage


def test_command_center_restores_rich_backend_connected_modules() -> None:
    rendered = rendered_shell_source()
    for label in [
        "Executive Brief",
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
        "Activity Feed",
    ]:
        assert label in rendered


def test_dashboard_uses_live_dashboard_api_models_and_not_mock_data() -> None:
    command_center = command_center_source()
    for required in [
        "api.getDashboardV2",
        "dashboard.empireHealth",
        "dashboard.financialMetrics",
        "dashboard.portfolioHealth.projects",
        "dashboard.bureauosApplications",
        "dashboard.careerProgress",
        "dashboard.engineeringMetrics.reviewRequired",
        "dashboard.notificationWatchdog.alerts",
        "dashboard.knowledgeVault",
    ]:
        assert required in source()
    for forbidden in ["mockFinance", "mockPlaid", "fakeBank", "demoNetWorth", "rawAccessToken", "access_token"]:
        assert forbidden not in command_center


def test_finance_command_center_preserves_plaid_registry_wiring_and_controls() -> None:
    text = source()
    command_center = command_center_source()
    finance = command_center[command_center.index('id="finance-command"'):command_center.index('id="venture-portfolio"')]
    for expected in [
        "api.requestPlaidLinkToken",
        "api.exchangePlaidPublicToken",
        "api.syncFinanceRegistry",
        "loadPlaidLinkScript",
        "window.Plaid",
        "window.dispatchEvent(new CustomEvent(\"hermes:dashboard-refresh\"))",
        "Connect Bank",
        "Sync Now",
        "Last Successful Sync",
        "Sync Health",
        "Plaid Environment",
        "Finance Registry via Dashboard API",
        "FinanceSyncConsole",
        "ExecutiveFinanceDashboard",
    ]:
        assert expected in text
    assert "ExecutiveFinanceDashboard finance={dashboard.financialMetrics}" in finance


def test_finance_main_view_shows_executive_metrics_not_metadata_cards() -> None:
    text = source()
    finance_component = text[text.index("function ExecutiveFinanceDashboard"):text.index("function FinanceSyncConsole")]
    sync_console = text[text.index("function FinanceSyncConsole"):text.index("function MiniBars")]
    rendered_finance = command_center_source()[command_center_source().index('id="finance-command"'):command_center_source().index('id="venture-portfolio"')]

    for metric in [
        "Net Worth",
        "Cash Position",
        "Emergency Fund",
        "Investment Portfolio",
        "Monthly Cash Flow",
        "Monthly Burn",
        "Runway",
        "Debt",
        "Savings Rate",
        "Credit Utilization",
    ]:
        assert metric in text
    for metadata_label in ["Provider", "Accounts", "Transactions", "Investments", "Liabilities", "Registry Source", "Registry Location"]:
        assert f'MetricTile compact label="{metadata_label}"' not in sync_console
    assert "Diagnostics" in finance_component
    assert "Diagnostics" in sync_console
    assert "Expanded Registry Metadata" not in rendered_finance
    assert "details open" not in finance_component


def test_sidebar_matches_restored_workspace_navigation() -> None:
    command_center = command_center_source()
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
        'label: "Engineering Brand"',
        'label: "Artist Management"',
        'label: "Hermes Operations"',
        'label: "Settings"',
    ]:
        assert label in command_center
    assert "Open ${item.label} workspace" in command_center
    assert "openWorkspace(item.target)" in command_center
    assert "disabled={item.disabled}" in command_center
    assert "Not wired yet" in command_center


def test_all_open_buttons_are_wired_to_sections_or_drawers() -> None:
    command_center = command_center_source()
    for target in [
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
    ]:
        assert target in command_center
    assert "onClick={() => openWorkspace" in command_center
    assert "setActiveDrawer({ type: \"task\"" in command_center
    assert "setActiveDrawer({ type: \"venture\"" in command_center
    assert "setActiveDrawer({ type: \"diagnostics\"" in command_center


def test_balanced_reference_layout_uses_top_middle_lower_rows() -> None:
    rendered = rendered_shell_source()
    assert "Left sidebar" not in rendered  # implemented structurally, not as placeholder copy
    assert "xl:grid-cols-[88px_1fr]" in rendered
    assert "xl:grid-cols-[220px_1fr]" in rendered
    assert "grid auto-rows-min grid-cols-12" in rendered
    assert "xl:col-span-6" in rendered  # Finance gets larger space
    assert rendered.index("Overall Operating Score") < rendered.index("Finance Command Center") < rendered.index("Career Command") < rendered.index("Hermes Operations")


def test_homepage_does_not_use_reports_shell_branding() -> None:
    text = source()
    app = app_source()
    assert "BureauOS Executive Dashboard V3" not in text
    assert "Executive Command Center" in text
    reports_nav_block = app[app.index('path: "/reports"'):app.index('path: "/models"')]
    assert 'label: "Dashboard"' in reports_nav_block
    assert 'label: "Reports"' not in reports_nav_block


def test_executive_dashboard_excludes_regtech_products_from_homepage() -> None:
    text = source()
    for forbidden in ["GovShield", "HIPAAOS", "AI Governance", "CloudComply", "VendorRisk", "FedRAMP Navigator", "FireInspect", "DOT Command", "MedWasteTrack"]:
        assert forbidden not in text
