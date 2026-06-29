from pathlib import Path


REPORTS_PAGE = Path(__file__).resolve().parents[2] / "web" / "src" / "pages" / "ReportsPage.tsx"
APP_PAGE = Path(__file__).resolve().parents[2] / "web" / "src" / "App.tsx"


def source() -> str:
    return REPORTS_PAGE.read_text(encoding="utf-8")


def app_source() -> str:
    return APP_PAGE.read_text(encoding="utf-8")


def homepage_render_source() -> str:
    text = source()
    start = text.index("      {dashboard && <ExecutiveCommandCenterShell dashboard={dashboard} />}")
    end = text.index('      <div className="sr-only"><PluginSlot name="reports:bottom" /></div>')
    return text[start:end]


def test_homepage_renders_only_executive_command_center_dashboard() -> None:
    homepage = homepage_render_source()

    assert homepage.count("<ExecutiveCommandCenterShell dashboard={dashboard} />") == 1
    assert "<DashboardSection" not in homepage
    assert "Project filter" not in homepage
    assert "Search reports and tasks" not in homepage


def test_required_executive_areas_are_present_inside_command_center() -> None:
    text = source()
    command_center = text[text.index("function ExecutiveCommandCenterShell"):text.index("export default function ReportsPage")]
    for label in [
        "Executive Command Center",
        "Mission Control",
        "Business Ventures",
        "BureauOS",
        "Parlay Analyzer",
        "TrustBase",
        "Career Development",
        "Engineering Brand",
        "Artist Management",
        "Hermes Operations",
        "Finance Command Center",
        "Venture Pipeline",
        "Research Center",
        "Knowledge Vault",
    ]:
        assert label in command_center


def test_command_center_uses_target_sidebar_structure() -> None:
    command_center = source()[source().index("function ExecutiveCommandCenterShell"):source().index("export default function ReportsPage")]

    for label in [
        'label: "Dashboard"',
        'label: "Mission Control"',
        'label: "Business Ventures"',
        'children: ["BureauOS", "Parlay Analyzer", "TrustBase"]',
        'label: "Career Development"',
        'label: "Finance"',
        'label: "Research"',
        'label: "Knowledge Vault"',
        'label: "Engineering Brand"',
        'label: "Artist Management"',
        'label: "Hermes Operations"',
        'label: "Settings"',
    ]:
        assert label in command_center


def test_business_ventures_cards_are_limited_to_target_registered_ventures() -> None:
    command_center = source()[source().index("function ExecutiveCommandCenterShell"):source().index("export default function ReportsPage")]

    assert "const businessVentures =" in command_center
    assert 'displayName: "TrustBase"' in command_center
    assert "Frontend Streaming Platform" not in command_center
    business_ventures_section = command_center[command_center.index("const businessVentures ="):command_center.index("const sidebar =")]
    for forbidden in [
        "command_center",
        "engineering_lab",
        "career_development",
        "venture_portfolio",
        "engineering_brand",
        "artist_management",
        "consulting_office",
    ]:
        assert forbidden not in business_ventures_section


def test_bureauos_is_one_compact_application_overview() -> None:
    text = source()
    command_center = text[text.index("function ExecutiveCommandCenterShell"):text.index("export default function ReportsPage")]

    assert "BureauOS Overview" in command_center
    for column in ["Application", "Stage", "Risk", "Last Activity"]:
        assert column in text
    assert "bureauosApplications" in command_center
    assert "app.name" in text
    assert "BureauOSRows" in text


def test_homepage_does_not_use_reports_shell_branding() -> None:
    text = source()
    app = app_source()

    assert "BureauOS Executive Dashboard V3" not in text
    assert "Hermes OS Executive Command Center" in text
    reports_nav_block = app[app.index('path: "/reports"'):app.index('path: "/models"')]
    assert 'label: "Dashboard"' in reports_nav_block
    assert 'label: "Reports"' not in reports_nav_block


def test_raw_task_metrics_are_scoped_to_hermes_operations() -> None:
    command_center = source()[source().index("function ExecutiveCommandCenterShell"):source().index("export default function ReportsPage")]
    operations_start = command_center.index("Hermes Operations")
    before_operations = command_center[:operations_start]

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
    homepage = homepage_render_source()

    assert "Deployment status" not in homepage
    assert "GitHub activity" not in homepage
    assert "Report Library" not in homepage


