"""CLI wiring for Hermes Learning Registry."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def _print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def _handle_learning(args: argparse.Namespace) -> int:
    action = getattr(args, "learning_action", None)

    if action == "sync":
        from hermes_cli.learning_registry import sync_obsidian_learning_registry

        _print_json(sync_obsidian_learning_registry())
        return 0

    if action == "status":
        from hermes_cli.learning_registry import learning_registry_status

        _print_json(learning_registry_status())
        return 0

    if action == "audit":
        from hermes_cli.learning_registry import audit_learning_notes

        _print_json(audit_learning_notes())
        return 0

    if action == "import":
        from pathlib import Path

        from hermes_cli.learning_registry import import_learning_evidence

        try:
            _print_json(import_learning_evidence(Path(args.file), provider=args.provider))
            return 0
        except Exception as exc:  # noqa: BLE001 - CLI boundary reports structured failure.
            _print_json({"success": False, "error": str(exc), "provider": getattr(args, "provider", None), "evidence_path": getattr(args, "file", None)})
            return 1

    print("Missing learning subcommand", file=sys.stderr)
    return 2


def register_cli(subparsers: argparse._SubParsersAction) -> None:
    learning_parser = subparsers.add_parser(
        "learning",
        help="Sync, inspect, and audit the local Learning Registry",
        description=(
            "Learning Registry commands. Obsidian learning notes sync into "
            "dashboard/learning_registry.json, then an executive learning_summary "
            "projection updates the Career Registry. Audit is read-only."
        ),
    )
    learning_sub = learning_parser.add_subparsers(dest="learning_action")
    learning_sub.add_parser("sync", help="Sync Obsidian learning notes into the Learning Registry and Career Registry projection")
    learning_sub.add_parser("status", help="Show Learning Registry path, counts, providers, last sync, and sync health")
    learning_sub.add_parser("audit", help="Read-only audit of Obsidian learning notes and frontmatter quality")
    import_parser = learning_sub.add_parser("import", help="Import a Microsoft Learn or AWS Skill Builder evidence file into the Learning Registry")
    import_parser.add_argument("file", help="Evidence file: PDF, CSV, text export, screenshot/image, certificate, or transcript")
    import_parser.add_argument("--provider", required=True, choices=["microsoft_learn", "aws_skill_builder"], help="Evidence provider")
    learning_parser.set_defaults(func=_handle_learning)
