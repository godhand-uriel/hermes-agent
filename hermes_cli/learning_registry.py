"""Learning Registry and Obsidian sync support for Career Command.

Flow: Obsidian/manual sources -> Learning Registry -> Career Registry -> Dashboard UI.
The UI must never parse Obsidian directly for learning progress.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
import time
from io import StringIO
from pathlib import Path
from typing import Any, Iterable

import yaml

from hermes_constants import get_hermes_home

DEFAULT_LEARNING_REGISTRY_RELATIVE_PATH = "dashboard/learning_registry.json"
DEFAULT_CAREER_REGISTRY_RELATIVE_PATH = "dashboard/career_registry.json"
DEFAULT_OBSIDIAN_VAULT = Path(os.environ.get("HERMES_DASHBOARD_OBSIDIAN_VAULT") or os.environ.get("OBSIDIAN_VAULT_PATH") or "/home/yuu/Sync/ObsidianVault")

LEARNING_KEYWORDS = (
    "learning",
    "study",
    "certification",
    "certifications",
    "aws",
    "azure",
    "microsoft learn",
    "linux",
    "security+",
    "terraform",
)

SAFE_FRONTMATTER_FIELDS = {
    "type",
    "provider",
    "certification",
    "course",
    "module",
    "status",
    "progress",
    "progress_percent",
    "last_studied",
    "next_action",
    "study_hours",
    "weekly_study_hours",
    "tags",
}


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def registry_path(env_name: str, relative_path: str) -> Path:
    configured = os.environ.get(env_name, "").strip()
    if configured:
        return Path(configured).expanduser()
    return get_hermes_home() / relative_path


def learning_registry_path() -> Path:
    return registry_path("HERMES_LEARNING_REGISTRY_PATH", DEFAULT_LEARNING_REGISTRY_RELATIVE_PATH)


def career_registry_path() -> Path:
    return registry_path("HERMES_CAREER_REGISTRY_PATH", DEFAULT_CAREER_REGISTRY_RELATIVE_PATH)


def obsidian_vault_path() -> Path:
    return Path(os.environ.get("HERMES_DASHBOARD_OBSIDIAN_VAULT") or os.environ.get("OBSIDIAN_VAULT_PATH") or DEFAULT_OBSIDIAN_VAULT).expanduser()


def empty_learning_registry(*, now: str | None = None) -> dict[str, Any]:
    timestamp = now or utc_now()
    return {
        "schema_version": 1,
        "last_updated": timestamp,
        "sources": {
            "obsidian": {
                "status": "Connected" if obsidian_vault_path().exists() else "Not connected",
                "source": "obsidian",
                "confidence": 1.0 if obsidian_vault_path().exists() else 0.0,
                "last_updated": timestamp,
                "path": str(obsidian_vault_path()),
            },
            "microsoft_learn": {
                "status": "Not connected",
                "source": "manual_provider_gap",
                "confidence": 1.0,
                "last_updated": timestamp,
                "needed_user_action": "Export Microsoft Learn transcript/progress or provide screenshots.",
            },
            "aws_skill_builder": {
                "status": "Not connected",
                "source": "manual_provider_gap",
                "confidence": 1.0,
                "last_updated": timestamp,
                "needed_user_action": "Export AWS Skill Builder completion/progress evidence or provide screenshots/PDF.",
            },
            "manual": {
                "status": "Allowed",
                "source": "manual_entry",
                "confidence": 1.0,
                "last_updated": timestamp,
            },
        },
        "providers": [],
        "certifications": [],
        "courses": [],
        "modules": [],
        "study_sessions": [],
        "learning_streak": {
            "current_days": 0,
            "last_studied": None,
            "source": "learning_registry",
            "confidence": 0.0,
            "last_updated": timestamp,
            "evidence_path": None,
        },
        "study_recommendations": [],
        "source_evidence": [],
        "manual_review": [],
    }


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else dict(default)
    except (OSError, json.JSONDecodeError):
        return dict(default)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def split_frontmatter(markdown: str) -> tuple[dict[str, Any], str, str | None]:
    if not markdown.startswith("---\n"):
        return {}, markdown, None
    end = markdown.find("\n---", 4)
    if end == -1:
        return {}, markdown, "frontmatter block is not closed"
    raw = markdown[4:end]
    body = markdown[end + len("\n---") :].lstrip("\r\n")
    try:
        parsed = yaml.safe_load(raw) or {}
        return parsed if isinstance(parsed, dict) else {}, body, None if isinstance(parsed, dict) else "frontmatter is not a mapping"
    except Exception as exc:  # noqa: BLE001 - preserve ambiguous parse details for manual review.
        return {}, body, f"frontmatter parse failed: {exc}"


def slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "unknown"


def stable_id(kind: str, *parts: Any) -> str:
    digest = hashlib.sha1("|".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()[:12]
    prefix = slug(parts[0] if parts else kind)[:32]
    return f"{kind}_{prefix}_{digest}"


def normalize_percent(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        num = float(str(value).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None
    return int(max(0, min(100, round(num))))


def normalize_hours(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(str(value).strip()), 2)
    except (TypeError, ValueError):
        return None


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def note_has_learning_signal(relative_path: str, frontmatter: dict[str, Any], body: str) -> bool:
    if str(frontmatter.get("type") or "").casefold() == "learning":
        return True
    haystack = f"{relative_path}\n{body[:12000]}".casefold()
    return any(keyword in haystack for keyword in LEARNING_KEYWORDS)


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def safe_frontmatter(frontmatter: dict[str, Any]) -> dict[str, Any]:
    return {key: json_safe(frontmatter.get(key)) for key in SAFE_FRONTMATTER_FIELDS if key in frontmatter}


def evidence(relative_path: str, field: str, value: Any, *, confidence: float, now: str) -> dict[str, Any]:
    return {
        "field": field,
        "value": value,
        "source": "obsidian",
        "confidence": confidence,
        "last_updated": now,
        "evidence_path": relative_path,
    }


def add_provider(providers: dict[str, dict[str, Any]], provider: str, *, source: str, confidence: float, now: str, evidence_path: str | None = None) -> None:
    if not provider:
        return
    key = slug(provider)
    existing = providers.get(key, {})
    providers[key] = {
        "id": key,
        "name": provider,
        "status": existing.get("status") or "connected_by_evidence",
        "source": existing.get("source") or source,
        "confidence": max(float(existing.get("confidence") or 0), confidence),
        "last_updated": now,
        "evidence_path": existing.get("evidence_path") or evidence_path,
    }


def parse_learning_notes(vault: Path | None = None, *, now: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    timestamp = now or utc_now()
    vault = vault or obsidian_vault_path()
    registry = empty_learning_registry(now=timestamp)
    registry["sources"]["obsidian"]["path"] = str(vault)
    registry["sources"]["obsidian"]["status"] = "Connected" if vault.exists() else "Not connected"
    registry["sources"]["obsidian"]["confidence"] = 1.0 if vault.exists() else 0.0
    if not vault.exists():
        registry["manual_review"].append({
            "source": "obsidian",
            "confidence": 1.0,
            "last_updated": timestamp,
            "message": "Obsidian vault path does not exist.",
            "evidence_path": str(vault),
        })
        return registry, {"notes_scanned": 0, "learning_notes": 0, "records_created": 0, "manual_review_count": 1}

    providers: dict[str, dict[str, Any]] = {}
    certifications: dict[str, dict[str, Any]] = {}
    courses: dict[str, dict[str, Any]] = {}
    modules: dict[str, dict[str, Any]] = {}
    sessions: dict[str, dict[str, Any]] = {}
    evidence_rows: list[dict[str, Any]] = []
    manual_review: list[dict[str, Any]] = []
    learning_notes = 0

    for path in sorted(vault.rglob("*.md")):
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            manual_review.append({"source": "obsidian", "confidence": 1.0, "last_updated": timestamp, "message": str(exc), "evidence_path": str(path)})
            continue
        relative = str(path.relative_to(vault)) if path.is_relative_to(vault) else str(path)
        frontmatter, body, fm_error = split_frontmatter(raw)
        if fm_error:
            manual_review.append({"source": "obsidian", "confidence": 0.4, "last_updated": timestamp, "message": fm_error, "evidence_path": relative})
        if not note_has_learning_signal(relative, frontmatter, body):
            continue
        learning_notes += 1
        note_type = str(frontmatter.get("type") or "").casefold()
        confidence = 0.95 if note_type == "learning" else 0.55
        provider = str(frontmatter.get("provider") or "").strip()
        cert_name = str(frontmatter.get("certification") or "").strip()
        course_name = str(frontmatter.get("course") or "").strip()
        module_name = str(frontmatter.get("module") or "").strip()
        progress = normalize_percent(frontmatter.get("progress_percent", frontmatter.get("progress")))
        status = frontmatter.get("status")
        last_studied = frontmatter.get("last_studied")
        next_action = frontmatter.get("next_action")
        study_hours = normalize_hours(frontmatter.get("study_hours"))
        weekly_study_hours = normalize_hours(frontmatter.get("weekly_study_hours"))

        if provider:
            add_provider(providers, provider, source="obsidian", confidence=confidence, now=timestamp, evidence_path=relative)
            evidence_rows.append(evidence(relative, "provider", provider, confidence=confidence, now=timestamp))
        if cert_name:
            cert_id = stable_id("cert", provider, cert_name)
            certifications[cert_id] = {
                "id": cert_id,
                "name": cert_name,
                "provider": provider or None,
                "status": status,
                "progress_percent": progress,
                "last_studied": str(last_studied) if last_studied else None,
                "next_action": next_action,
                "source": "obsidian",
                "confidence": confidence,
                "last_updated": timestamp,
                "evidence_path": relative,
                "frontmatter": safe_frontmatter(frontmatter),
            }
            evidence_rows.append(evidence(relative, "certification", cert_name, confidence=confidence, now=timestamp))
        if course_name:
            course_id = stable_id("course", provider, course_name)
            courses[course_id] = {
                "id": course_id,
                "name": course_name,
                "provider": provider or None,
                "status": status,
                "progress_percent": progress,
                "last_studied": str(last_studied) if last_studied else None,
                "next_action": next_action,
                "source": "obsidian",
                "confidence": confidence,
                "last_updated": timestamp,
                "evidence_path": relative,
                "frontmatter": safe_frontmatter(frontmatter),
            }
            evidence_rows.append(evidence(relative, "course", course_name, confidence=confidence, now=timestamp))
        if module_name:
            module_id = stable_id("module", provider, course_name, module_name)
            modules[module_id] = {
                "id": module_id,
                "name": module_name,
                "course": course_name or None,
                "provider": provider or None,
                "status": status,
                "progress_percent": progress,
                "last_studied": str(last_studied) if last_studied else None,
                "next_action": next_action,
                "source": "obsidian",
                "confidence": confidence,
                "last_updated": timestamp,
                "evidence_path": relative,
                "frontmatter": safe_frontmatter(frontmatter),
            }
            evidence_rows.append(evidence(relative, "module", module_name, confidence=confidence, now=timestamp))
        if last_studied or study_hours is not None or weekly_study_hours is not None:
            session_id = stable_id("study", relative, last_studied, module_name or course_name or cert_name)
            sessions[session_id] = {
                "id": session_id,
                "date": str(last_studied) if last_studied else None,
                "provider": provider or None,
                "certification": cert_name or None,
                "course": course_name or None,
                "module": module_name or None,
                "hours": study_hours,
                "weekly_hours": weekly_study_hours,
                "next_action": next_action,
                "source": "obsidian",
                "confidence": confidence,
                "last_updated": timestamp,
                "evidence_path": relative,
            }
        ambiguous_fields = sorted(set(frontmatter) - SAFE_FRONTMATTER_FIELDS)
        if ambiguous_fields and note_type == "learning":
            manual_review.append({
                "source": "obsidian",
                "confidence": 0.6,
                "last_updated": timestamp,
                "message": "Learning note has unrecognized frontmatter fields.",
                "fields": ambiguous_fields,
                "evidence_path": relative,
            })
        if note_type != "learning" and any(keyword in (relative + body[:2000]).casefold() for keyword in ("aws", "azure", "linux", "terraform", "certification", "study")):
            manual_review.append({
                "source": "obsidian",
                "confidence": 0.45,
                "last_updated": timestamp,
                "message": "Learning keywords found, but note is not typed as learning; not importing progress.",
                "evidence_path": relative,
            })

    registry["providers"] = sorted(providers.values(), key=lambda item: item["name"])
    registry["certifications"] = sorted(certifications.values(), key=lambda item: item["name"])
    registry["courses"] = sorted(courses.values(), key=lambda item: item["name"])
    registry["modules"] = sorted(modules.values(), key=lambda item: item["name"])
    registry["study_sessions"] = sorted(sessions.values(), key=lambda item: (str(item.get("date") or ""), item["id"]), reverse=True)
    registry["source_evidence"] = evidence_rows
    registry["manual_review"] = manual_review
    registry["learning_streak"] = compute_learning_streak(registry["study_sessions"], now=timestamp)
    registry["study_recommendations"] = build_recommendations(registry, now=timestamp)
    records = sum(len(registry[key]) for key in ("providers", "certifications", "courses", "modules", "study_sessions"))
    report = {
        "vault_path": str(vault),
        "notes_scanned": len(list(vault.rglob("*.md"))),
        "learning_notes": learning_notes,
        "records_created": records,
        "manual_review_count": len(manual_review),
        "last_updated": timestamp,
    }
    return registry, report


def compute_learning_streak(study_sessions: Iterable[dict[str, Any]], *, now: str) -> dict[str, Any]:
    dates = sorted({str(item.get("date")) for item in study_sessions if item.get("date")}, reverse=True)
    last_studied = dates[0] if dates else None
    return {
        "current_days": 1 if last_studied else 0,
        "last_studied": last_studied,
        "source": "learning_registry",
        "confidence": 0.8 if last_studied else 0.0,
        "last_updated": now,
        "evidence_path": next((item.get("evidence_path") for item in study_sessions if str(item.get("date")) == last_studied), None) if last_studied else None,
    }


def build_recommendations(registry: dict[str, Any], *, now: str) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    candidates = [*registry.get("certifications", []), *registry.get("courses", []), *registry.get("modules", [])]
    for item in candidates:
        action = item.get("next_action")
        if action:
            recommendations.append({
                "id": stable_id("rec", item.get("id"), action),
                "recommendation": action,
                "related_record_id": item.get("id"),
                "source": item.get("source") or "learning_registry",
                "confidence": item.get("confidence", 0.8),
                "last_updated": now,
                "evidence_path": item.get("evidence_path"),
            })
    if not recommendations:
        recommendations.append({
            "id": "rec_standardize_obsidian_learning_notes",
            "recommendation": "Create or update a typed Obsidian learning note with provider, certification/course, status, progress, last_studied, and next_action.",
            "source": "learning_registry",
            "confidence": 1.0,
            "last_updated": now,
            "evidence_path": None,
        })
    return recommendations[:5]


def project_learning_summary(registry: dict[str, Any], *, now: str | None = None) -> dict[str, Any]:
    timestamp = now or utc_now()
    raw_certs = registry.get("certifications")
    raw_courses = registry.get("courses")
    raw_modules = registry.get("modules")
    raw_recommendations = registry.get("study_recommendations")
    raw_streak = registry.get("learning_streak")
    raw_sessions = registry.get("study_sessions")
    certs: list[dict[str, Any]] = [item for item in raw_certs if isinstance(item, dict)] if isinstance(raw_certs, list) else []
    courses: list[dict[str, Any]] = [item for item in raw_courses if isinstance(item, dict)] if isinstance(raw_courses, list) else []
    modules: list[dict[str, Any]] = [item for item in raw_modules if isinstance(item, dict)] if isinstance(raw_modules, list) else []
    recommendations: list[dict[str, Any]] = [item for item in raw_recommendations if isinstance(item, dict)] if isinstance(raw_recommendations, list) else []
    streak: dict[str, Any] = raw_streak if isinstance(raw_streak, dict) else {}
    sessions: list[dict[str, Any]] = [item for item in raw_sessions if isinstance(item, dict)] if isinstance(raw_sessions, list) else []

    def priority(item: dict[str, Any]) -> tuple[int, int]:
        progress = normalize_percent(item.get("progress_percent"))
        in_progress = str(item.get("status") or "").casefold() in {"in_progress", "studying", "active"}
        return (1 if in_progress else 0, progress if progress is not None else -1)

    primary = max(certs, key=priority) if certs else None
    weekly_hours = sum(float(item.get("weekly_hours") or item.get("hours") or 0) for item in sessions if isinstance(item, dict))
    next_recommendation = recommendations[0] if recommendations else None
    next_task = (primary or {}).get("next_action") or (next_recommendation or {}).get("recommendation")
    risk = "Needs learning source standardization" if not certs and not courses and not modules else "On pace" if next_task else "Needs next action"
    return {
        "primary_certification": (primary or {}).get("name"),
        "certification_progress": (primary or {}).get("progress_percent"),
        "next_learning_task": next_task,
        "study_streak_days": streak.get("current_days") or 0,
        "last_studied": streak.get("last_studied"),
        "weekly_study_hours": weekly_hours,
        "learning_risk": risk,
        "next_recommendation": (next_recommendation or {}).get("recommendation"),
        "provider_connections": registry.get("sources", {}),
        "source": "learning_registry",
        "confidence": max([float(item.get("confidence") or 0) for item in [*(certs or []), *(courses or []), *(modules or [])]], default=0.0),
        "last_updated": timestamp,
        "evidence_path": (primary or {}).get("evidence_path") or (next_recommendation or {}).get("evidence_path"),
    }


def _learning_record_paths(registry: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for key in ("certifications", "courses", "modules", "study_sessions", "source_evidence", "manual_review"):
        rows = registry.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and row.get("evidence_path"):
                paths.add(str(row["evidence_path"]))
    return paths


def _sync_health(registry: dict[str, Any], path: Path) -> dict[str, Any]:
    manual_review = registry.get("manual_review") if isinstance(registry.get("manual_review"), list) else []
    sources = registry.get("sources") if isinstance(registry.get("sources"), dict) else {}
    obsidian = sources.get("obsidian") if isinstance(sources.get("obsidian"), dict) else {}
    has_records = any(isinstance(registry.get(key), list) and registry.get(key) for key in ("certifications", "courses", "modules", "study_sessions"))
    if not path.exists():
        state = "missing_registry"
    elif obsidian.get("status") != "Connected":
        state = "source_disconnected"
    elif manual_review:
        state = "needs_review"
    elif has_records:
        state = "healthy"
    else:
        state = "no_learning_records"
    return {
        "status": state,
        "registry_exists": path.exists(),
        "obsidian_status": obsidian.get("status") or "Unknown",
        "manual_review_count": len(manual_review),
        "has_learning_records": bool(has_records),
    }


def learning_registry_status(*, learning_path: Path | None = None) -> dict[str, Any]:
    """Return read-only status for the Learning Registry CLI."""
    path = learning_path or learning_registry_path()
    registry = load_json(path, empty_learning_registry())
    providers = registry.get("providers") if isinstance(registry.get("providers"), list) else []
    certifications = registry.get("certifications") if isinstance(registry.get("certifications"), list) else []
    courses = registry.get("courses") if isinstance(registry.get("courses"), list) else []
    sessions = registry.get("study_sessions") if isinstance(registry.get("study_sessions"), list) else []
    return {
        "registry_path": str(path),
        "last_sync": registry.get("last_updated"),
        "providers": providers,
        "learning_notes_discovered": len(_learning_record_paths(registry)),
        "certifications": len(certifications),
        "courses": len(courses),
        "study_sessions": len(sessions),
        "sync_health": _sync_health(registry, path),
    }


def audit_learning_notes(vault: Path | None = None, *, now: str | None = None) -> dict[str, Any]:
    """Read-only audit of Obsidian notes relevant to Learning Registry import."""
    timestamp = now or utc_now()
    vault = vault or obsidian_vault_path()
    report: dict[str, Any] = {
        "vault_path": str(vault),
        "notes_scanned": 0,
        "learning_notes": 0,
        "malformed_yaml": [],
        "missing_type_learning": [],
        "missing_required_frontmatter": [],
        "duplicate_certifications": [],
        "duplicate_courses": [],
        "ignored_notes": [],
        "last_updated": timestamp,
    }
    if not vault.exists():
        report["sync_health"] = {"status": "source_disconnected", "message": "Obsidian vault path does not exist."}
        return report

    cert_seen: dict[tuple[str, str], list[str]] = {}
    course_seen: dict[tuple[str, str], list[str]] = {}
    required_any = ("certification", "course", "module", "last_studied", "study_hours", "weekly_study_hours")
    for path in sorted(vault.rglob("*.md")):
        report["notes_scanned"] += 1
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            relative = str(path.relative_to(vault)) if path.is_relative_to(vault) else str(path)
            report["malformed_yaml"].append({"path": relative, "message": str(exc)})
            continue
        relative = str(path.relative_to(vault)) if path.is_relative_to(vault) else str(path)
        frontmatter, body, fm_error = split_frontmatter(raw)
        has_signal = note_has_learning_signal(relative, frontmatter, body)
        if fm_error:
            report["malformed_yaml"].append({"path": relative, "message": fm_error})
        if not has_signal:
            report["ignored_notes"].append({"path": relative, "reason": "no learning signal"})
            continue
        report["learning_notes"] += 1
        note_type = str(frontmatter.get("type") or "").casefold()
        if note_type != "learning":
            report["missing_type_learning"].append({"path": relative, "current_type": frontmatter.get("type")})
        missing = []
        if not frontmatter.get("provider"):
            missing.append("provider")
        if not any(frontmatter.get(field) not in (None, "") for field in required_any):
            missing.append("one_of: certification, course, module, last_studied, study_hours, weekly_study_hours")
        if missing:
            report["missing_required_frontmatter"].append({"path": relative, "missing": missing})
        provider = slug(frontmatter.get("provider") or "")
        cert_name = str(frontmatter.get("certification") or "").strip()
        course_name = str(frontmatter.get("course") or "").strip()
        if cert_name:
            cert_seen.setdefault((provider, slug(cert_name)), []).append(relative)
        if course_name:
            course_seen.setdefault((provider, slug(course_name)), []).append(relative)

    report["duplicate_certifications"] = [
        {"provider": provider or None, "certification": cert, "paths": paths}
        for (provider, cert), paths in sorted(cert_seen.items())
        if len(paths) > 1
    ]
    report["duplicate_courses"] = [
        {"provider": provider or None, "course": course, "paths": paths}
        for (provider, course), paths in sorted(course_seen.items())
        if len(paths) > 1
    ]
    issue_count = sum(len(report[key]) for key in ("malformed_yaml", "missing_type_learning", "missing_required_frontmatter", "duplicate_certifications", "duplicate_courses"))
    report["sync_health"] = {"status": "needs_review" if issue_count else "healthy", "issue_count": issue_count}
    return report



SUPPORTED_MANUAL_IMPORT_PROVIDERS = {"microsoft_learn", "aws_skill_builder"}
PROVIDER_DISPLAY_NAMES = {
    "microsoft_learn": "Microsoft Learn",
    "aws_skill_builder": "AWS Skill Builder",
}
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def _manual_source_evidence(evidence_path: str, field: str, value: Any, *, provider: str, confidence: float, now: str) -> dict[str, Any]:
    return {
        "field": field,
        "value": value,
        "source": provider,
        "confidence": confidence,
        "last_updated": now,
        "evidence_path": evidence_path,
    }


def _read_pdf_text(path: Path) -> tuple[str, list[str]]:
    warnings: list[str] = []
    try:
        import fitz  # type: ignore

        with fitz.open(path) as doc:
            return "\n".join(page.get_text("text") for page in doc), warnings
    except Exception as exc:  # noqa: BLE001 - optional dependency/fallback path.
        warnings.append(f"pymupdf unavailable or failed: {exc}")
    try:
        import pypdf  # type: ignore

        reader = pypdf.PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages), warnings
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"pypdf unavailable or failed: {exc}")
    try:
        result = subprocess.run(["pdftotext", str(path), "-"], check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout, warnings
        warnings.append(f"pdftotext failed: {result.stderr.strip() or result.returncode}")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"pdftotext unavailable or failed: {exc}")
    raw = path.read_bytes()
    decoded = raw.decode("utf-8", errors="ignore")
    printable = "\n".join(part.strip() for part in re.findall(r"[ -~]{4,}", decoded) if part.strip())
    if printable:
        warnings.append("used lossy PDF byte-text fallback")
    return printable, warnings


def _read_image_text(path: Path) -> tuple[str, list[str]]:
    warnings: list[str] = []
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore

        return pytesseract.image_to_string(Image.open(path)), warnings
    except Exception as exc:  # noqa: BLE001 - optional OCR dependency/fallback path.
        warnings.append(f"image OCR unavailable or failed: {exc}")
    # Screenshot-style exports sometimes arrive as text payloads with image extensions in tests/fixtures.
    raw = path.read_bytes()
    decoded = raw.decode("utf-8", errors="ignore")
    printable = "\n".join(part.strip() for part in re.findall(r"[ -~]{4,}", decoded) if part.strip())
    if printable:
        warnings.append("used lossy image byte-text fallback")
    return printable, warnings


def extract_learning_evidence_text(path: Path) -> tuple[str, dict[str, Any]]:
    suffix = path.suffix.casefold()
    metadata: dict[str, Any] = {"path": str(path), "kind": suffix.lstrip(".") or "text", "warnings": []}
    if suffix == ".pdf":
        text, warnings = _read_pdf_text(path)
        metadata["warnings"] = warnings
        return text, metadata
    if suffix in IMAGE_EXTENSIONS:
        text, warnings = _read_image_text(path)
        metadata["warnings"] = warnings
        return text, metadata
    try:
        return path.read_text(encoding="utf-8"), metadata
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore"), metadata


def _first_match(patterns: Iterable[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            value = next((group for group in match.groups() if group), None)
            if value:
                return re.sub(r"\s+", " ", value).strip(" :-–—\t")
    return None


def _find_progress(text: str) -> int | None:
    return normalize_percent(
        _first_match(
            [
                r"(?:progress|completed|completion|course progress|module progress)\s*[:\-]?\s*(\d{1,3})\s*%",
                r"(\d{1,3})\s*%\s*(?:complete|completed|progress)",
            ],
            text,
        )
    )


def _find_status(text: str, progress: int | None) -> str | None:
    status = _first_match([r"(?:status|state)\s*[:\-]\s*([A-Za-z _-]{3,40})"], text)
    if status:
        return slug(status).replace("-", "_")
    if re.search(r"\b(completed|complete|earned|passed)\b", text, flags=re.IGNORECASE):
        return "completed"
    if progress is not None and 0 < progress < 100:
        return "in_progress"
    if progress == 100:
        return "completed"
    return None


def _find_date(text: str) -> str | None:
    return _first_match(
        [
            r"(?:completed|completion date|last studied|date)\s*[:\-]\s*(\d{4}-\d{2}-\d{2})",
            r"(?:completed|completion date|last studied|date)\s*[:\-]\s*(\d{1,2}/\d{1,2}/\d{2,4})",
        ],
        text,
    )


def _known_certification(text: str, provider: str) -> str | None:
    candidates = {
        "microsoft_learn": [
            "Microsoft Azure Fundamentals",
            "Azure Fundamentals",
            "AZ-900",
            "Azure Administrator Associate",
            "AZ-104",
            "Azure AI Fundamentals",
            "AI-900",
        ],
        "aws_skill_builder": [
            "AWS Solutions Architect Associate",
            "AWS Certified Solutions Architect - Associate",
            "AWS Certified Cloud Practitioner",
            "AWS Cloud Practitioner",
            "AWS Developer Associate",
            "AWS SysOps Administrator Associate",
        ],
    }.get(provider, [])
    lowered = text.casefold()
    for candidate in candidates:
        if candidate.casefold() in lowered:
            return candidate
    return None


def _parse_freeform_learning_evidence(text: str, provider: str, evidence_path: str, *, now: str, source_kind: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    progress = _find_progress(text)
    status = _find_status(text, progress)
    completed_date = _find_date(text)
    cert_name = _first_match([r"certification\s*[:\-]\s*(.+)", r"certificate\s*[:\-]\s*(.+)", r"exam\s*[:\-]\s*(.+)"], text) or _known_certification(text, provider)
    course_name = _first_match([r"course\s*[:\-]\s*(.+)", r"learning path\s*[:\-]\s*(.+)", r"transcript\s*[:\-]\s*(.+)"], text)
    module_name = _first_match([r"module\s*[:\-]\s*(.+)", r"unit\s*[:\-]\s*(.+)"], text)
    confidence = 0.9 if (cert_name or course_name or module_name) and (progress is not None or status or completed_date) else 0.65 if (cert_name or course_name or module_name) else 0.35
    base = {
        "provider": PROVIDER_DISPLAY_NAMES[provider],
        "status": status,
        "progress_percent": progress,
        "last_studied": completed_date,
        "next_action": None,
        "source": provider,
        "confidence": confidence,
        "last_updated": now,
        "imported_at": now,
        "evidence_path": evidence_path,
        "import_kind": source_kind,
    }
    certs: list[dict[str, Any]] = []
    courses: list[dict[str, Any]] = []
    modules: list[dict[str, Any]] = []
    manual_review: list[dict[str, Any]] = []
    if cert_name:
        certs.append({"id": stable_id("cert", provider, cert_name), "name": cert_name, **base})
    if course_name:
        courses.append({"id": stable_id("course", provider, course_name), "name": course_name, **base})
    if module_name:
        modules.append({"id": stable_id("module", provider, course_name or cert_name or provider, module_name), "name": module_name, "course": course_name, **base})
    if not (certs or courses or modules):
        manual_review.append({
            "source": provider,
            "confidence": confidence,
            "last_updated": now,
            "imported_at": now,
            "message": "Manual learning evidence did not contain an unambiguous certification, course, or module name; no progress imported.",
            "evidence_path": evidence_path,
            "extracted_text_preview": text[:500],
        })
    elif progress is None and status not in {"completed", "complete"}:
        manual_review.append({
            "source": provider,
            "confidence": confidence,
            "last_updated": now,
            "imported_at": now,
            "message": "Manual learning evidence identified a learning item but no explicit progress/completion value; progress left null.",
            "evidence_path": evidence_path,
            "items": [item.get("name") for item in [*certs, *courses, *modules]],
        })
    return certs, courses, modules, manual_review


def _parse_csv_learning_evidence(text: str, provider: str, evidence_path: str, *, now: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.DictReader(StringIO(text), dialect=dialect))
    if not rows or not rows[0]:
        return _parse_freeform_learning_evidence(text, provider, evidence_path, now=now, source_kind="csv")
    certs: list[dict[str, Any]] = []
    courses: list[dict[str, Any]] = []
    modules: list[dict[str, Any]] = []
    manual_review: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        normalized = {slug(key).replace("-", "_"): (value or "").strip() for key, value in row.items() if key is not None}
        cert_name = normalized.get("certification") or normalized.get("certificate") or normalized.get("exam")
        course_name = normalized.get("course") or normalized.get("learning_path") or normalized.get("title")
        module_name = normalized.get("module") or normalized.get("unit")
        progress = normalize_percent(normalized.get("progress") or normalized.get("progress_percent") or normalized.get("completion") or normalized.get("percent_complete"))
        status = normalized.get("status") or _find_status(" ".join(normalized.values()), progress)
        completed_date = normalized.get("completed") or normalized.get("completed_on") or normalized.get("completion_date") or normalized.get("last_studied") or None
        confidence = 0.92 if (cert_name or course_name or module_name) and (progress is not None or status or completed_date) else 0.65 if (cert_name or course_name or module_name) else 0.35
        base = {
            "provider": PROVIDER_DISPLAY_NAMES[provider],
            "status": slug(status).replace("-", "_") if status else None,
            "progress_percent": progress,
            "last_studied": completed_date,
            "next_action": normalized.get("next_action") or None,
            "source": provider,
            "confidence": confidence,
            "last_updated": now,
            "imported_at": now,
            "evidence_path": evidence_path,
            "import_kind": "csv",
            "source_row": index,
        }
        if cert_name:
            certs.append({"id": stable_id("cert", provider, cert_name), "name": cert_name, **base})
        if course_name:
            courses.append({"id": stable_id("course", provider, course_name), "name": course_name, **base})
        if module_name:
            modules.append({"id": stable_id("module", provider, course_name or cert_name or provider, module_name), "name": module_name, "course": course_name, **base})
        if not (cert_name or course_name or module_name):
            manual_review.append({
                "source": provider,
                "confidence": confidence,
                "last_updated": now,
                "imported_at": now,
                "message": "CSV row did not contain certification, course, or module fields; no progress imported.",
                "evidence_path": evidence_path,
                "source_row": index,
                "row": normalized,
            })
    return certs, courses, modules, manual_review


def _merge_records(existing: list[Any], imported: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {item["id"]: item for item in existing if isinstance(item, dict) and item.get("id")}
    for item in imported:
        old = merged.get(item["id"], {})
        merged[item["id"]] = {**old, **item}
    return sorted(merged.values(), key=lambda item: str(item.get("name") or item.get("id") or ""))


def import_learning_evidence(path: Path, *, provider: str, learning_path: Path | None = None, career_path: Path | None = None, now: str | None = None) -> dict[str, Any]:
    """Import manually supplied learning evidence into Learning Registry.

    This parser is conservative: it only records explicitly extracted names and progress/status.
    Ambiguous extraction is routed to manual_review instead of fabricating progress.
    """
    timestamp = now or utc_now()
    provider = slug(provider).replace("-", "_")
    if provider not in SUPPORTED_MANUAL_IMPORT_PROVIDERS:
        raise ValueError(f"Unsupported learning import provider: {provider}")
    path = path.expanduser()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(str(path))
    learning_path = learning_path or learning_registry_path()
    registry = load_json(learning_path, empty_learning_registry(now=timestamp))
    text, extraction = extract_learning_evidence_text(path)
    evidence_path = str(path)
    if path.suffix.casefold() == ".csv":
        certs, courses, modules, manual_review = _parse_csv_learning_evidence(text, provider, evidence_path, now=timestamp)
    else:
        certs, courses, modules, manual_review = _parse_freeform_learning_evidence(text, provider, evidence_path, now=timestamp, source_kind=extraction.get("kind") or "text")
    if not text.strip():
        manual_review.append({
            "source": provider,
            "confidence": 0.2,
            "last_updated": timestamp,
            "imported_at": timestamp,
            "message": "No text could be extracted from manual learning evidence; install OCR/PDF extraction support or provide a text/CSV export.",
            "evidence_path": evidence_path,
            "extraction": extraction,
        })

    sources = registry.setdefault("sources", {})
    source_record = sources.setdefault(provider, {})
    source_record.update({
        "status": "Connected" if (certs or courses or modules) else "Needs review",
        "source": "manual_import",
        "confidence": max([*(float(item.get("confidence") or 0) for item in [*certs, *courses, *modules]), 0.0]),
        "last_updated": timestamp,
        "last_imported_at": timestamp,
        "evidence_path": evidence_path,
    })
    provider_map = {slug(item.get("name")): item for item in registry.get("providers", []) if isinstance(item, dict)}
    add_provider(provider_map, PROVIDER_DISPLAY_NAMES[provider], source=provider, confidence=source_record["confidence"], now=timestamp, evidence_path=evidence_path)
    registry["providers"] = sorted(provider_map.values(), key=lambda item: item["name"])
    registry["certifications"] = _merge_records(registry.get("certifications", []), certs)
    registry["courses"] = _merge_records(registry.get("courses", []), courses)
    registry["modules"] = _merge_records(registry.get("modules", []), modules)
    registry.setdefault("source_evidence", [])
    for item in [*certs, *courses, *modules]:
        registry["source_evidence"].append(_manual_source_evidence(evidence_path, "learning_record", item.get("name"), provider=provider, confidence=float(item.get("confidence") or 0), now=timestamp))
        if item.get("progress_percent") is not None:
            registry["source_evidence"].append(_manual_source_evidence(evidence_path, "progress_percent", item.get("progress_percent"), provider=provider, confidence=float(item.get("confidence") or 0), now=timestamp))
    registry["manual_review"] = [*(item for item in registry.get("manual_review", []) if isinstance(item, dict)), *manual_review]
    registry["learning_streak"] = compute_learning_streak(registry.get("study_sessions", []), now=timestamp)
    registry["study_recommendations"] = build_recommendations(registry, now=timestamp)
    registry["last_updated"] = timestamp
    write_json(learning_path, registry)
    update_career_registry_with_learning_summary(registry, career_path, now=timestamp)
    return {
        "provider": provider,
        "provider_name": PROVIDER_DISPLAY_NAMES[provider],
        "evidence_path": evidence_path,
        "learning_registry_path": str(learning_path),
        "career_registry_path": str(career_path or career_registry_path()),
        "certifications_imported": len(certs),
        "courses_imported": len(courses),
        "modules_imported": len(modules),
        "manual_review_count": len(manual_review),
        "extraction": extraction,
        "last_updated": timestamp,
    }

def update_career_registry_with_learning_summary(learning_registry: dict[str, Any], career_path: Path | None = None, *, now: str | None = None) -> dict[str, Any]:
    timestamp = now or utc_now()
    career_path = career_path or career_registry_path()
    career = load_json(career_path, {})
    summary = project_learning_summary(learning_registry, now=timestamp)
    career["learning_summary"] = summary
    career["learning_source"] = {
        "registry_path": str(learning_registry_path()),
        "source": "learning_registry_projection",
        "confidence": summary.get("confidence", 0.0),
        "last_updated": timestamp,
        "evidence_path": summary.get("evidence_path"),
    }
    if summary.get("primary_certification"):
        career["current_certification_priority"] = summary["primary_certification"]
    if summary.get("next_learning_task"):
        raw_existing_tasks = career.get("today_tasks")
        existing_tasks = raw_existing_tasks if isinstance(raw_existing_tasks, list) else []
        if summary["next_learning_task"] not in existing_tasks:
            career["today_tasks"] = [summary["next_learning_task"], *existing_tasks]
    career.setdefault("source_connections", {})
    career["source_connections"]["learning_registry"] = {
        "status": "Connected",
        "path": str(learning_registry_path()),
        "source": "learning_registry_projection",
        "confidence": summary.get("confidence", 0.0),
        "last_updated": timestamp,
    }
    write_json(career_path, career)
    return career


def sync_obsidian_learning_registry(*, vault_path: Path | None = None, learning_path: Path | None = None, career_path: Path | None = None, now: str | None = None) -> dict[str, Any]:
    timestamp = now or utc_now()
    registry, report = parse_learning_notes(vault_path, now=timestamp)
    learning_path = learning_path or learning_registry_path()
    write_json(learning_path, registry)
    update_career_registry_with_learning_summary(registry, career_path, now=timestamp)
    report["learning_registry_path"] = str(learning_path)
    report["career_registry_path"] = str(career_path or career_registry_path())
    return report