def test_legacy_reports_dashboard_sections_are_removed_from_homepage() -> None:
    homepage = homepage_render_source()

    for forbidden in [
        "Command Brief",
        "Recent completed work",
        "Recent Completed Work",
        "Review queue",
        "Reports",
        "Report Library",
        "Completion reports",
        "Latest report links",
        'title="Career Development"',
        'title="Artist Management"',
        'title="Venture Portfolio"',
    ]:
        assert forbidden not in homepage


def test_venture_portfolio_copy_uses_registered_venture_language() -> None:
    text = source()

    assert "Registered ventures" in text
    assert "Portfolio registry" in text
    assert "No registered ventures" in text
    assert "No ventures configured." in text
    assert "No active projects" not in text


def test_executive_command_center_shell_matches_founder_operating_system_brief() -> None:
    text = source()

    for label in [
        "Executive Command Center",
        "Empire Health",
        "Decisions Needed",
        "Current Blockers",
        "Mission Control",
        "Finance Command Center",
        "Business Ventures",
        "Venture Pipeline",
        "Career Command",
        "Research Center",
        "Knowledge Vault",
        "Bloomberg Terminal + Linear + Notion + Jarvis",
    ]:
        assert label in text


def test_executive_dashboard_excludes_regtech_products_from_business_ventures() -> None:
    text = source()

    for forbidden in [
        "GovShield",
        "HIPAAOS",
        "AI Governance",
        "CloudComply",
        "VendorRisk",
        "FedRAMP Navigator",
        "FireInspect",
        "DOT Command",
        "MedWasteTrack",
    ]:
        assert forbidden not in text


def test_executive_dashboard_does_not_hardcode_intelligence_outputs() -> None:
    command_center = source()[source().index("function ExecutiveCommandCenterShell"):source().index("export default function ReportsPage")]

    for forbidden in [
        "82<span",
        "P0 Select first BureauOS MVP",
        "P0 Approve TrustBase validation",
        "Veteran Benefits research incomplete",
        "TrustBase onboarding undefined",
        "Parlay workflow not finalized",
        "Gallery outreach awaiting response",
        "Define next operating milestone",
        "Connected</span>",
        "Warning</span>",
        "Total Notes",
    ]:
        assert forbidden not in command_center


def test_executive_dashboard_uses_source_backed_intelligence_helpers() -> None:
    command_center = source()[source().index("function ExecutiveCommandCenterShell"):source().index("export default function ReportsPage")]

    for required in [
        "missionPriorities",
        "decisionItems",
        "blockerItems",
        "empireHealthItems",
        "researchItems",
        "knowledgeVaultItems",
        "backendIntegrationItems",
        "formatDecisionItem",
        "formatBlockerItem",
        "BureauOS application registry",
        "No Activity Yet",
        "No Metrics Yet",
        "Not Started",
    ]:
        assert required in command_center


def test_bureauos_overview_does_not_use_arbitrary_progress_bars() -> None:
    command_center = source()[source().index("function ExecutiveCommandCenterShell"):source().index("export default function ReportsPage")]
    bureauos_section = command_center[command_center.index("BureauOS Overview"):command_center.index("Venture Pipeline")]

    assert "Math.max" not in bureauos_section
    assert "90 - Math.abs" not in bureauos_section
    assert "BureauOSRows" in source()
    assert "bureauRows.map" in source()


def test_quick_capture_buttons_open_drawer_forms() -> None:
    text = source()
    command_center = text[text.index("function ExecutiveCommandCenterShell"):text.index("export default function ReportsPage")]

    for action in ["New Task", "New Research", "New Venture", "New Note", "Capture Idea"]:
        assert action in command_center
    assert "setActiveDrawer({ type: \"quick-capture\"" in command_center
    assert "Quick Capture Form" in text
    assert "textarea" in text
    assert "Capture locally" in text


def test_sidebar_navigation_buttons_scroll_to_sections_and_disable_unwired_settings() -> None:
    command_center = source()[source().index("function ExecutiveCommandCenterShell"):source().index("export default function ReportsPage")]

    assert "scrollToSection" in command_center
    assert "document.getElementById(targetId)?.scrollIntoView" in command_center
    assert "aria-expanded={businessNavExpanded}" in command_center
    assert "Not wired yet" in command_center
    assert "disabled={item.disabled}" in command_center
    for target in [
        "dashboard-top",
        "mission-control",
        "venture-portfolio",
        "bureauos",
        "career-development",
        "finance-command",
        "knowledge-vault",
        "engineering-brand",
        "artist-management",
        "hermes-operations",
    ]:
        assert target in command_center


