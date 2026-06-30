"""Tests for Learning Registry and Obsidian sync projection."""

from __future__ import annotations

import json
from pathlib import Path

from hermes_cli.learning_registry import (
    audit_learning_notes,
    import_learning_evidence,
    learning_registry_status,
    parse_learning_notes,
    project_learning_summary,
    sync_obsidian_learning_registry,
)


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
