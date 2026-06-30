"""Tests for Learning Registry and Obsidian sync projection."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

from hermes_cli.learning_registry import (
    audit_learning_notes,
    debug_udemy_browser_dom,
    import_learning_evidence,
    import_udemy_browser_html,
    learning_registry_status,
    parse_learning_notes,
    project_learning_summary,
    sync_obsidian_learning_registry,
    sync_udemy_browser_learning,
    udemy_browser_status,
    stable_id,
)


class _FakeUdemyPage:
    def __init__(self, html: str, *, url: str = "about:blank", goto_errors: list[Exception] | None = None) -> None:
        self.html = html
        self.url = url
        self.goto_errors = list(goto_errors or [])
        self.goto_calls: list[tuple[str, str | None]] = []
        self.wait_for_selector_calls: list[tuple[str, int | None]] = []

    def goto(self, url: str, wait_until: str | None = None) -> None:
        self.goto_calls.append((url, wait_until))
        self.url = url
        if self.goto_errors:
            raise self.goto_errors.pop(0)

    def wait_for_selector(self, selector: str, timeout: int | None = None) -> None:
        self.wait_for_selector_calls.append((selector, timeout))
        if "course-card" not in self.html and "/course/" not in self.html:
            raise TimeoutError("course card not found")

    def content(self) -> str:
        return self.html

    def title(self) -> str:
        match = self.html and __import__("re").search(r"<title>(.*?)</title>", self.html, flags=__import__("re").IGNORECASE | __import__("re").DOTALL)
        return match.group(1).strip() if match else "Udemy My Learning"


class _FakeUdemyContext:
    def __init__(self, page: _FakeUdemyPage) -> None:
        self.pages = [page]
        self.storage_state_calls: list[str] = []

    def new_page(self) -> _FakeUdemyPage:
        return self.pages[0]

    def storage_state(self, path: str | None = None) -> None:
        self.storage_state_calls.append(path or "")


class _FakeUdemyBrowser:
    def __init__(self, context: _FakeUdemyContext) -> None:
        self.contexts = [context]
        self.closed = False

    def new_context(self, **_kwargs):
        return self.contexts[0]

    def close(self) -> None:
        self.closed = True


def install_fake_playwright(monkeypatch, *, html: str = "", fail_cdp: bool = False, page_url: str = "about:blank", goto_errors: list[Exception] | None = None) -> dict[str, object]:
    page = _FakeUdemyPage(html, url=page_url, goto_errors=goto_errors)
    context = _FakeUdemyContext(page)
    browser = _FakeUdemyBrowser(context)
    calls: dict[str, object] = {"connect_over_cdp": [], "launch": [], "browser": browser, "context": context, "page": page}

    class _Chromium:
        def connect_over_cdp(self, cdp_url: str):
            calls["connect_over_cdp"].append(cdp_url)  # type: ignore[index]
            if fail_cdp:
                raise ConnectionError("endpoint unavailable with cookie=secret-token")
            return browser

        def launch(self, **kwargs):
            calls["launch"].append(kwargs)  # type: ignore[index]
            return browser

    class _Playwright:
        chromium = _Chromium()

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    sync_api = types.ModuleType("playwright.sync_api")
    setattr(sync_api, "sync_playwright", lambda: _Playwright())
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)
    return calls


def write_learning_note(path: Path, *, progress: int = 15) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "type: learning\n"
        "provider: AWS\n"
        "certification: AWS Solutions Architect Associate\n"
        "course: AWS SAA Study Plan\n"
        "module: VPC fundamentals\n"
        "status: in_progress\n"
        f"progress: {progress}\n"
        "last_studied: 2026-06-29\n"
        "study_hours: 1.5\n"
        "weekly_study_hours: 4\n"
        "next_action: Complete VPC module\n"
        "---\n"
        "# AWS SAA\n\nStudy notes for VPC and IAM.\n",
        encoding="utf-8",
    )


def test_obsidian_learning_note_parses_into_learning_registry(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    write_learning_note(vault / "Learning" / "AWS" / "AWS SAA.md")

    registry, report = parse_learning_notes(vault, now="2026-06-30T00:00:00Z")

    assert report["notes_scanned"] == 1
    assert report["learning_notes"] == 1
    assert registry["sources"]["obsidian"]["status"] == "Connected"
    assert registry["providers"][0]["name"] == "AWS"
    assert registry["certifications"][0]["name"] == "AWS Solutions Architect Associate"
    assert registry["certifications"][0]["progress_percent"] == 15
    assert registry["certifications"][0]["evidence_path"] == "Learning/AWS/AWS SAA.md"
    assert registry["courses"][0]["name"] == "AWS SAA Study Plan"
    assert registry["modules"][0]["name"] == "VPC fundamentals"
    assert registry["study_sessions"][0]["hours"] == 1.5
    assert registry["learning_streak"]["last_studied"] == "2026-06-29"
    assert registry["sources"]["microsoft_learn"]["status"] == "Not connected"
    assert "Export Microsoft Learn" in registry["sources"]["microsoft_learn"]["needed_user_action"]
    assert registry["sources"]["aws_skill_builder"]["status"] == "Not connected"
    assert "Export AWS Skill Builder" in registry["sources"]["aws_skill_builder"]["needed_user_action"]


def test_duplicate_learning_notes_do_not_duplicate_records(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    write_learning_note(vault / "Learning" / "AWS" / "AWS SAA.md")
    write_learning_note(vault / "Learning" / "AWS" / "AWS SAA duplicate.md", progress=20)

    registry, _report = parse_learning_notes(vault, now="2026-06-30T00:00:00Z")

    assert len(registry["providers"]) == 1
    assert len(registry["certifications"]) == 1
    assert len(registry["courses"]) == 1
    assert len(registry["modules"]) == 1
    assert registry["certifications"][0]["progress_percent"] in {15, 20}


def test_learning_registry_projects_executive_summary_into_career_registry(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    career_path.write_text(json.dumps({"current_role": "Support Engineer", "today_tasks": []}), encoding="utf-8")
    write_learning_note(vault / "Learning" / "AWS" / "AWS SAA.md")

    report = sync_obsidian_learning_registry(
        vault_path=vault,
        learning_path=learning_path,
        career_path=career_path,
        now="2026-06-30T00:00:00Z",
    )

    learning = json.loads(learning_path.read_text(encoding="utf-8"))
    career = json.loads(career_path.read_text(encoding="utf-8"))
    assert report["records_created"] >= 5
    assert learning["certifications"][0]["name"] == "AWS Solutions Architect Associate"
    assert career["learning_summary"] == project_learning_summary(learning, now="2026-06-30T00:00:00Z")
    assert career["learning_summary"]["primary_certification"] == "AWS Solutions Architect Associate"
    assert career["learning_summary"]["certification_progress"] == 15
    assert career["learning_summary"]["next_learning_task"] == "Complete VPC module"
    assert career["learning_summary"]["study_streak_days"] == 1
    assert career["learning_summary"]["weekly_study_hours"] == 4.0
    assert career["source_connections"]["learning_registry"]["status"] == "Connected"


def test_ambiguous_learning_fields_go_to_manual_review_without_inventing_progress(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    note = vault / "Learning" / "Linux" / "Daily Study Log.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "---\n"
        "type: learning\n"
        "provider: Linux\n"
        "course: Linux fundamentals\n"
        "mood: focused\n"
        "---\n"
        "Studied shell navigation.\n",
        encoding="utf-8",
    )

    registry, _report = parse_learning_notes(vault, now="2026-06-30T00:00:00Z")

    assert registry["courses"][0]["progress_percent"] is None
    assert registry["manual_review"][0]["fields"] == ["mood"]


def test_learning_status_returns_registry_info_after_sync(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    write_learning_note(vault / "Learning" / "AWS" / "AWS-SAA.md")

    sync_obsidian_learning_registry(
        vault_path=vault,
        learning_path=learning_path,
        career_path=career_path,
        now="2026-06-30T00:00:00Z",
    )

    status = learning_registry_status(learning_path=learning_path)

    assert status["registry_path"] == str(learning_path)
    assert status["last_sync"] == "2026-06-30T00:00:00Z"
    assert status["learning_notes_discovered"] == 1
    assert status["providers"][0]["name"] == "AWS"
    assert status["certifications"] == 1
    assert status["courses"] == 1
    assert status["study_sessions"] == 1
    assert status["sync_health"]["status"] == "healthy"


def test_learning_audit_detects_malformed_and_duplicate_notes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    write_learning_note(vault / "Learning" / "AWS" / "AWS-SAA.md")
    write_learning_note(vault / "Learning" / "AWS" / "AWS-SAA-copy.md", progress=20)
    missing_type = vault / "Learning" / "Azure Study.md"
    missing_type.parent.mkdir(parents=True, exist_ok=True)
    missing_type.write_text(
        "---\nprovider: Azure\ncourse: AZ-900\n---\n# Azure certification study\n",
        encoding="utf-8",
    )
    malformed = vault / "Learning" / "Broken.md"
    malformed.write_text(
        "---\ntype: learning\nprovider: [AWS\n---\n# broken aws certification note\n",
        encoding="utf-8",
    )
    ignored = vault / "Recipes.md"
    ignored.write_text("# Dinner\nNo training content here.\n", encoding="utf-8")

    report = audit_learning_notes(vault, now="2026-06-30T00:00:00Z")

    assert report["notes_scanned"] == 5
    assert {item["path"] for item in report["malformed_yaml"]} == {"Learning/Broken.md"}
    assert {item["path"] for item in report["missing_type_learning"]} == {"Learning/Azure Study.md", "Learning/Broken.md"}
    assert report["duplicate_certifications"][0]["paths"] == ["Learning/AWS/AWS-SAA-copy.md", "Learning/AWS/AWS-SAA.md"]
    assert report["duplicate_courses"][0]["paths"] == ["Learning/AWS/AWS-SAA-copy.md", "Learning/AWS/AWS-SAA.md"]
    assert report["ignored_notes"] == [{"path": "Recipes.md", "reason": "no learning signal"}]
    assert report["sync_health"]["status"] == "needs_review"


def test_learning_cli_sync_status_audit_emit_json(monkeypatch, tmp_path: Path, capsys) -> None:
    import argparse

    from hermes_cli.learning_cli import _handle_learning

    vault = tmp_path / "vault"
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    write_learning_note(vault / "Learning" / "AWS" / "AWS-SAA.md")
    monkeypatch.setenv("HERMES_DASHBOARD_OBSIDIAN_VAULT", str(vault))
    monkeypatch.setenv("HERMES_LEARNING_REGISTRY_PATH", str(learning_path))
    monkeypatch.setenv("HERMES_CAREER_REGISTRY_PATH", str(career_path))

    assert _handle_learning(argparse.Namespace(learning_action="sync")) == 0
    sync_out = json.loads(capsys.readouterr().out)
    assert sync_out["learning_registry_path"] == str(learning_path)
    assert sync_out["learning_notes"] == 1

    assert _handle_learning(argparse.Namespace(learning_action="status")) == 0
    status_out = json.loads(capsys.readouterr().out)
    assert status_out["registry_path"] == str(learning_path)
    assert status_out["sync_health"]["status"] == "healthy"

    assert _handle_learning(argparse.Namespace(learning_action="audit")) == 0
    audit_out = json.loads(capsys.readouterr().out)
    assert audit_out["vault_path"] == str(vault)
    assert audit_out["sync_health"]["status"] == "healthy"

    career = json.loads(career_path.read_text(encoding="utf-8"))
    assert career["learning_summary"]["primary_certification"] == "AWS Solutions Architect Associate"


def test_manual_import_microsoft_learn_text_updates_learning_registry_and_projection(tmp_path: Path) -> None:
    evidence = tmp_path / "microsoft-learn-export.txt"
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    evidence.write_text(
        "Microsoft Learn transcript\n"
        "Certification: AZ-900\n"
        "Course: Microsoft Azure Fundamentals\n"
        "Module: Describe cloud concepts\n"
        "Progress: 80%\n"
        "Status: In Progress\n"
        "Last studied: 2026-06-30\n",
        encoding="utf-8",
    )

    report = import_learning_evidence(
        evidence,
        provider="microsoft_learn",
        learning_path=learning_path,
        career_path=career_path,
        now="2026-06-30T00:00:00Z",
    )

    registry = json.loads(learning_path.read_text(encoding="utf-8"))
    career = json.loads(career_path.read_text(encoding="utf-8"))
    assert report["certifications_imported"] == 1
    assert report["courses_imported"] == 1
    assert report["modules_imported"] == 1
    assert registry["sources"]["microsoft_learn"]["status"] == "Connected"
    assert registry["certifications"][0]["name"] == "AZ-900"
    assert registry["certifications"][0]["provider"] == "Microsoft Learn"
    assert registry["certifications"][0]["progress_percent"] == 80
    assert registry["certifications"][0]["evidence_path"] == str(evidence)
    assert registry["certifications"][0]["confidence"] >= 0.9
    assert registry["certifications"][0]["imported_at"] == "2026-06-30T00:00:00Z"
    assert career["learning_summary"]["primary_certification"] == "AZ-900"
    assert career["learning_summary"]["certification_progress"] == 80
    assert career["learning_summary"]["source"] == "learning_registry"
    assert "certifications" not in career  # detailed learning records remain only in Learning Registry.


def test_manual_import_aws_skill_builder_csv_updates_courses_and_cert(tmp_path: Path) -> None:
    evidence = tmp_path / "aws-skill-builder.csv"
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    evidence.write_text(
        "certification,course,module,progress,status,completed_on\n"
        "AWS Solutions Architect Associate,AWS Skill Builder SAA Plan,IAM fundamentals,45,in_progress,2026-06-28\n",
        encoding="utf-8",
    )

    report = import_learning_evidence(
        evidence,
        provider="aws_skill_builder",
        learning_path=learning_path,
        career_path=career_path,
        now="2026-06-30T00:00:00Z",
    )

    registry = json.loads(learning_path.read_text(encoding="utf-8"))
    career = json.loads(career_path.read_text(encoding="utf-8"))
    assert report["certifications_imported"] == 1
    assert registry["sources"]["aws_skill_builder"]["status"] == "Connected"
    assert registry["certifications"][0]["name"] == "AWS Solutions Architect Associate"
    assert registry["certifications"][0]["progress_percent"] == 45
    assert registry["courses"][0]["name"] == "AWS Skill Builder SAA Plan"
    assert registry["modules"][0]["name"] == "IAM fundamentals"
    assert registry["source_evidence"][0]["source"] == "aws_skill_builder"
    assert registry["source_evidence"][0]["evidence_path"] == str(evidence)
    assert career["learning_summary"]["primary_certification"] == "AWS Solutions Architect Associate"
    assert career["learning_summary"]["certification_progress"] == 45


def test_manual_import_pdf_text_fallback_and_screenshot_style_file(tmp_path: Path) -> None:
    pdf = tmp_path / "aws-certificate.pdf"
    image = tmp_path / "mslearn-screenshot.png"
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    pdf.write_bytes(
        b"%PDF-1.4\nCertificate\nCertification: AWS Certified Cloud Practitioner\nProgress: 100%\nStatus: Completed\n%%EOF"
    )
    image.write_bytes(
        b"PNG screenshot text export\nMicrosoft Learn\nCourse: Azure Administrator Associate\nProgress: 60%\nStatus: In Progress\n"
    )

    aws_report = import_learning_evidence(
        pdf,
        provider="aws_skill_builder",
        learning_path=learning_path,
        career_path=career_path,
        now="2026-06-30T00:00:00Z",
    )
    ms_report = import_learning_evidence(
        image,
        provider="microsoft_learn",
        learning_path=learning_path,
        career_path=career_path,
        now="2026-06-30T01:00:00Z",
    )

    registry = json.loads(learning_path.read_text(encoding="utf-8"))
    assert aws_report["certifications_imported"] == 1
    assert ms_report["courses_imported"] == 1
    assert any("fallback" in warning for warning in aws_report["extraction"]["warnings"])
    assert any("fallback" in warning for warning in ms_report["extraction"]["warnings"])
    assert {item["provider"] for item in registry["certifications"] + registry["courses"]} == {"AWS Skill Builder", "Microsoft Learn"}
    assert any(item["evidence_path"] == str(pdf) for item in registry["certifications"])
    assert any(item["evidence_path"] == str(image) for item in registry["courses"])


def test_manual_import_ambiguous_evidence_goes_to_manual_review_without_progress(tmp_path: Path) -> None:
    evidence = tmp_path / "ambiguous.txt"
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    evidence.write_text("Microsoft Learn dashboard export. Keep studying soon.\n", encoding="utf-8")

    report = import_learning_evidence(
        evidence,
        provider="microsoft_learn",
        learning_path=learning_path,
        career_path=career_path,
        now="2026-06-30T00:00:00Z",
    )

    registry = json.loads(learning_path.read_text(encoding="utf-8"))
    career = json.loads(career_path.read_text(encoding="utf-8"))
    assert report["certifications_imported"] == 0
    assert report["courses_imported"] == 0
    assert report["manual_review_count"] == 1
    assert registry["certifications"] == []
    assert registry["courses"] == []
    assert "no progress imported" in registry["manual_review"][0]["message"]
    assert career["learning_summary"]["primary_certification"] is None


def test_learning_cli_import_emits_json(monkeypatch, tmp_path: Path, capsys) -> None:
    import argparse

    from hermes_cli.learning_cli import _handle_learning

    evidence = tmp_path / "mslearn.txt"
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    evidence.write_text("Certification: AZ-900\nProgress: 70%\nStatus: In Progress\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_LEARNING_REGISTRY_PATH", str(learning_path))
    monkeypatch.setenv("HERMES_CAREER_REGISTRY_PATH", str(career_path))

    assert _handle_learning(argparse.Namespace(learning_action="import", file=str(evidence), provider="microsoft_learn")) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["provider"] == "microsoft_learn"
    assert out["certifications_imported"] == 1
    assert json.loads(career_path.read_text(encoding="utf-8"))["learning_summary"]["primary_certification"] == "AZ-900"


def test_udemy_browser_html_imports_course_maps_aws_saa_and_projection(tmp_path: Path) -> None:
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    html = """
    <html><body>
      <div data-purpose="course-card" data-course-title="Ultimate AWS Certified Solutions Architect Associate SAA-C03" data-progress="68">
        <a href="/course/aws-certified-solutions-architect-associate-saa-c03/">Ultimate AWS Certified Solutions Architect Associate SAA-C03</a>
        <span>Instructor: Stephane Maarek</span>
        <span>68% complete</span>
        <span>34/50 lectures</span>
        <span>Last accessed: 2026-06-29</span>
      </div>
    </body></html>
    """

    report = import_udemy_browser_html(html, learning_path=learning_path, career_path=career_path, now="2026-06-30T00:00:00Z")

    registry = json.loads(learning_path.read_text(encoding="utf-8"))
    career = json.loads(career_path.read_text(encoding="utf-8"))
    assert report["courses_imported"] == 1
    assert report["manual_review_count"] == 0
    assert registry["sources"]["udemy_browser"]["status"] == "Connected"
    assert registry["courses"][0]["name"] == "Ultimate AWS Certified Solutions Architect Associate SAA-C03"
    assert registry["courses"][0]["source"] == "udemy_browser"
    assert registry["courses"][0]["progress_percent"] == 68
    assert registry["courses"][0]["completed_lectures"] == 34
    assert registry["courses"][0]["total_lectures"] == 50
    assert registry["courses"][0]["instructor"] == "Stephane Maarek"
    assert registry["courses"][0]["evidence_url"] == "https://www.udemy.com/course/aws-certified-solutions-architect-associate-saa-c03/"
    assert registry["certifications"][0]["name"] == "AWS Solutions Architect Associate"
    assert registry["certifications"][0]["provider"] == "AWS"
    assert registry["certifications"][0]["progress_percent"] == 68
    assert registry["certifications"][0]["source"] == "udemy_browser"
    assert career["learning_summary"]["primary_certification"] == "AWS Solutions Architect Associate"
    assert career["learning_summary"]["certification_progress"] == 68
    assert "courses" not in career


def test_udemy_browser_import_prevents_duplicate_courses(tmp_path: Path) -> None:
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    html = """
    <div data-purpose="course-card" data-course-title="Ultimate AWS Certified Solutions Architect Associate SAA-C03" data-progress="68">
      <a href="/course/aws-certified-solutions-architect-associate-saa-c03/">Ultimate AWS Certified Solutions Architect Associate SAA-C03</a>
      <span>68% complete</span>
    </div>
    """

    import_udemy_browser_html(html, learning_path=learning_path, career_path=career_path, now="2026-06-30T00:00:00Z")
    import_udemy_browser_html(html, learning_path=learning_path, career_path=career_path, now="2026-06-30T01:00:00Z")

    registry = json.loads(learning_path.read_text(encoding="utf-8"))
    assert len([course for course in registry["courses"] if course["source"] == "udemy_browser"]) == 1
    assert len([cert for cert in registry["certifications"] if cert["source"] == "udemy_browser"]) == 1


def test_udemy_browser_ambiguous_course_goes_to_manual_review(tmp_path: Path) -> None:
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    html = """
    <div data-purpose="course-card">
      <a href="/course/productivity-notes/">Productivity Notes</a>
      <span>Keep learning</span>
    </div>
    """

    report = import_udemy_browser_html(html, learning_path=learning_path, career_path=career_path, now="2026-06-30T00:00:00Z")

    registry = json.loads(learning_path.read_text(encoding="utf-8"))
    assert report["courses_imported"] == 0
    assert report["manual_review_count"] == 1
    assert registry["courses"] == []
    assert registry["manual_review"][0]["source"] == "udemy_browser"
    assert "no progress was imported" in registry["manual_review"][0]["message"]


def test_udemy_browser_does_not_overwrite_newer_manual_confirmed_course(tmp_path: Path) -> None:
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    learning_path.write_text(json.dumps({
        "schema_version": 1,
        "last_updated": "2026-06-30T02:00:00Z",
        "sources": {},
        "providers": [],
        "certifications": [],
        "courses": [{
            "id": "course_udemy_126bf3d7c5d5",
            "name": "Ultimate AWS Certified Solutions Architect Associate SAA-C03",
            "provider": "Udemy",
            "source": "manual_import",
            "manual_confirmed": True,
            "progress_percent": 90,
            "last_updated": "2026-06-30T02:00:00Z",
            "evidence_path": "manual-note",
        }],
        "modules": [],
        "study_sessions": [],
        "source_evidence": [],
        "manual_review": [],
    }), encoding="utf-8")
    html = """
    <div data-purpose="course-card" data-course-title="Ultimate AWS Certified Solutions Architect Associate SAA-C03" data-progress="68">
      <a href="/course/aws-certified-solutions-architect-associate-saa-c03/">Ultimate AWS Certified Solutions Architect Associate SAA-C03</a>
      <span>68% complete</span>
    </div>
    """

    import_udemy_browser_html(html, learning_path=learning_path, career_path=career_path, now="2026-06-30T01:00:00Z")

    registry = json.loads(learning_path.read_text(encoding="utf-8"))
    assert registry["courses"][0]["progress_percent"] == 90
    assert registry["courses"][0]["source"] == "manual_import"


def test_udemy_browser_status_and_session_file_permissions(tmp_path: Path, monkeypatch) -> None:
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    state_path = tmp_path / "browser_sessions" / "udemy_storage_state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text('{"cookies": [], "origins": []}', encoding="utf-8")
    state_path.chmod(0o600)
    monkeypatch.setenv("HERMES_UDEMY_BROWSER_STATE_PATH", str(state_path))
    html = """
    <div data-purpose="course-card" data-course-title="Ultimate AWS Certified Solutions Architect Associate SAA-C03" data-progress="68">
      <a href="/course/aws-certified-solutions-architect-associate-saa-c03/">Ultimate AWS Certified Solutions Architect Associate SAA-C03</a>
      <span>68% complete</span>
    </div>
    """

    sync_report = sync_udemy_browser_learning(state_path=state_path, learning_path=learning_path, career_path=career_path, html_override=html, now="2026-06-30T00:00:00Z")
    status = udemy_browser_status(learning_path=learning_path, state_path=state_path)

    assert sync_report["success"] is True
    assert sync_report["password_stored"] is False
    assert sync_report["screenshots_saved"] is False
    assert status["session_exists"] is True
    assert status["session_file_mode"] == "0o600"
    assert status["courses_imported"] == 1
    assert status["last_sync"] == "2026-06-30T00:00:00Z"
    assert status["manual_review_count"] == 0


def test_learning_cli_udemy_browser_status_emits_json(monkeypatch, tmp_path: Path, capsys) -> None:
    import argparse

    from hermes_cli.learning_cli import _handle_learning

    learning_path = tmp_path / "learning_registry.json"
    state_path = tmp_path / "udemy_state.json"
    state_path.write_text('{"cookies": []}', encoding="utf-8")
    state_path.chmod(0o600)
    monkeypatch.setenv("HERMES_LEARNING_REGISTRY_PATH", str(learning_path))
    monkeypatch.setenv("HERMES_UDEMY_BROWSER_STATE_PATH", str(state_path))

    assert _handle_learning(argparse.Namespace(learning_action="browser-status", browser_provider="udemy")) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["provider"] == "udemy"
    assert out["session_exists"] is True
    assert out["password_stored"] is False




def test_udemy_current_style_enrolled_course_card_imports_progress(tmp_path: Path) -> None:
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    html = """
    <section data-purpose="enrolled-course-card" class="learning-card--container progress-card">
      <a href="/course/current-aws-saa/learn/lecture/123"><h3 data-purpose="course-title">AWS Certified Solutions Architect Associate 2026</h3></a>
      <div aria-label="Course progress: 41% complete">41% complete</div>
      <span>12 lectures</span><span>3 hours</span>
    </section>
    """

    report = import_udemy_browser_html(html, learning_path=learning_path, career_path=career_path, now="2026-06-30T00:00:00Z")
    registry = json.loads(learning_path.read_text(encoding="utf-8"))

    assert report["courses_imported"] == 1
    assert registry["courses"][0]["name"] == "AWS Certified Solutions Architect Associate 2026"
    assert registry["courses"][0]["progress_percent"] == 41


def test_udemy_course_link_fallback_extracts_nearby_progress(tmp_path: Path) -> None:
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    html = """
    <main>
      <div class="random-grid-item">
        <p>Keep going</p>
        <a href="https://www.udemy.com/course/python-for-cloud-engineers/">Python for Cloud Engineers</a>
        <span>Course progress</span><span>26% complete</span><span>18 min left</span>
      </div>
    </main>
    """

    report = import_udemy_browser_html(html, learning_path=learning_path, career_path=career_path, now="2026-06-30T00:00:00Z")
    registry = json.loads(learning_path.read_text(encoding="utf-8"))

    assert report["courses_imported"] == 1
    assert registry["courses"][0]["name"] == "Python for Cloud Engineers"
    assert registry["courses"][0]["progress_percent"] == 26


def test_udemy_progress_text_extraction_variants(tmp_path: Path) -> None:
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    html = """
    <div data-purpose="learning-card">
      <h4>Deep Learning Deployment</h4>
      <a href="/course/deep-learning-deployment/learn/">Go to course</a>
      <span>Course Progress 63%</span><span>lectures</span><span>2 hours</span>
    </div>
    """

    report = import_udemy_browser_html(html, learning_path=learning_path, career_path=career_path, now="2026-06-30T00:00:00Z")
    registry = json.loads(learning_path.read_text(encoding="utf-8"))

    assert report["courses_imported"] == 1
    assert registry["courses"][0]["progress_percent"] == 63


def test_udemy_course_card_parses_percent_complete_and_start_course_status(tmp_path: Path) -> None:
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    html = """
    <main>
      <section data-purpose="enrolled-course-card" class="my-course-card">
        <a href="/course-dashboard-redirect/?course_id=2776760"><h3>100 Days of Code™: The Complete Python Pro Bootcamp</h3></a>
        <div class="course-progress">7% complete</div>
      </section>
      <section data-purpose="enrolled-course-card" class="my-course-card">
        <a href="/course-dashboard-redirect/?course_id=1456464"><h3>CompTIA CySA+ (CS0-002) Complete Course & Practice Exam</h3></a>
        <button>START COURSE</button>
      </section>
    </main>
    """

    report = import_udemy_browser_html(html, learning_path=learning_path, career_path=career_path, now="2026-06-30T00:00:00Z")
    registry = json.loads(learning_path.read_text(encoding="utf-8"))
    by_name = {course["name"]: course for course in registry["courses"]}

    assert report["source"] == "udemy_browser"
    assert report["courses_imported"] == 2
    assert by_name["100 Days of Code™: The Complete Python Pro Bootcamp"]["progress_percent"] == 7
    assert by_name["100 Days of Code™: The Complete Python Pro Bootcamp"]["status"] == "in_progress"
    assert by_name["CompTIA CySA+ (CS0-002) Complete Course & Practice Exam"]["progress_percent"] == 0
    assert by_name["CompTIA CySA+ (CS0-002) Complete Course & Practice Exam"]["status"] == "not_started"
    assert all(course["source"] == "udemy_browser" for course in registry["courses"])
    assert registry["manual_review"] == []


def test_udemy_browser_progress_update_replaces_heading_fallback_record_and_prunes_missing_progress_review(tmp_path: Path) -> None:
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    title = "CompTIA Linux+ (XK0-006) Complete Course & Exam"
    course_id = stable_id("course", "Udemy", title)
    learning_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "last_updated": "2026-06-30T00:00:00Z",
                "sources": {},
                "providers": [],
                "certifications": [],
                "courses": [
                    {
                        "id": course_id,
                        "name": title,
                        "provider": "Udemy",
                        "source": "udemy_browser_heading_fallback",
                        "progress_percent": None,
                        "status": None,
                        "confidence": 0.65,
                        "last_updated": "2026-06-30T00:00:00Z",
                        "imported_at": "2026-06-30T00:00:00Z",
                    }
                ],
                "modules": [],
                "study_sessions": [],
                "manual_review": [
                    {
                        "source": "udemy_browser_heading_fallback",
                        "message": "Udemy course imported from heading, but progress percentage was not visible.",
                        "course_title": title,
                    }
                ],
                "source_evidence": [],
            }
        ),
        encoding="utf-8",
    )
    html = f"""
    <section data-purpose="enrolled-course-card" class="my-course-card">
      <a href="/course-dashboard-redirect/?course_id=4658902"><h3>{title}</h3></a>
      <button>START COURSE</button>
    </section>
    """

    import_udemy_browser_html(html, learning_path=learning_path, career_path=career_path, now="2026-06-30T01:00:00Z")
    registry = json.loads(learning_path.read_text(encoding="utf-8"))

    assert len(registry["courses"]) == 1
    assert registry["courses"][0]["id"] == course_id
    assert registry["courses"][0]["source"] == "udemy_browser"
    assert registry["courses"][0]["progress_percent"] == 0
    assert registry["courses"][0]["status"] == "not_started"
    assert registry["manual_review"] == []
    assert registry["certifications"][0]["name"] == "Linux+"
    assert registry["certifications"][0]["progress_percent"] == 0
    assert registry["certifications"][0]["status"] == "not_started"


def test_udemy_heading_fallback_imports_courses_without_fabricating_progress(tmp_path: Path) -> None:
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    html = """
    <html><head><title>My learning | Udemy</title></head><body>
      <h1>My learning</h1>
      <h2>All courses</h2>
      <h3>100 Days of Code™: The Complete Python Pro Bootcamp</h3>
      <h3>TOTAL: CompTIA Network+ (N10-009) + Practice Exam</h3>
      <h3>Ultimate AWS Certified Solutions Architect Associate 2026</h3>
      <h3>CompTIA CySA+ (CS0-002) Complete Course & Practice Exam</h3>
      <h3>CompTIA Security+ (SY0-701) Complete Course & Practice Exam</h3>
      <h3>CompTIA Linux+ (XK0-006) Complete Course & Exam</h3>
      <h3>Cisco CCNA 200-301 – The Complete Guide to Getting Certified</h3>
      <h2>Learning tools</h2>
      <h2>Leadership</h2>
    </body></html>
    """

    report = import_udemy_browser_html(
        html,
        learning_path=learning_path,
        career_path=career_path,
        now="2026-06-30T00:00:00Z",
        evidence_url="https://www.udemy.com/home/my-courses/learning/",
    )
    registry = json.loads(learning_path.read_text(encoding="utf-8"))

    assert report["source"] == "udemy_browser_heading_fallback"
    assert report["courses_imported"] == 7
    assert report["manual_review_count"] == 7
    assert {course["name"] for course in registry["courses"]} == {
        "100 Days of Code™: The Complete Python Pro Bootcamp",
        "TOTAL: CompTIA Network+ (N10-009) + Practice Exam",
        "Ultimate AWS Certified Solutions Architect Associate 2026",
        "CompTIA CySA+ (CS0-002) Complete Course & Practice Exam",
        "CompTIA Security+ (SY0-701) Complete Course & Practice Exam",
        "CompTIA Linux+ (XK0-006) Complete Course & Exam",
        "Cisco CCNA 200-301 – The Complete Guide to Getting Certified",
    }
    assert all(course["source"] == "udemy_browser_heading_fallback" for course in registry["courses"])
    assert all(course["progress_percent"] is None for course in registry["courses"])
    assert all(course["confidence"] == 0.65 for course in registry["courses"])
    assert all(course["evidence_url"] == "https://www.udemy.com/home/my-courses/learning/" for course in registry["courses"])
    assert all(item["message"] == "Udemy course imported from heading, but progress percentage was not visible." for item in registry["manual_review"])
    assert "All courses" not in {course["name"] for course in registry["courses"]}
    assert "Learning tools" not in {course["name"] for course in registry["courses"]}
    assert {cert["name"] for cert in registry["certifications"]} == {
        "AWS Solutions Architect Associate",
        "Network+",
        "CySA+",
        "Security+",
        "Linux+",
        "CCNA",
    }
    assert {cert["source"] for cert in registry["certifications"]} == {"udemy_browser_heading_fallback"}


def test_udemy_heading_fallback_excludes_footer_category_marketing_and_privacy_headings(tmp_path: Path) -> None:
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    false_positives = {
        "New & Featured",
        "Certifications by Skill",
        "Data Science",
        "Communication",
        "Business Analytics & Intelligence",
        "About",
        "Discover Udemy",
        "Udemy for Business",
        "Legal & Accessibility",
        "Cookie Preferences",
        "Your Privacy",
        "Strictly Necessary Cookies",
        "Sale of Personal Information",
        "Cookie List",
    }
    html = """
    <html><head><title>My learning | Udemy</title></head><body>
      <h1>My learning</h1>
      <h2>All courses</h2>
      <section data-purpose="my-learning-course-list">
        <h3>100 Days of Code™: The Complete Python Pro Bootcamp</h3>
        <h3>TOTAL: CompTIA Network+ (N10-009) + Practice Exam</h3>
        <h3>Ultimate AWS Certified Solutions Architect Associate 2026</h3>
        <h3>CompTIA CySA+ (CS0-002) Complete Course & Practice Exam</h3>
        <h3>CompTIA Security+ (SY0-701) Complete Course & Practice Exam</h3>
        <h3>CompTIA Linux+ (XK0-006) Complete Course & Exam</h3>
        <h3>Cisco CCNA 200-301 – The Complete Guide to Getting Certified</h3>
      </section>
      <h2>Explore top skills and certifications</h2>
      <h3>New & Featured</h3>
      <h3>Certifications by Skill</h3>
      <h3>Data Science</h3>
      <h3>Communication</h3>
      <h3>Business Analytics & Intelligence</h3>
      <footer>
        <h3>About</h3>
        <h3>Discover Udemy</h3>
        <h3>Udemy for Business</h3>
        <h3>Legal & Accessibility</h3>
        <h3>Cookie Preferences</h3>
      </footer>
      <div id="privacy-modal">
        <h2>Your Privacy</h2>
        <h3>Strictly Necessary Cookies</h3>
        <h3>Sale of Personal Information</h3>
        <h3>Cookie List</h3>
      </div>
    </body></html>
    """

    report = import_udemy_browser_html(
        html,
        learning_path=learning_path,
        career_path=career_path,
        now="2026-06-30T00:00:00Z",
        evidence_url="https://www.udemy.com/home/my-courses/learning/",
    )
    registry = json.loads(learning_path.read_text(encoding="utf-8"))
    titles = {course["name"] for course in registry["courses"] if course["source"] == "udemy_browser_heading_fallback"}

    assert report["courses_imported"] == 7
    assert titles == {
        "100 Days of Code™: The Complete Python Pro Bootcamp",
        "TOTAL: CompTIA Network+ (N10-009) + Practice Exam",
        "Ultimate AWS Certified Solutions Architect Associate 2026",
        "CompTIA CySA+ (CS0-002) Complete Course & Practice Exam",
        "CompTIA Security+ (SY0-701) Complete Course & Practice Exam",
        "CompTIA Linux+ (XK0-006) Complete Course & Exam",
        "Cisco CCNA 200-301 – The Complete Guide to Getting Certified",
    }
    assert titles.isdisjoint(false_positives)
    assert {item.get("course_title") for item in registry["manual_review"]}.isdisjoint(false_positives)


def test_udemy_heading_fallback_ignores_course_like_headings_outside_my_learning_region(tmp_path: Path) -> None:
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    html = """
    <html><head><title>My learning | Udemy</title></head><body>
      <h1>My learning</h1>
      <h2>All courses</h2>
      <h3>CompTIA Security+ (SY0-701) Complete Course & Practice Exam</h3>
      <h2>Learning tools</h2>
      <section class="marketing-category-grid">
        <h3>Python Bootcamp Course Sale</h3>
        <h3>AWS Certification Deals</h3>
      </section>
    </body></html>
    """

    import_udemy_browser_html(html, learning_path=learning_path, career_path=career_path, now="2026-06-30T00:00:00Z")
    registry = json.loads(learning_path.read_text(encoding="utf-8"))
    titles = {course["name"] for course in registry["courses"]}

    assert titles == {"CompTIA Security+ (SY0-701) Complete Course & Practice Exam"}
    assert "Python Bootcamp Course Sale" not in titles
    assert "AWS Certification Deals" not in titles


def test_udemy_course_titles_are_not_hardcoded_in_frontend() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    frontend_files = list((repo_root / "web" / "src").rglob("*.ts")) + list((repo_root / "web" / "src").rglob("*.tsx"))
    frontend_text = "\n".join(path.read_text(encoding="utf-8") for path in frontend_files)

    for title in (
        "100 Days of Code™: The Complete Python Pro Bootcamp",
        "TOTAL: CompTIA Network+ (N10-009) + Practice Exam",
        "Ultimate AWS Certified Solutions Architect Associate 2026",
        "CompTIA CySA+ (CS0-002) Complete Course & Practice Exam",
        "CompTIA Security+ (SY0-701) Complete Course & Practice Exam",
        "CompTIA Linux+ (XK0-006) Complete Course & Exam",
        "Cisco CCNA 200-301 – The Complete Guide to Getting Certified",
    ):
        assert title not in frontend_text


def test_udemy_remote_sync_imports_heading_fallback_with_current_url(monkeypatch, tmp_path: Path) -> None:
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    html = """
    <html><head><title>My learning | Udemy</title></head><body>
      <h1>My learning</h1>
      <h3>Ultimate AWS Certified Solutions Architect Associate 2026</h3>
    </body></html>
    """
    install_fake_playwright(monkeypatch, html=html, page_url="https://www.udemy.com/home/my-courses/learning/")

    report = sync_udemy_browser_learning(
        learning_path=learning_path,
        career_path=career_path,
        remote=True,
        cdp_url="http://127.0.0.1:9222",
        now="2026-06-30T00:00:00Z",
    )
    registry = json.loads(learning_path.read_text(encoding="utf-8"))

    assert report["success"] is True
    assert report["source"] == "udemy_browser_heading_fallback"
    assert registry["courses"][0]["source"] == "udemy_browser_heading_fallback"
    assert registry["courses"][0]["progress_percent"] is None
    assert registry["courses"][0]["evidence_url"] == "https://www.udemy.com/home/my-courses/learning/"
    assert registry["manual_review"][0]["evidence_url"] == "https://www.udemy.com/home/my-courses/learning/"


def test_udemy_no_course_detected_includes_diagnostic_payload(monkeypatch, tmp_path: Path) -> None:
    html = '<html><head><title>My learning</title></head><body><h1>My learning</h1><a href="/home/my-courses/learning/">Learning</a></body></html>'
    install_fake_playwright(monkeypatch, html=html, page_url="https://www.udemy.com/home/my-courses/learning/")

    report = sync_udemy_browser_learning(
        learning_path=tmp_path / "learning_registry.json",
        career_path=tmp_path / "career_registry.json",
        remote=True,
        cdp_url="http://127.0.0.1:9222",
    )

    assert report["success"] is False
    assert report["error"] == "no_udemy_courses_detected"
    assert report["current_url"] == "https://www.udemy.com/home/my-courses/learning/"
    assert report["title"] == "My learning"
    assert report["course_link_count"] == 0
    assert report["candidate_container_count"] == 0
    assert report["recommendation"] == "run --debug-dom"


def test_udemy_debug_dom_redacts_sensitive_values() -> None:
    html = """
    <html><head><title>Udemy user@example.com token=abc123</title></head><body>
      <h1>My learning user@example.com</h1>
      <button>Account token=secret123</button>
      <a href="/course/safe-course/">Safe Course 45% complete</a>
      <div data-purpose="enrolled-course" class="course-card token=secret" aria-label="session=abc123 Safe Course">Safe Course 45% complete user@example.com</div>
      <p>4111 1111 1111 1111</p>
    </body></html>
    """

    report = debug_udemy_browser_dom(html_override=html)
    output = json.dumps(report)

    assert report["success"] is True
    assert report["debug_dom"] is True
    assert "Safe Course" in output
    assert "user@example.com" not in output
    assert "secret123" not in output
    assert "4111 1111 1111 1111" not in output
    assert report["cookies_read"] is False
    assert report["storage_read"] is False


def test_udemy_remote_cdp_sync_imports_course_and_projection(monkeypatch, tmp_path: Path) -> None:
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    html = """
    <div data-purpose="course-card" data-course-title="Ultimate AWS Certified Solutions Architect Associate SAA-C03" data-progress="72">
      <a href="/course/aws-certified-solutions-architect-associate-saa-c03/">Ultimate AWS Certified Solutions Architect Associate SAA-C03</a>
      <span>72% complete</span>
    </div>
    """
    calls = install_fake_playwright(monkeypatch, html=html)

    report = sync_udemy_browser_learning(
        learning_path=learning_path,
        career_path=career_path,
        remote=True,
        cdp_url="http://127.0.0.1:9222",
        now="2026-06-30T00:00:00Z",
    )

    registry = json.loads(learning_path.read_text(encoding="utf-8"))
    career = json.loads(career_path.read_text(encoding="utf-8"))
    assert calls["connect_over_cdp"] == ["http://127.0.0.1:9222"]
    assert calls["launch"] == []
    assert report["success"] is True
    assert report["remote"] is True
    assert report["courses_imported"] == 1
    assert report["session_state_path"] is None
    assert calls["context"].storage_state_calls == []  # type: ignore[union-attr]
    assert calls["browser"].closed is False  # type: ignore[union-attr]
    assert registry["courses"][0]["progress_percent"] == 72
    assert career["learning_summary"]["primary_certification"] == "AWS Solutions Architect Associate"
    assert career["learning_summary"]["certification_progress"] == 72



def test_udemy_remote_cdp_tolerates_err_aborted_and_extracts_courses(monkeypatch, tmp_path: Path) -> None:
    learning_path = tmp_path / "learning_registry.json"
    career_path = tmp_path / "career_registry.json"
    html = """
    <div data-purpose="course-card" data-course-title="Ultimate AWS Certified Solutions Architect Associate SAA-C03" data-progress="74">
      <a href="/course/aws-certified-solutions-architect-associate-saa-c03/">Ultimate AWS Certified Solutions Architect Associate SAA-C03</a>
      <span>74% complete</span>
    </div>
    """
    calls = install_fake_playwright(
        monkeypatch,
        html=html,
        goto_errors=[RuntimeError("Page.goto: net::ERR_ABORTED at https://www.udemy.com/home/my-courses/learning/?cookie=secret-token")],
    )

    report = sync_udemy_browser_learning(
        learning_path=learning_path,
        career_path=career_path,
        remote=True,
        cdp_url="http://127.0.0.1:9222",
        now="2026-06-30T00:00:00Z",
    )
    output = json.dumps(report)

    page = calls["page"]
    assert report["success"] is True
    assert report["courses_imported"] == 1
    assert "secret-token" not in output
    assert page.goto_calls[0] == ("https://www.udemy.com/home/my-courses/learning/", "domcontentloaded")  # type: ignore[union-attr]
    assert page.wait_for_selector_calls  # type: ignore[union-attr]
    assert json.loads(career_path.read_text(encoding="utf-8"))["learning_summary"]["certification_progress"] == 74


def test_udemy_remote_cdp_missing_endpoint_returns_friendly_error_without_secrets(monkeypatch, tmp_path: Path) -> None:
    install_fake_playwright(monkeypatch, fail_cdp=True)

    report = sync_udemy_browser_learning(
        learning_path=tmp_path / "learning_registry.json",
        career_path=tmp_path / "career_registry.json",
        remote=True,
        cdp_url="http://user:secret-token@127.0.0.1:9222/json/version?token=secret-token",
    )
    output = json.dumps(report)

    assert report["success"] is False
    assert report["error"] == "cdp_connection_failed"
    assert "Start Chrome or Edge" in report["message"]
    assert "secret-token" not in output
    assert "cookie" not in output.lower()
    assert "session" not in output.lower()



def test_udemy_remote_sync_returns_friendly_not_logged_in_without_secrets(monkeypatch, tmp_path: Path) -> None:
    html = '<html><body>Udemy <form data-purpose="login-form"><input name="email"><input name="password"></form></body></html>'
    calls = install_fake_playwright(monkeypatch, html=html, page_url="https://www.udemy.com/join/login-popup/")

    report = sync_udemy_browser_learning(
        learning_path=tmp_path / "learning_registry.json",
        career_path=tmp_path / "career_registry.json",
        remote=True,
        cdp_url="http://user:secret-token@127.0.0.1:9222/json/version?token=secret-token",
    )
    output = json.dumps(report)

    assert report["success"] is False
    assert report["error"] == "udemy_not_logged_in"
    assert report["cdp_url"] == "http://127.0.0.1:9222/json/version"
    assert "secret-token" not in output
    assert "password" not in report["message"].lower()
    assert calls["page"].goto_calls == [  # type: ignore[union-attr]
        ("https://www.udemy.com/home/my-courses/learning/", "domcontentloaded"),
        ("https://www.udemy.com/home/my-courses/", "domcontentloaded"),
        ("https://www.udemy.com/home/my-courses/learning/?p=1", "domcontentloaded"),
    ]


def test_udemy_remote_sync_returns_friendly_no_courses_detected(monkeypatch, tmp_path: Path) -> None:
    html = '<html><body><h1>My learning</h1><p>No course cards here.</p></body></html>'
    install_fake_playwright(monkeypatch, html=html, page_url="https://www.udemy.com/home/my-courses/learning/")

    report = sync_udemy_browser_learning(
        learning_path=tmp_path / "learning_registry.json",
        career_path=tmp_path / "career_registry.json",
        remote=True,
        cdp_url="http://127.0.0.1:9222",
    )

    assert report["success"] is False
    assert report["error"] == "no_udemy_courses_detected"
    assert report["password_stored"] is False
    assert report["screenshots_saved"] is False


def test_learning_cli_udemy_remote_flags_emit_json(monkeypatch, tmp_path: Path, capsys) -> None:
    import argparse

    from hermes_cli.learning_cli import _handle_learning

    learning_path = tmp_path / "learning_registry.json"
    monkeypatch.setenv("HERMES_LEARNING_REGISTRY_PATH", str(learning_path))

    assert _handle_learning(argparse.Namespace(learning_action="browser-status", browser_provider="udemy", remote=True, cdp_url="http://127.0.0.1:9222")) == 0
    status = json.loads(capsys.readouterr().out)

    assert status["provider"] == "udemy"
    assert status["remote"] is True
    assert status["cdp_url"] == "http://127.0.0.1:9222"
    assert status["session_exists"] is False
    assert status["session_state_path"] is None
    assert status["password_stored"] is False
    assert status["screenshots_saved"] is False