def test_venture_rows_open_detail_drawer_and_show_required_readable_columns() -> None:
    command_center = source()[source().index("function VentureRows"):source().index("function QuickCaptureBar")]
    shell = source()[source().index("function ExecutiveCommandCenterShell"):source().index("export default function ReportsPage")]

    assert "onOpen" in command_center
    assert "aria-label={`Open ${venture.displayName} details`}" in command_center
    assert "setActiveDrawer({ type: \"venture\"" in shell
    for label in ["Venture", "Stage", "Confidence", "Next Milestone", "Blockers", "Last Activity", "Action"]:
        assert label in command_center or label in shell
    assert "MetricTile compact label=\"Stage\"" not in command_center


def test_mission_control_renders_compact_rows_not_raw_task_bodies() -> None:
    command_center = source()[source().index("function ExecutiveCommandCenterShell"):source().index("export default function ReportsPage")]
    mission = command_center[command_center.index("id=\"mission-control\""):command_center.index("id=\"venture-portfolio\"")]

    mission_component = source()[source().index("function MissionControlRows"):source().index("function VentureRows")]

    assert "MissionControlRows" in mission
    assert "Priority" in mission_component
    assert "Title" in mission_component
    assert "Status" in mission_component
    assert "Owner" in mission_component
    assert "Due / age" in mission_component
    assert "View details" in mission_component
    assert "line-clamp" in mission_component
    assert "task.summary" not in mission
    assert "No full task body" in source()


def test_visible_dashboard_buttons_have_actions_or_disabled_tooltips() -> None:
    text = source()
    command_center = text[text.index("function ExecutiveCommandCenterShell"):text.index("export default function ReportsPage")]

    assert "setTitle(\"\")" in text
    assert command_center.count("<button") > 0
    assert "onClick={() => scrollToSection" in command_center
    assert "onClick={() => setActiveDrawer" in command_center
    assert "disabled={item.disabled}" in command_center
    assert "title={item.disabled ? \"Not wired yet\"" in command_center


def test_redesign_top_row_contains_activity_feed_as_executive_widget() -> None:
    command_center = source()[source().index("function ExecutiveCommandCenterShell"):source().index("export default function ReportsPage")]
    top_grid = command_center[command_center.index("xl:grid-cols-12"):command_center.index("id=\"mission-control\"")]

    for label in ["Executive Brief", "Empire Health", "Decisions Needed", "Current Blockers", "Activity Feed", "QuickCaptureBar"]:
        assert label in top_grid
    assert "xl:grid-cols-[148px_1fr]" in command_center
    assert "xl:grid-cols-[72px_1fr]" in command_center
    assert "setSidebarCollapsed" in command_center


def test_mission_control_uses_labeled_progress_flow_not_heatmap() -> None:
    command_center = source()[source().index("function ExecutiveCommandCenterShell"):source().index("export default function ReportsPage")]
    mission = command_center[command_center.index("id=\"mission-control\""):command_center.index("id=\"venture-portfolio\"")]

    for label in ["P0/P1 Priorities", "Due Today", "Review Required", "Blocked", "Recently Completed"]:
        assert label in mission
    assert "Priority Heat Map" not in mission
    assert "Array.from({ length: 28 })" not in mission
    assert mission.count("<ProgressBar") >= 3
    assert "completed" in mission and "Open drawer" in mission


def test_venture_pipeline_renders_all_required_funnel_stages_even_when_counts_are_zero() -> None:
    command_center = source()[source().index("function ExecutiveCommandCenterShell"):source().index("export default function ReportsPage")]

    assert "const pipelineStages" in command_center
    for stage in ["Research", "Validation", "MVP", "Build", "Production", "Paying Clients", "Scale"]:
        assert stage in command_center
    assert "<CompactStageSummary stages={pipelineStages}" in command_center


