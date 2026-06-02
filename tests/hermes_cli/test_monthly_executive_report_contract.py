from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_SERVER = REPO_ROOT / "hermes_cli" / "web_server.py"
API_TYPES = REPO_ROOT / "web" / "src" / "lib" / "api.ts"
DOCS = REPO_ROOT / "docs" / "hermes-os" / "DASHBOARD_V2_REPORTS_API.md"


def test_monthly_executive_review_is_a_generated_report_type() -> None:
    server = WEB_SERVER.read_text(encoding="utf-8")

    assert '"monthly_executive_review"' in server
    assert '"Monthly Executive Review"' in server
    assert '"monthly executive review"' in server


def test_reports_ui_type_union_includes_monthly_executive_review() -> None:
    api = API_TYPES.read_text(encoding="utf-8")

    assert '| "monthly_executive_review"' in api


def test_generated_report_docs_document_monthly_cron_schedule() -> None:
    docs = DOCS.read_text(encoding="utf-8")

    assert "monthly_executive_review" in docs
    assert "Monthly Executive Review" in docs
    assert "0 20 1 * *" in docs
