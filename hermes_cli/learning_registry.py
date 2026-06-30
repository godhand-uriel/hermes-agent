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
from urllib.parse import urlsplit, urlunsplit
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
            "udemy_browser": {
                "status": "Not connected",
                "source": "browser_connector",
                "confidence": 0.0,
                "last_updated": timestamp,
                "needed_user_action": "Run `hermes learning browser-connect udemy`, log in manually, then run browser-sync.",
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


def project_learning_summary(registry: dict[str, Any], *, now: str | None = None, active_certification: str | None = None) -> dict[str, Any]:
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

    def norm_name(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())

    def certification_matches(item: dict[str, Any], target: str | None) -> bool:
        if not target:
            return False
        item_name = norm_name(item.get("name"))
        target_name = norm_name(target)
        aliases = {
            "awssolutionsarchitectassociate": {"awssaa", "awscertifiedsolutionsarchitectassociate"},
            "security": {"comptiasecurity", "securityplus", "sy0701"},
            "linux": {"comptialinux", "linuxplus", "xk0006"},
            "network": {"comptianetwork", "networkplus", "n10009"},
        }
        return item_name == target_name or item_name in aliases.get(target_name, set()) or target_name in aliases.get(item_name, set()) or item_name in target_name or target_name in item_name

    def priority(item: dict[str, Any]) -> tuple[int, int, int]:
        progress = normalize_percent(item.get("progress_percent"))
        in_progress = str(item.get("status") or "").casefold() in {"in_progress", "studying", "active"}
        active = certification_matches(item, active_certification)
        return (1 if active else 0, 1 if in_progress else 0, progress if progress is not None else -1)

    primary = max(certs, key=priority) if certs else None
    linked_course = None
    if primary and primary.get("linked_course_id"):
        linked_course = next((course for course in courses if course.get("id") == primary.get("linked_course_id")), None)
    weekly_hours = sum(float(item.get("weekly_hours") or item.get("hours") or 0) for item in sessions if isinstance(item, dict))
    active_recommendation = next((item for item in recommendations if primary and item.get("related_record_id") == primary.get("id")), None)
    next_recommendation = active_recommendation or (recommendations[0] if recommendations else None)
    next_task = (primary or {}).get("next_action") or (next_recommendation or {}).get("recommendation")
    risk = "Needs learning source standardization" if not certs and not courses and not modules else "On pace" if next_task else "Needs next action"
    secondary_items = []
    for item in [*certs, *courses]:
        if primary and item.get("id") == primary.get("id"):
            continue
        name = item.get("name")
        if name:
            secondary_items.append({
                "name": name,
                "progress_percent": item.get("progress_percent"),
                "provider": item.get("provider"),
                "source": item.get("source"),
                "status": item.get("status"),
            })
    return {
        "primary_certification": (primary or {}).get("name"),
        "primary_active_learning_target": (primary or {}).get("name"),
        "learning_provider": (linked_course or {}).get("provider") or (primary or {}).get("source") or (primary or {}).get("provider"),
        "course": (linked_course or {}).get("name"),
        "certification_progress": (primary or {}).get("progress_percent"),
        "course_progress_percent": (linked_course or primary or {}).get("progress_percent"),
        "next_learning_task": next_task,
        "study_streak_days": streak.get("current_days") or 0,
        "last_studied": streak.get("last_studied"),
        "weekly_study_hours": weekly_hours,
        "learning_risk": risk,
        "secondary_learning_items": secondary_items[:8],
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


def _find_udemy_progress(text: str) -> tuple[int | None, bool]:
    """Return Udemy progress and whether an explicit progress/start signal was visible."""
    progress = _find_progress(text)
    if progress is not None:
        return progress, True
    if re.search(r"\bSTART\s+COURSE\b", text, flags=re.IGNORECASE):
        return 0, True
    return None, False


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


UDEMY_SOURCE = "udemy_browser"
UDEMY_HEADING_FALLBACK_SOURCE = "udemy_browser_heading_fallback"
UDEMY_PROVIDER_NAME = "Udemy"
UDEMY_LOGIN_URL = "https://www.udemy.com/join/login-popup/"
UDEMY_MY_LEARNING_URL = "https://www.udemy.com/home/my-courses/learning/"
UDEMY_MY_LEARNING_URLS = [
    "https://www.udemy.com/home/my-courses/learning/",
    "https://www.udemy.com/home/my-courses/",
    "https://www.udemy.com/home/my-courses/learning/?p=1",
]
UDEMY_COURSE_CARD_SELECTOR = ", ".join([
    "[data-purpose*='course-card']",
    "[data-purpose*='course-list']",
    "[data-purpose*='enrolled-course']",
    "[data-purpose*='learning-card']",
    "[data-purpose*='progress']",
    "[data-testid*='course-card']",
    "[class*='course-card']",
    "[class*='my-course']",
    "[class*='learning-course']",
    "a[href*='/course/']",
    "a[href*='/learn/']",
    "a[href*='course-dashboard-redirect']",
])
UDEMY_COURSE_CONTAINER_RE = r"(?:course-card|course-list|enrolled-course|learning-card|my-course|learning-course)"
UDEMY_COURSE_DIAGNOSTIC_CONTAINER_RE = r"(?:course-card|course-list|enrolled-course|learning-card|my-course|learning-course|container|progress)"
DEFAULT_UDEMY_CDP_URL = "http://127.0.0.1:9222"


def udemy_session_state_path() -> Path:
    configured = os.environ.get("HERMES_UDEMY_BROWSER_STATE_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    return get_hermes_home() / "browser_sessions" / "udemy_storage_state.json"


def _chmod_0600(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        # POSIX permissions are best-effort on non-POSIX filesystems.
        pass


def _safe_cdp_url_for_output(cdp_url: str) -> str:
    """Return a CDP URL safe for JSON/log output by dropping credentials/query/fragment."""
    try:
        parts = urlsplit(cdp_url)
    except ValueError:
        return "<invalid-cdp-url>"
    hostname = parts.hostname or ""
    if not hostname:
        return cdp_url.split("?", 1)[0].split("#", 1)[0]
    netloc = hostname
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme or "http", netloc, parts.path or "", "", ""))


def _strip_html(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("&amp;", "&").replace("&nbsp;", " ").replace("&#x27;", "'").replace("&quot;", '"')
    return re.sub(r"\s+", " ", value).strip()


def _redact_udemy_debug_text(value: Any, *, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[REDACTED_EMAIL]", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)\b(cookie|token|session|auth|bearer|password|passwd|secret)\b\s*[:=]\s*\S+", r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)(access[_-]?token|id[_-]?token|refresh[_-]?token|client[_-]?secret)=([^&\s]+)", r"\1=[REDACTED]", text)
    text = re.sub(r"\b(?:\d[ -]*?){13,19}\b", "[REDACTED_CARD]", text)
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def _html_attr(fragment: str, name: str) -> str | None:
    match = re.search(rf"\b{name}\s*=\s*(['\"])(.*?)\1", fragment, flags=re.IGNORECASE | re.DOTALL)
    return match.group(2).strip() if match else None


def _first_html_text(fragment: str, selectors: tuple[str, ...]) -> str | None:
    for selector in selectors:
        if selector in {"h3", "h4"}:
            match = re.search(rf"<{selector}\b[^>]*>(.*?)</{selector}>", fragment, flags=re.IGNORECASE | re.DOTALL)
        elif selector == "data-purpose-course-title":
            match = re.search(r"<[^>]+data-purpose\s*=\s*(['\"])[^'\"]*course-title[^'\"]*\1[^>]*>(.*?)</[^>]+>", fragment, flags=re.IGNORECASE | re.DOTALL)
        else:
            match = None
        if match:
            text = _strip_html(match.group(2) if selector == "data-purpose-course-title" else match.group(1))
            if text:
                return text
    return None


def _absolute_udemy_url(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return f"https://www.udemy.com{url}"
    return f"https://www.udemy.com/{url}"


def _first_udemy_course_href(fragment: str) -> str | None:
    for match in re.finditer(r"<a\b[^>]+href\s*=\s*(['\"])([^'\"]*(?:/course/|/learn/|course-dashboard-redirect)[^'\"]*)\1", fragment, flags=re.IGNORECASE | re.DOTALL):
        return match.group(2)
    return None


def _page_url(page: Any) -> str:
    try:
        return str(getattr(page, "url", "") or "")
    except Exception:
        return ""


def _page_title(page: Any) -> str:
    title_fn = getattr(page, "title", None)
    if callable(title_fn):
        try:
            return _redact_udemy_debug_text(title_fn(), limit=120)
        except Exception:
            return ""
    return ""


def _is_udemy_learning_url(url: str) -> bool:
    return "udemy.com/home/my-courses" in url


def _is_udemy_url(url: str) -> bool:
    return "udemy.com" in url


def _find_udemy_learning_page(context: Any) -> Any | None:
    pages = list(getattr(context, "pages", []) or [])
    for page in pages:
        if _is_udemy_learning_url(_page_url(page)):
            return page
    for page in pages:
        if _is_udemy_url(_page_url(page)):
            return page
    return None


def _wait_for_udemy_course_cards(page: Any, *, timeout: int = 10000) -> bool:
    wait_for_selector = getattr(page, "wait_for_selector", None)
    if not callable(wait_for_selector):
        return False
    try:
        wait_for_selector(UDEMY_COURSE_CARD_SELECTOR, timeout=timeout)
        return True
    except Exception:
        return False


def _is_udemy_login_page(url: str, html: str) -> bool:
    lowered_url = url.casefold()
    lowered_html = html.casefold()
    if any(marker in lowered_url for marker in ("/join/login", "/join/signup", "/user/login")):
        return True
    login_markers = ("data-purpose=\"login-form\"", "data-purpose='login-form'", "name=\"email\"", "name='email'", "name=\"password\"", "name='password'")
    if "udemy" in lowered_html and any(marker in lowered_html for marker in login_markers):
        return True
    return False


def _udemy_sync_error(error: str, message: str, *, remote: bool, cdp_url: str | None = None, state_path: Path | None = None, diagnostics: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "success": False,
        "error": error,
        "message": message,
        "remote": remote,
        "cdp_url": _safe_cdp_url_for_output(cdp_url) if remote and cdp_url else None,
        "session_state_path": None if remote else str(state_path) if state_path else None,
        "password_stored": False,
        "screenshots_saved": False,
    }
    if diagnostics:
        result.update(diagnostics)
    return result


def _navigate_udemy_learning_page(page: Any) -> None:
    for url in UDEMY_MY_LEARNING_URLS:
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception as exc:  # noqa: BLE001 - tolerate Udemy aborting document navigation after a usable page commit.
            current_url = _page_url(page)
            if "ERR_ABORTED" in str(exc) and (_is_udemy_learning_url(current_url) or _is_udemy_url(current_url)):
                pass
            elif _is_udemy_learning_url(current_url):
                pass
            else:
                continue
        if _wait_for_udemy_course_cards(page, timeout=10000):
            return


def _read_udemy_learning_html(page: Any, *, remote: bool, cdp_url: str | None = None, state_path: Path | None = None) -> tuple[str | None, dict[str, Any] | None]:
    _wait_for_udemy_course_cards(page, timeout=10000)
    html = page.content()
    page_url = _page_url(page)
    if _is_udemy_login_page(page_url, html):
        return None, _udemy_sync_error(
            "udemy_not_logged_in",
            "Udemy is showing a login page. Log into Udemy in your Chrome/Edge session, then rerun `hermes learning browser-sync udemy --remote`.",
            remote=remote,
            cdp_url=cdp_url,
            state_path=state_path,
        )
    if not _split_udemy_course_cards(html) and not _extract_udemy_heading_candidates(html):
        return None, _udemy_sync_error(
            "no_udemy_courses_detected",
            "Hermes connected to Udemy but could not extract course cards on My Learning. Run with --debug-dom for safe DOM clues.",
            remote=remote,
            cdp_url=cdp_url,
            state_path=state_path,
            diagnostics=_udemy_no_courses_diagnostics(html, page),
        )
    return html, None


def _split_udemy_course_cards(html: str) -> list[str]:
    # Prefer modern Udemy data/class markers; fall back to link-centered chunks.
    marker_re = rf"<(?P<tag>article|li|section|div)\b[^>]*(?:data-purpose|data-testid|class|aria-label)\s*=\s*(['\"])[^'\"]*{UDEMY_COURSE_CONTAINER_RE}[^'\"]*\2[^>]*>"
    matches = list(re.finditer(marker_re, html, flags=re.IGNORECASE))
    cards: list[str] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else min(len(html), match.start() + 10000)
        fragment = html[match.start():end]
        text = _strip_html(fragment)
        if re.search(r"/course/|/learn/|course-dashboard-redirect|%\s*complete|\bSTART\s+COURSE\b|\bcomplete\b|\blectures\b|\bmin left\b|\bhours?\b", fragment + " " + text, flags=re.IGNORECASE):
            cards.append(fragment)
    if cards:
        return cards
    link_matches = list(re.finditer(r"<a\b[^>]+href\s*=\s*(['\"])([^'\"]*(?:/course/|/learn/|course-dashboard-redirect)[^'\"]*)\1[^>]*>.*?</a>", html, flags=re.IGNORECASE | re.DOTALL))
    for match in link_matches:
        start = max(0, match.start() - 1800)
        end = min(len(html), match.end() + 2200)
        cards.append(html[start:end])
    return cards


def _udemy_course_link_count(html: str) -> int:
    return len(re.findall(r"<a\b[^>]+href\s*=\s*(['\"])[^'\"]*(?:/course/|/learn/|course-dashboard-redirect)" , html, flags=re.IGNORECASE))


_UDEMY_NAVIGATION_HEADINGS = {
    "my learning",
    "all courses",
    "my lists",
    "wishlist",
    "certifications",
    "archived",
    "learning tools",
    "schedule learning time",
    "explore top skills and certifications",
    "in-demand careers",
    "web development",
    "it certifications",
    "leadership",
}

_UDEMY_HEADING_FALLBACK_BLOCKLIST = {
    *_UDEMY_NAVIGATION_HEADINGS,
    "new & featured",
    "certifications by skill",
    "data science",
    "communication",
    "business analytics & intelligence",
    "about",
    "discover udemy",
    "udemy for business",
    "legal & accessibility",
    "cookie preferences",
    "your privacy",
    "strictly necessary cookies",
    "sale of personal information",
    "cookie list",
}

_UDEMY_COURSE_LIKE_TITLE_RE = re.compile(
    r"\b(?:course|bootcamp|practice\s+exam|exam|certified|certification|getting\s+certified|"
    r"comptia|network\+|security\+|cysa\+|linux\+|ccna|aws|solutions\s+architect|python|"
    r"n10-\d+|cs0-\d+|sy0-\d+|xk0-\d+|200-301)\b",
    flags=re.IGNORECASE,
)

_UDEMY_COURSE_LIST_STOP_HEADINGS = {
    "learning tools",
    "schedule learning time",
    "explore top skills and certifications",
    "in-demand careers",
    "web development",
    "it certifications",
    "new & featured",
    "certifications by skill",
    "discover udemy",
    "udemy for business",
    "legal & accessibility",
    "your privacy",
    "cookie preferences",
}


def _is_udemy_navigation_heading(title: str) -> bool:
    normalized = re.sub(r"\s+", " ", title or "").strip().casefold()
    return normalized in _UDEMY_HEADING_FALLBACK_BLOCKLIST


def _is_udemy_heading_candidate(title: str) -> bool:
    normalized = re.sub(r"\s+", " ", title or "").strip()
    return bool(normalized) and not _is_udemy_navigation_heading(normalized)


def _extract_udemy_my_learning_course_region(html: str) -> str:
    """Return the bounded My Learning course-list region used by heading fallback."""
    heading_re = re.compile(r"<h(?P<level>[1-6])\b[^>]*>(?P<text>.*?)</h[1-6]>", flags=re.IGNORECASE | re.DOTALL)
    headings = list(heading_re.finditer(html))
    start: int | None = None
    for match in headings:
        title = _strip_html(match.group("text")).casefold()
        if title == "all courses":
            start = match.end()
            break
        if start is None and title == "my learning":
            start = match.end()
    if start is None:
        return ""

    end = len(html)
    structural_stop = re.search(
        r"<(?:footer|nav)\b|\brole\s*=\s*(['\"])contentinfo\1|\b(?:id|class|data-purpose)\s*=\s*(['\"])[^'\"]*(?:footer|cookie|privacy|category|marketing)[^'\"]*\2",
        html[start:],
        flags=re.IGNORECASE | re.DOTALL,
    )
    if structural_stop:
        end = min(end, start + structural_stop.start())

    for match in headings:
        if match.start() <= start:
            continue
        level = int(match.group("level"))
        title = re.sub(r"\s+", " ", _strip_html(match.group("text"))).strip().casefold()
        if level <= 2 and title in _UDEMY_COURSE_LIST_STOP_HEADINGS:
            end = min(end, match.start())
            break
    return html[start:end]


def _udemy_heading_has_course_signal(title: str, fragment: str) -> bool:
    text = _strip_html(fragment)
    haystack = f"{title} {text}"
    if _UDEMY_COURSE_LIKE_TITLE_RE.search(title):
        return True
    if re.search(r"<button\b[^>]*(?:aria-label\s*=\s*(['\"])[^'\"]*(?:rating|star|review)[^'\"]*\1)[^>]*>|<button\b[^>]*>.*?(?:rating|star|review).*?</button>", fragment, flags=re.IGNORECASE | re.DOTALL):
        return True
    if re.search(UDEMY_COURSE_DIAGNOSTIC_CONTAINER_RE, fragment, flags=re.IGNORECASE):
        return True
    if re.search(r"\b(?:instructor|progress|%\s*(?:complete|completed)?|lectures?|lessons?|course\s+content)\b", haystack, flags=re.IGNORECASE):
        return True
    if re.search(r"\b(?:all courses|in progress|completed|archived)\b", text, flags=re.IGNORECASE) and _UDEMY_COURSE_LIKE_TITLE_RE.search(haystack):
        return True
    return False


def _extract_udemy_heading_candidates(html: str) -> list[dict[str, Any]]:
    if _udemy_course_link_count(html) > 0:
        return []
    region = _extract_udemy_my_learning_course_region(html)
    if not region:
        return []
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    heading_re = re.compile(r"<h[2-4]\b[^>]*>(.*?)</h[2-4]>", flags=re.IGNORECASE | re.DOTALL)
    for match in heading_re.finditer(region):
        title = _strip_html(match.group(1))
        if not _is_udemy_heading_candidate(title):
            continue
        key = slug(title)
        if key in seen:
            continue
        start = max(0, match.start() - 1200)
        end = min(len(region), match.end() + 1800)
        fragment = region[start:end]
        if not _udemy_heading_has_course_signal(title, fragment):
            continue
        seen.add(key)
        candidates.append({"title": title, "progress_percent": normalize_percent(_find_progress(_strip_html(fragment))), "raw_text": _strip_html(fragment)[:1000]})
    return candidates


def _udemy_heading_candidate_count(html: str) -> int:
    return len(_extract_udemy_heading_candidates(html))


def _udemy_candidate_container_count(html: str) -> int:
    return len(re.findall(rf"<(?P<tag>article|li|section|div)\b[^>]*(?:data-purpose|data-testid|class|aria-label)\s*=\s*(['\"])[^'\"]*{UDEMY_COURSE_DIAGNOSTIC_CONTAINER_RE}[^'\"]*\2", html, flags=re.IGNORECASE))


def _udemy_no_courses_diagnostics(html: str, page: Any | None = None) -> dict[str, Any]:
    return {
        "current_url": _safe_cdp_url_for_output(_page_url(page)) if page is not None else None,
        "title": _page_title(page) if page is not None else None,
        "course_link_count": _udemy_course_link_count(html),
        "candidate_container_count": _udemy_candidate_container_count(html),
        "heading_candidate_count": _udemy_heading_candidate_count(html),
        "recommendation": "run --debug-dom",
    }

def _extract_udemy_course(card: str) -> dict[str, Any]:
    text = _strip_html(card)
    url = _absolute_udemy_url(_first_udemy_course_href(card) or _html_attr(card, "href"))
    title = (
        _html_attr(card, "data-course-title")
        or _first_html_text(card, ("data-purpose-course-title", "h3", "h4"))
        or _first_match([r"(?:Course|Title)\s*[:\-]\s*([^|\n]+?)(?: Instructor| Progress|$)"], text)
    )
    if not title:
        anchor = re.search(r"<a\b[^>]+href\s*=\s*(['\"])[^'\"]*(?:/course/|/learn/|course-dashboard-redirect)[^'\"]*\1[^>]*>(.*?)</a>", card, flags=re.IGNORECASE | re.DOTALL)
        title = _strip_html(anchor.group(2)) if anchor else None
    progress = normalize_percent(_html_attr(card, "data-progress") or _html_attr(card, "aria-valuenow"))
    progress_visible = progress is not None
    if progress is None:
        progress, progress_visible = _find_udemy_progress(text)
    lectures = re.search(r"(\d+)\s*/\s*(\d+)\s+(?:lectures|lessons|items)", text, flags=re.IGNORECASE)
    completed_lectures = int(lectures.group(1)) if lectures else None
    total_lectures = int(lectures.group(2)) if lectures else None
    if progress is None and completed_lectures is not None and total_lectures:
        progress = normalize_percent((completed_lectures / total_lectures) * 100)
    instructor = _first_match([r"Instructor\s*[:\-]\s*([^|]+?)(?: Progress| Last accessed| Certificate| \d+\s*%|$)", r"By\s+([^|]+?)(?: Progress| Last accessed|$)"], text)
    last_accessed = _first_match([r"Last accessed\s*[:\-]\s*([^|]+?)(?: Certificate| Instructor|$)", r"Accessed\s*[:\-]\s*([^|]+?)(?: Certificate|$)"], text)
    certificate_url = None
    cert_match = re.search(r"<a\b[^>]+href\s*=\s*(['\"])([^'\"]*(?:certificate|completion)[^'\"]*)\1", card, flags=re.IGNORECASE)
    if cert_match:
        certificate_url = _absolute_udemy_url(cert_match.group(2))
    elif re.search(r"\b(certificate|certification of completion)\b", text, flags=re.IGNORECASE) and progress == 100:
        certificate_url = url
    return {
        "title": title.strip() if title else None,
        "course_url": url,
        "progress_percent": progress,
        "progress_visible": progress_visible,
        "completed_lectures": completed_lectures,
        "total_lectures": total_lectures,
        "last_accessed": last_accessed,
        "certificate_url": certificate_url,
        "instructor": instructor,
        "raw_text": text[:1000],
    }


def parse_udemy_learning_html(html: str, *, now: str | None = None, evidence_url: str | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    timestamp = now or utc_now()
    courses: list[dict[str, Any]] = []
    manual_review: list[dict[str, Any]] = []
    seen: set[str] = set()
    for card in _split_udemy_course_cards(html):
        extracted = _extract_udemy_course(card)
        title = extracted.get("title")
        progress = normalize_percent(extracted.get("progress_percent"))
        progress_visible = bool(extracted.get("progress_visible"))
        url = extracted.get("course_url")
        if not title or not progress_visible:
            manual_review.append({
                "source": UDEMY_SOURCE,
                "confidence": 0.35 if title else 0.2,
                "last_updated": timestamp,
                "message": "Udemy course card was ambiguous; title or explicit progress was missing, so no progress was imported.",
                "evidence_url": url,
                "evidence_path": url,
                "course_title": title,
                "extracted_text_preview": extracted.get("raw_text"),
            })
            continue
        if progress is None:
            manual_review.append({
                "source": UDEMY_SOURCE,
                "confidence": 0.35,
                "last_updated": timestamp,
                "message": "Udemy course card was ambiguous; title or explicit progress was missing, so no progress was imported.",
                "evidence_url": url,
                "evidence_path": url,
                "course_title": title,
                "extracted_text_preview": extracted.get("raw_text"),
            })
            continue
        key = slug(url or title)
        if key in seen:
            continue
        seen.add(key)
        confidence = 0.9 if url else 0.75
        if extracted.get("completed_lectures") is not None and extracted.get("total_lectures") is not None:
            confidence = max(confidence, 0.92)
        courses.append({
            "id": stable_id("course", UDEMY_PROVIDER_NAME, title),
            "name": title,
            "provider": UDEMY_PROVIDER_NAME,
            "status": "completed" if progress == 100 else "in_progress" if progress > 0 else "not_started" if progress == 0 else None,
            "progress_percent": progress,
            "completed_lectures": extracted.get("completed_lectures"),
            "total_lectures": extracted.get("total_lectures"),
            "last_studied": extracted.get("last_accessed"),
            "last_accessed": extracted.get("last_accessed"),
            "certificate_url": extracted.get("certificate_url"),
            "instructor": extracted.get("instructor"),
            "course_url": url,
            "source": UDEMY_SOURCE,
            "confidence": confidence,
            "last_updated": timestamp,
            "imported_at": timestamp,
            "evidence_path": url or f"udemy:{slug(title)}",
            "evidence_url": url,
        })
    if not courses and _udemy_course_link_count(html) == 0:
        fallback_evidence_url = evidence_url or UDEMY_MY_LEARNING_URL
        for extracted in _extract_udemy_heading_candidates(html):
            title = str(extracted.get("title") or "").strip()
            if not title:
                continue
            key = slug(title)
            if key in seen:
                continue
            seen.add(key)
            progress = normalize_percent(extracted.get("progress_percent"))
            if progress is None:
                manual_review.append({
                    "source": UDEMY_HEADING_FALLBACK_SOURCE,
                    "confidence": 0.65,
                    "last_updated": timestamp,
                    "message": "Udemy course imported from heading, but progress percentage was not visible.",
                    "course_title": title,
                    "evidence_url": fallback_evidence_url,
                    "evidence_path": fallback_evidence_url,
                    "extracted_text_preview": extracted.get("raw_text"),
                })
            courses.append({
                "id": stable_id("course", UDEMY_PROVIDER_NAME, title),
                "name": title,
                "provider": UDEMY_PROVIDER_NAME,
                "status": "completed" if progress == 100 else "in_progress" if progress and progress > 0 else None,
                "progress_percent": progress,
                "completed_lectures": None,
                "total_lectures": None,
                "last_studied": None,
                "last_accessed": None,
                "certificate_url": None,
                "instructor": None,
                "course_url": None,
                "source": UDEMY_HEADING_FALLBACK_SOURCE,
                "confidence": 0.65,
                "last_updated": timestamp,
                "imported_at": timestamp,
                "evidence_path": fallback_evidence_url,
                "evidence_url": fallback_evidence_url,
            })
    return courses, manual_review


def _udemy_certification_for_course(title: str) -> str | None:
    normalized = title.casefold()
    if "comptia security+" in normalized or "security+" in normalized or "sy0-" in normalized:
        return "Security+"
    if "comptia linux+" in normalized or "linux+" in normalized or "xk0-" in normalized:
        return "Linux+"
    if "comptia network+" in normalized or "network+" in normalized or "n10-" in normalized:
        return "Network+"
    if "comptia cysa+" in normalized or "cysa+" in normalized or "cs0-" in normalized:
        return "CySA+"
    if "cisco ccna" in normalized or "ccna" in normalized or "200-301" in normalized:
        return "CCNA"
    has_aws = "aws" in normalized or "amazon web services" in normalized
    has_saa = any(token in normalized for token in ("saa", "solutions architect associate", "solution architect associate"))
    if has_aws and has_saa:
        return "AWS Solutions Architect Associate"
    return None


def _udemy_certification_provider(cert_name: str) -> str:
    if cert_name in {"Security+", "Linux+", "Network+", "CySA+"}:
        return "CompTIA"
    if cert_name == "CCNA":
        return "Cisco"
    if cert_name == "AWS Solutions Architect Associate":
        return "AWS"
    return UDEMY_PROVIDER_NAME


def _merge_records_preserving_confirmed(existing: list[Any], imported: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {item["id"]: item for item in existing if isinstance(item, dict) and item.get("id")}
    for item in imported:
        old = merged.get(item["id"])
        if old:
            old_source = str(old.get("source") or "")
            old_confirmed = bool(old.get("manual_confirmed") or old.get("confirmed")) or old_source in {"manual", "manual_import", "obsidian"}
            old_updated = str(old.get("last_updated") or "")
            new_updated = str(item.get("last_updated") or "")
            if old_confirmed and old_updated and new_updated and old_updated > new_updated:
                continue
            merged[item["id"]] = {**old, **item}
        else:
            merged[item["id"]] = item
    return sorted(merged.values(), key=lambda row: str(row.get("name") or row.get("id") or ""))


def apply_udemy_courses_to_learning_registry(courses: list[dict[str, Any]], *, manual_review: list[dict[str, Any]] | None = None, learning_path: Path | None = None, career_path: Path | None = None, now: str | None = None) -> dict[str, Any]:
    timestamp = now or utc_now()
    learning_path = learning_path or learning_registry_path()
    registry = load_json(learning_path, empty_learning_registry(now=timestamp))
    imported_courses = [{**course, "last_updated": course.get("last_updated") or timestamp, "imported_at": course.get("imported_at") or timestamp} for course in courses]
    certifications: list[dict[str, Any]] = []
    cert_seen: set[str] = set()
    for course in imported_courses:
        cert_name = _udemy_certification_for_course(str(course.get("name") or ""))
        if not cert_name:
            if any(keyword in str(course.get("name") or "").casefold() for keyword in ("aws", "cert", "exam")):
                (manual_review or []).append({
                    "source": UDEMY_SOURCE,
                    "confidence": 0.45,
                    "last_updated": timestamp,
                    "message": "Udemy course may relate to a certification, but the title did not clearly map to a supported certification.",
                    "course_title": course.get("name"),
                    "evidence_url": course.get("course_url"),
                    "evidence_path": course.get("evidence_path"),
                })
            continue
        cert_provider = _udemy_certification_provider(cert_name)
        cert_id = stable_id("cert", cert_provider, cert_name)
        if cert_id in cert_seen:
            continue
        cert_seen.add(cert_id)
        course_source = str(course.get("source") or UDEMY_SOURCE)
        certifications.append({
            "id": cert_id,
            "name": cert_name,
            "provider": cert_provider,
            "status": course.get("status"),
            "progress_percent": course.get("progress_percent"),
            "last_studied": course.get("last_studied"),
            "next_action": None if course.get("progress_percent") == 100 else f"Continue Udemy course: {course.get('name')}",
            "source": course_source,
            "confidence": min(0.9, float(course.get("confidence") or 0.8)),
            "last_updated": course.get("last_updated") or timestamp,
            "imported_at": course.get("imported_at") or timestamp,
            "evidence_path": course.get("evidence_path"),
            "evidence_url": course.get("evidence_url"),
            "linked_course_id": course.get("id"),
        })
    provider_map = {slug(item.get("name")): item for item in registry.get("providers", []) if isinstance(item, dict)}
    add_provider(provider_map, UDEMY_PROVIDER_NAME, source=UDEMY_SOURCE, confidence=max([float(course.get("confidence") or 0) for course in imported_courses], default=0.0), now=timestamp, evidence_path=(imported_courses[0].get("evidence_path") if imported_courses else None))
    registry["providers"] = sorted(provider_map.values(), key=lambda item: item["name"])
    registry["courses"] = _merge_records_preserving_confirmed(registry.get("courses", []), imported_courses)
    registry["certifications"] = _merge_records_preserving_confirmed(registry.get("certifications", []), certifications)
    imported_titles = {str(course.get("name") or "") for course in imported_courses if course.get("name")}
    stale_progress_messages = {
        "Udemy course card was ambiguous; title or explicit progress was missing, so no progress was imported.",
        "Udemy course imported from heading, but progress percentage was not visible.",
    }
    registry.setdefault("manual_review", [])
    registry["manual_review"] = [
        *(
            item
            for item in registry.get("manual_review", [])
            if isinstance(item, dict)
            and not (
                str(item.get("source") or "") in {UDEMY_SOURCE, UDEMY_HEADING_FALLBACK_SOURCE}
                and str(item.get("message") or "") in stale_progress_messages
                and (not item.get("course_title") or str(item.get("course_title")) in imported_titles)
            )
        ),
        *(manual_review or []),
    ]
    registry.setdefault("source_evidence", [])
    existing_evidence = {(item.get("source"), item.get("field"), item.get("evidence_path"), str(item.get("value"))) for item in registry["source_evidence"] if isinstance(item, dict)}
    for course in imported_courses:
        course_source = str(course.get("source") or UDEMY_SOURCE)
        for field in ("progress_percent", "course_url", "completed_lectures", "total_lectures", "certificate_url", "instructor"):
            value = course.get(field)
            if value in (None, ""):
                continue
            key = (course_source, field, course.get("evidence_path"), str(value))
            if key in existing_evidence:
                continue
            registry["source_evidence"].append({
                "field": field,
                "value": value,
                "source": course_source,
                "confidence": course.get("confidence", 0.8),
                "last_updated": timestamp,
                "evidence_path": course.get("evidence_path"),
                "evidence_url": course.get("evidence_url"),
                "course_id": course.get("id"),
            })
            existing_evidence.add(key)
    sources = registry.setdefault("sources", {})
    source_names = sorted({str(course.get("source") or UDEMY_SOURCE) for course in imported_courses} | {str(item.get("source") or UDEMY_SOURCE) for item in (manual_review or []) if isinstance(item, dict)} | {UDEMY_SOURCE})
    for source_name in source_names:
        source_courses = [course for course in imported_courses if str(course.get("source") or UDEMY_SOURCE) == source_name]
        source_reviews = [item for item in (manual_review or []) if isinstance(item, dict) and str(item.get("source") or UDEMY_SOURCE) == source_name]
        sources[source_name] = {
            "status": "Connected" if source_courses else "Needs review",
            "source": source_name,
            "confidence": max([float(course.get("confidence") or 0) for course in source_courses], default=0.0),
            "last_updated": timestamp,
            "last_sync": timestamp,
            "session_state_path": str(udemy_session_state_path()),
            "courses_imported": len(source_courses),
            "manual_review_count": len(source_reviews),
        }
    registry["learning_streak"] = compute_learning_streak(registry.get("study_sessions", []), now=timestamp)
    registry["study_recommendations"] = build_recommendations(registry, now=timestamp)
    registry["last_updated"] = timestamp
    write_json(learning_path, registry)
    update_career_registry_with_learning_summary(registry, career_path, now=timestamp)
    return registry


def import_udemy_browser_html(html: str, *, learning_path: Path | None = None, career_path: Path | None = None, now: str | None = None, evidence_url: str | None = None) -> dict[str, Any]:
    timestamp = now or utc_now()
    courses, manual_review = parse_udemy_learning_html(html, now=timestamp, evidence_url=evidence_url)
    registry = apply_udemy_courses_to_learning_registry(courses, manual_review=manual_review, learning_path=learning_path, career_path=career_path, now=timestamp)
    report_source = UDEMY_HEADING_FALLBACK_SOURCE if courses and all(course.get("source") == UDEMY_HEADING_FALLBACK_SOURCE for course in courses) else UDEMY_SOURCE
    return {
        "source": report_source,
        "courses_imported": len(courses),
        "manual_review_count": len(manual_review),
        "learning_registry_path": str(learning_path or learning_registry_path()),
        "career_registry_path": str(career_path or career_registry_path()),
        "last_updated": timestamp,
        "course_titles": [course.get("name") for course in courses],
        "certifications": [cert.get("name") for cert in registry.get("certifications", []) if isinstance(cert, dict) and cert.get("source") in {UDEMY_SOURCE, UDEMY_HEADING_FALLBACK_SOURCE}],
    }


def _safe_dom_debug_from_html(html: str, *, page: Any | None = None) -> dict[str, Any]:
    def _texts(pattern: str, limit: int = 20) -> list[str]:
        values: list[str] = []
        for match in re.finditer(pattern, html, flags=re.IGNORECASE | re.DOTALL):
            value = _redact_udemy_debug_text(_strip_html(match.group(1)), limit=120)
            if value and value not in values:
                values.append(value)
            if len(values) >= limit:
                break
        return values

    candidates = []
    for card in _split_udemy_course_cards(html)[:12]:
        candidates.append({
            "text": _redact_udemy_debug_text(_strip_html(card), limit=220),
            "class": _redact_udemy_debug_text(_html_attr(card, "class") or "", limit=120),
            "data_purpose": _redact_udemy_debug_text(_html_attr(card, "data-purpose") or "", limit=120),
            "aria_label": _redact_udemy_debug_text(_html_attr(card, "aria-label") or "", limit=120),
        })
    return {
        "success": True,
        "provider": "udemy",
        "debug_dom": True,
        "current_url": _safe_cdp_url_for_output(_page_url(page)) if page is not None else None,
        "title": _page_title(page) if page is not None else None,
        "headings": _texts(r"<h[1-4]\b[^>]*>(.*?)</h[1-4]>", 20),
        "buttons": _texts(r"<button\b[^>]*>(.*?)</button>", 30),
        "links": _texts(r"<a\b[^>]*>(.*?)</a>", 40),
        "candidate_containers": candidates,
        "course_link_count": _udemy_course_link_count(html),
        "candidate_container_count": _udemy_candidate_container_count(html),
        "password_stored": False,
        "screenshots_saved": False,
        "storage_read": False,
        "cookies_read": False,
    }


def _safe_udemy_dom_debug(page: Any) -> dict[str, Any]:
    evaluate = getattr(page, "evaluate", None)
    if callable(evaluate):
        try:
            data = evaluate(
                r"""
                () => {
                  const txt = (v, n=160) => (v || '').replace(/\s+/g, ' ').trim().slice(0, n);
                  const arr = (sel, n=30) => Array.from(document.querySelectorAll(sel)).filter(e => e.offsetParent !== null).slice(0, n).map(e => txt(e.innerText || e.textContent || e.getAttribute('aria-label') || '', 160)).filter(Boolean);
                  const candidates = Array.from(document.querySelectorAll('[data-purpose], [data-testid], [class], [aria-label], a[href*="/course/"], a[href*="/learn/"]')).filter(e => {
                    const s = `${e.getAttribute('data-purpose')||''} ${e.getAttribute('data-testid')||''} ${e.className||''} ${e.getAttribute('aria-label')||''} ${e.getAttribute('href')||''} ${e.innerText||''}`.toLowerCase();
                    return /course-card|course-list|enrolled-course|learning-card|my-course|learning-course|progress|\/course\/|\/learn\/|% complete|lectures|min left|hours?/.test(s);
                  }).slice(0, 12).map(e => ({
                    text: txt(e.innerText || e.textContent || '', 220),
                    class: txt(typeof e.className === 'string' ? e.className : '', 120),
                    data_purpose: txt(e.getAttribute('data-purpose') || '', 120),
                    aria_label: txt(e.getAttribute('aria-label') || '', 120)
                  }));
                  return {headings: arr('h1,h2,h3,h4', 20), buttons: arr('button,[role="button"]', 30), links: arr('a[href]', 40), candidate_containers: candidates, title: document.title || ''};
                }
                """
            )
            html = page.content()
            safe = _safe_dom_debug_from_html(html, page=page)
            if isinstance(data, dict):
                for key in ("headings", "buttons", "links"):
                    safe[key] = [_redact_udemy_debug_text(item, limit=160) for item in data.get(key, []) if _redact_udemy_debug_text(item, limit=160)]
                safe["candidate_containers"] = [
                    {k: _redact_udemy_debug_text(v, limit=220 if k == "text" else 120) for k, v in item.items() if k in {"text", "class", "data_purpose", "aria_label"}}
                    for item in data.get("candidate_containers", [])[:12]
                    if isinstance(item, dict)
                ]
                safe["title"] = _redact_udemy_debug_text(data.get("title") or safe.get("title"), limit=120)
            return safe
        except Exception:
            pass
    return _safe_dom_debug_from_html(page.content(), page=page)


def debug_udemy_browser_dom(*, state_path: Path | None = None, headless: bool = True, remote: bool = False, cdp_url: str = DEFAULT_UDEMY_CDP_URL, html_override: str | None = None) -> dict[str, Any]:
    if html_override is not None:
        return _safe_dom_debug_from_html(html_override)
    state_path = state_path or udemy_session_state_path()
    if not remote and not state_path.exists():
        return {"success": False, "error": "missing_session", "message": "Run `hermes learning browser-connect udemy` first.", "session_state_path": str(state_path), "password_stored": False, "screenshots_saved": False}
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": "playwright_not_installed", "message": "Install Playwright and Chromium to use Udemy browser debug.", "details": type(exc).__name__, "session_state_path": None if remote else str(state_path), "password_stored": False, "screenshots_saved": False}
    with sync_playwright() as pw:
        if remote:
            try:
                browser = pw.chromium.connect_over_cdp(cdp_url)
            except Exception as exc:  # noqa: BLE001
                return _cdp_connection_error(cdp_url, exc)
            try:
                page, _context = _remote_cdp_page(browser, prefer_udemy_learning=True)
                if not _is_udemy_learning_url(_page_url(page)):
                    _navigate_udemy_learning_page(page)
                report = _safe_udemy_dom_debug(page)
                report.update({"remote": True, "cdp_url": _safe_cdp_url_for_output(cdp_url), "session_state_path": None})
                return report
            finally:
                _close_remote_cdp_connection(browser)
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=str(state_path))
        page = context.new_page()
        _navigate_udemy_learning_page(page)
        report = _safe_udemy_dom_debug(page)
        browser.close()
        report.update({"remote": False, "cdp_url": None, "session_state_path": str(state_path)})
        return report


def _cdp_connection_error(cdp_url: str, exc: Exception) -> dict[str, Any]:
    safe_cdp_url = _safe_cdp_url_for_output(cdp_url)
    return {
        "success": False,
        "error": "cdp_connection_failed",
        "message": (
            f"Could not connect to Chrome/Edge at {safe_cdp_url}. Start Chrome or Edge with "
            "--remote-debugging-port=9222 and, if Hermes runs on a VPS, create an SSH tunnel: "
            "ssh -L 9222:127.0.0.1:9222 yuu@<VPS_IP>."
        ),
        "details": type(exc).__name__,
        "cdp_url": safe_cdp_url,
        "remote": True,
        "password_stored": False,
        "screenshots_saved": False,
    }


def _remote_cdp_page(browser: Any, *, prefer_udemy_learning: bool = False) -> Any:
    contexts = list(getattr(browser, "contexts", []) or [])
    context = contexts[0] if contexts else browser.new_context()
    if prefer_udemy_learning:
        udemy_page = _find_udemy_learning_page(context)
        if udemy_page is not None:
            return udemy_page, context
    pages = list(getattr(context, "pages", []) or [])
    return (pages[0] if pages else context.new_page()), context


def _close_remote_cdp_connection(browser: Any) -> None:
    # Playwright's CDP connection is external to Hermes. Best effort only; never
    # close contexts/pages because those belong to the user's local browser session.
    disconnect = getattr(browser, "disconnect", None)
    if callable(disconnect):
        try:
            disconnect()
        except Exception:
            pass


def connect_udemy_browser_session(*, state_path: Path | None = None, headless: bool = False, remote: bool = False, cdp_url: str = DEFAULT_UDEMY_CDP_URL) -> dict[str, Any]:
    state_path = state_path or udemy_session_state_path()
    if not remote:
        state_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "error": "playwright_not_installed",
            "message": "Install Playwright in the Hermes venv, then run `python -m playwright install chromium`.",
            "details": str(exc),
            "session_state_path": str(state_path),
            "password_stored": False,
        }
    with sync_playwright() as pw:
        if remote:
            try:
                browser = pw.chromium.connect_over_cdp(cdp_url)
            except Exception as exc:  # noqa: BLE001
                return _cdp_connection_error(cdp_url, exc)
            try:
                page, _context = _remote_cdp_page(browser)
                page.goto(UDEMY_LOGIN_URL, wait_until="domcontentloaded")
                print("Udemy login page opened in your remote Chrome/Edge session. Log in locally, then press Enter here. Passwords, cookies, session tokens, and screenshots are never logged by Hermes.")
                input()
            finally:
                _close_remote_cdp_connection(browser)
            return {
                "success": True,
                "provider": "udemy",
                "remote": True,
                "cdp_url": _safe_cdp_url_for_output(cdp_url),
                "session_exists": False,
                "session_state_path": None,
                "file_mode": None,
                "password_stored": False,
                "screenshots_saved": False,
                "message": "Connected to remote Chrome/Edge through Playwright CDP. No Udemy password, cookies, session tokens, screenshots, or browser storage state were stored by Hermes.",
            }
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=str(state_path) if state_path.exists() else None)
        page = context.new_page()
        page.goto(UDEMY_LOGIN_URL, wait_until="domcontentloaded")
        print("Udemy login page opened. Log in manually in the browser window, then press Enter here to save cookie/session state. Passwords are never read or stored.")
        input()
        context.storage_state(path=str(state_path))
        browser.close()
    _chmod_0600(state_path)
    return {
        "success": True,
        "provider": "udemy",
        "remote": False,
        "session_exists": state_path.exists(),
        "session_state_path": str(state_path),
        "file_mode": oct(state_path.stat().st_mode & 0o777) if state_path.exists() else None,
        "password_stored": False,
        "screenshots_saved": False,
        "message": "Udemy browser session saved. Only Playwright cookie/storage state was written; no username or password was stored.",
    }


def sync_udemy_browser_learning(*, state_path: Path | None = None, learning_path: Path | None = None, career_path: Path | None = None, now: str | None = None, html_override: str | None = None, headless: bool = True, remote: bool = False, cdp_url: str = DEFAULT_UDEMY_CDP_URL, debug_dom: bool = False) -> dict[str, Any]:
    timestamp = now or utc_now()
    state_path = state_path or udemy_session_state_path()
    html = html_override
    evidence_url = UDEMY_MY_LEARNING_URL if html_override is not None else None
    if html is None:
        if not remote and not state_path.exists():
            return {"success": False, "error": "missing_session", "message": "Run `hermes learning browser-connect udemy` first.", "session_state_path": str(state_path)}
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": "playwright_not_installed", "message": "Install Playwright and Chromium to use Udemy browser sync.", "details": str(exc), "session_state_path": str(state_path)}
        with sync_playwright() as pw:
            if remote:
                try:
                    browser = pw.chromium.connect_over_cdp(cdp_url)
                except Exception as exc:  # noqa: BLE001
                    return _cdp_connection_error(cdp_url, exc)
                try:
                    page, _context = _remote_cdp_page(browser, prefer_udemy_learning=True)
                    existing_html = page.content() if _is_udemy_learning_url(_page_url(page)) else ""
                    if not _split_udemy_course_cards(existing_html):
                        _navigate_udemy_learning_page(page)
                    if debug_dom:
                        report = _safe_udemy_dom_debug(page)
                        report.update({"remote": True, "cdp_url": _safe_cdp_url_for_output(cdp_url), "session_state_path": None})
                        return report
                    html, sync_error = _read_udemy_learning_html(page, remote=True, cdp_url=cdp_url)
                    evidence_url = _safe_cdp_url_for_output(_page_url(page))
                    if sync_error:
                        return sync_error
                finally:
                    _close_remote_cdp_connection(browser)
            else:
                browser = pw.chromium.launch(headless=headless)
                context = browser.new_context(storage_state=str(state_path))
                page = context.new_page()
                _navigate_udemy_learning_page(page)
                if debug_dom:
                    report = _safe_udemy_dom_debug(page)
                    browser.close()
                    report.update({"remote": False, "cdp_url": None, "session_state_path": str(state_path)})
                    return report
                html, sync_error = _read_udemy_learning_html(page, remote=False, state_path=state_path)
                evidence_url = _safe_cdp_url_for_output(_page_url(page))
                if sync_error:
                    browser.close()
                    return sync_error
                context.storage_state(path=str(state_path))
                browser.close()
                _chmod_0600(state_path)
    if debug_dom and html is not None:
        report = _safe_dom_debug_from_html(html)
        report.update({"remote": remote, "cdp_url": _safe_cdp_url_for_output(cdp_url) if remote else None, "session_state_path": None if remote else str(state_path)})
        return report
    if html is None:
        return _udemy_sync_error(
            "no_udemy_courses_detected",
            "Hermes connected to Udemy but could not read Udemy My Learning page content.",
            remote=remote,
            cdp_url=cdp_url,
            state_path=state_path,
        )
    if _is_udemy_login_page("", html):
        return _udemy_sync_error(
            "udemy_not_logged_in",
            "Udemy is showing a login page. Log into Udemy in your Chrome/Edge session, then rerun `hermes learning browser-sync udemy --remote`.",
            remote=remote,
            cdp_url=cdp_url,
            state_path=state_path,
        )
    if not _split_udemy_course_cards(html) and not _extract_udemy_heading_candidates(html):
        return _udemy_sync_error(
            "no_udemy_courses_detected",
            "Hermes connected to Udemy but could not extract course cards on My Learning. Run with --debug-dom for safe DOM clues.",
            remote=remote,
            cdp_url=cdp_url,
            state_path=state_path,
            diagnostics=_udemy_no_courses_diagnostics(html),
        )
    report = import_udemy_browser_html(html, learning_path=learning_path, career_path=career_path, now=timestamp, evidence_url=evidence_url)
    report.update({"success": True, "remote": remote, "cdp_url": _safe_cdp_url_for_output(cdp_url) if remote else None, "session_state_path": None if remote else str(state_path), "password_stored": False, "screenshots_saved": False})
    return report


def udemy_browser_status(*, learning_path: Path | None = None, state_path: Path | None = None, remote: bool = False, cdp_url: str = DEFAULT_UDEMY_CDP_URL) -> dict[str, Any]:
    learning_path = learning_path or learning_registry_path()
    state_path = state_path or udemy_session_state_path()
    registry = load_json(learning_path, empty_learning_registry())
    sources = registry.get("sources") if isinstance(registry.get("sources"), dict) else {}
    udemy = sources.get(UDEMY_SOURCE) if isinstance(sources.get(UDEMY_SOURCE), dict) else {}
    courses = [course for course in registry.get("courses", []) if isinstance(course, dict) and course.get("source") == UDEMY_SOURCE]
    manual_review = [item for item in registry.get("manual_review", []) if isinstance(item, dict) and item.get("source") == UDEMY_SOURCE]
    return {
        "provider": "udemy",
        "remote": remote,
        "cdp_url": _safe_cdp_url_for_output(cdp_url) if remote else None,
        "session_exists": False if remote else state_path.exists(),
        "session_state_path": None if remote else str(state_path),
        "session_file_mode": None if remote else oct(state_path.stat().st_mode & 0o777) if state_path.exists() else None,
        "last_sync": udemy.get("last_sync") or udemy.get("last_updated"),
        "courses_imported": len(courses),
        "errors": udemy.get("errors", []),
        "manual_review_count": len(manual_review),
        "learning_registry_path": str(learning_path),
        "password_stored": False,
        "screenshots_saved": False,
    }

def update_career_registry_with_learning_summary(learning_registry: dict[str, Any], career_path: Path | None = None, *, now: str | None = None) -> dict[str, Any]:
    timestamp = now or utc_now()
    career_path = career_path or career_registry_path()
    career = load_json(career_path, {})
    active_certification = career.get("current_priority") or career.get("current_certification_priority")
    summary = project_learning_summary(learning_registry, now=timestamp, active_certification=active_certification)
    career["learning_summary"] = summary
    career["learning_source"] = {
        "registry_path": str(learning_registry_path()),
        "source": "learning_registry_projection",
        "confidence": summary.get("confidence", 0.0),
        "last_updated": timestamp,
        "evidence_path": summary.get("evidence_path"),
    }
    if summary.get("primary_certification") and not (career.get("current_certification_priority") or career.get("current_priority")):
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