def test_engineering_brand_and_artist_management_are_separate_panels() -> None:
    command_center = source()[source().index("function ExecutiveCommandCenterShell"):source().index("export default function ReportsPage")]
    brand = command_center[command_center.index("id=\"engineering-brand\""):command_center.index("id=\"research-center\"")]
    artist = command_center[command_center.index("id=\"artist-management\""):command_center.index("id=\"hermes-operations\"")]

    assert "Content Pipeline" in brand
    assert "Collector + Gallery Pipeline" in artist
    assert "Engineering Brand / Artist Management" not in command_center
    for label in ["Ideas", "Recording", "Editing", "Published"]:
        assert label in brand
    for label in ["Collectors", "Outreach", "Inventory", "Revenue"]:
        assert label in artist


def test_engineering_diagnostics_are_scoped_inside_operations_panel() -> None:
    command_center = source()[source().index("function ExecutiveCommandCenterShell"):source().index("export default function ReportsPage")]
    operations = command_center[command_center.index("id=\"hermes-operations\""):command_center.index("</ExecutivePanel></div>", command_center.index("id=\"hermes-operations\""))]
    rendered_before_operations = command_center[command_center.index("return ("):command_center.index("id=\"hermes-operations\"")]

    assert "OperationsHealthStrip" in operations
    assert "diagnostics" in operations
    assert "No GitHub report source" not in rendered_before_operations
    assert "No notification audit source" not in rendered_before_operations
    assert "No deployment source" not in rendered_before_operations
    assert "<ExecutivePanel eyebrow=\"NOC\"" not in command_center


def test_research_and_knowledge_vault_show_count_based_executive_metrics() -> None:
    command_center = source()[source().index("function ExecutiveCommandCenterShell"):source().index("export default function ReportsPage")]
    research = command_center[command_center.index("id=\"research-center\""):command_center.index("id=\"knowledge-vault\"")]
    knowledge = command_center[command_center.index("id=\"knowledge-vault\""):command_center.index("id=\"artist-management\"")]

    for label in ["Market Intelligence", "Competitive Intelligence", "Open Questions", "Opportunities"]:
        assert label in research
    for label in ["Recently Modified Notes", "Most Referenced Notes", "Recent Decisions", "Knowledge Health"]:
        assert label in knowledge
    assert "Knowledge Health" in knowledge


def test_viewport_layout_uses_dense_twelve_column_grid_and_hides_reports_shell() -> None:
    text = source()
    command_center = text[text.index("function ExecutiveCommandCenterShell"):text.index("export default function ReportsPage")]
    reports_page = text[text.index("export default function ReportsPage"):]

    assert "min-h-[calc(100vh-4rem)]" in command_center
    assert "xl:grid-cols-12" in command_center
    assert "auto-rows-min" in command_center
    assert "setAfterTitle(null)" in reports_page
    assert "Hermes OS Executive Command Center</span>" not in reports_page


def test_bureauos_empty_state_uses_executive_labels_not_setup_instructions() -> None:
    text = source()
    bureau_component = text[text.index("function BureauOSRows"):text.index("function CompactStageSummary")]

    assert "BUREAUOS_APPLICATION_NAMES.map" in bureau_component
    assert "Not Started" in bureau_component
    assert "Low" in bureau_component
    assert "No Activity" in bureau_component
    assert "bureauos_application_registry.applications" not in bureau_component
    assert "$HERMES_HOME/ventures/bureauos_applications.json" not in bureau_component


def test_operations_diagnostics_are_drawer_only_and_quick_capture_is_above_mission_control() -> None:
    command_center = source()[source().index("function ExecutiveCommandCenterShell"):source().index("export default function ReportsPage")]
    quick_capture_index = command_center.index("QuickCaptureBar")
    mission_index = command_center.index("id=\"mission-control\"")
    operations = command_center[command_center.index("id=\"hermes-operations\""):command_center.index("</ExecutivePanel></div>", command_center.index("id=\"hermes-operations\""))]

    assert quick_capture_index < mission_index
    assert "backendIntegrationItems.map" not in operations
    assert "setActiveDrawer({ type: \"diagnostics\"" in operations


def test_executive_empty_states_use_human_labels_not_backend_setup_instructions() -> None:
    command_center = source()[source().index("function ExecutiveCommandCenterShell"):source().index("export default function ReportsPage")]
    diagnostics = command_center[command_center.index("const backendIntegrationItems"):command_center.index("const operationsCards")]
    executive_render = command_center[command_center.index("return ("):]
    executive_without_diagnostics = executive_render.replace(diagnostics, "")

    for human_label in ["Not Started", "No Data Yet", "No Activity Yet", "No Metrics Yet"]:
        assert human_label in command_center

    for forbidden in ["Missing source", "Missing registry", "POST /api", "Missing milestone source", "Missing deployment source", "Finance registry missing", "BureauOS Application Registry missing"]:
        assert forbidden not in executive_without_diagnostics


def test_bureauos_always_renders_fixed_application_rows_with_executive_empty_values() -> None:
    text = source()
    command_center = text[text.index("function ExecutiveCommandCenterShell"):text.index("export default function ReportsPage")]
    bureauos = command_center[command_center.index("id=\"bureauos\""):command_center.index("id=\"venture-pipeline\"")]

    for app_name in ["DMV Navigator", "Veteran Benefits Navigator", "Insurance Denial Navigator", "Tenant Rights Navigator", "Small Business Compliance Navigator"]:
        assert app_name in text
    for column in ["Application", "Stage", "Risk", "Last Activity"]:
        assert column in text
    for empty in ["Not Started", "Low", "No Activity"]:
        assert empty in text
    assert "bureauRows.map" in text
    assert "bureauRows.length ?" not in bureauos


def test_pipeline_is_compact_stage_summary_not_tall_funnel() -> None:
    text = source()
    command_center = text[text.index("function ExecutiveCommandCenterShell"):text.index("export default function ReportsPage")]
    pipeline = command_center[command_center.index("id=\"venture-pipeline\""):command_center.index("id=\"finance-command\"")]

    assert "CompactStageSummary" in pipeline
    assert "Stage Funnel" not in pipeline
    for stage in ["Research", "Validation", "MVP", "Build", "Production", "Paying Clients", "Scale"]:
        assert stage in text


def test_lower_dashboard_uses_three_column_operating_layout() -> None:
    command_center = source()[source().index("function ExecutiveCommandCenterShell"):source().index("export default function ReportsPage")]
    lower = command_center[command_center.index("id=\"executive-operating-grid\""):command_center.index("</div>\n\n      </div>", command_center.index("id=\"executive-operating-grid\""))]

    assert "LEFT COLUMN" in lower
    assert "CENTER COLUMN" in lower
    assert "RIGHT COLUMN" in lower
    assert "xl:grid-cols-[4fr_5fr_3fr]" in lower
    assert lower.index("id=\"mission-control\"") < lower.index("id=\"venture-portfolio\"") < lower.index("id=\"finance-command\"")




def test_finance_command_center_manual_sync_controls_and_feedback() -> None:
    text = source()
    command_center = text[text.index("function ExecutiveCommandCenterShell"):text.index("export default function ReportsPage")]
    finance = command_center[command_center.index("id=\"finance-command\""):command_center.index("id=\"career-development\"")]

    for expected in [
        "Sync Now",
        "Connect Bank",
        "Connecting...",
        "Plaid Environment",
        "Bank connected and synced successfully.",
        "Bank connection failed.",
        "Synced Successfully",
        "Sync Failed",
        "Connecting…",
        "Downloading Accounts…",
        "Downloading Transactions…",
        "Updating Registry…",
        "Refreshing Dashboard…",
        "Completed",
        "Recent Syncs",
        "Registry Metadata",
        "Sync Health",
        "Last Successful Sync",
    ]:
        assert expected in text
    assert "api.syncFinanceRegistry" in command_center
    assert "api.requestPlaidLinkToken" in command_center
    assert "api.exchangePlaidPublicToken" in command_center
    assert "loadPlaidLinkScript" in text
    assert "window.Plaid" in command_center
    assert "window.dispatchEvent(new CustomEvent(\"hermes:dashboard-refresh\"))" in command_center
    assert "disabled={syncing || connectingBank}" in text
    assert "syncingFinance" in finance
    assert "connectingBank" in finance
    assert "FinanceSyncConsole" in finance


def test_collapsed_sidebar_uses_readable_short_labels() -> None:
    command_center = source()[source().index("function ExecutiveCommandCenterShell"):source().index("export default function ReportsPage")]
    for label in ["Dash", "Ctrl", "Vent", "Career", "Fin", "Res", "Vault", "Brand", "Artist", "Ops", "Settings"]:
        assert f'shortLabel: "{label}"' in command_center
    assert "item.label.slice" not in command_center
    assert "item.label.split" not in command_center
