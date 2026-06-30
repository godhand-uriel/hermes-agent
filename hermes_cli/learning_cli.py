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

    if action == "browser-connect" and getattr(args, "browser_provider", None) == "udemy":
        from hermes_cli.learning_registry import connect_udemy_browser_session

        _print_json(connect_udemy_browser_session(headless=False, remote=getattr(args, "remote", False), cdp_url=getattr(args, "cdp_url", "http://127.0.0.1:9222")))
        return 0

    if action == "browser-sync" and getattr(args, "browser_provider", None) == "udemy":
        from hermes_cli.learning_registry import sync_udemy_browser_learning

        result = sync_udemy_browser_learning(headless=not getattr(args, "headed", False), remote=getattr(args, "remote", False), cdp_url=getattr(args, "cdp_url", "http://127.0.0.1:9222"), debug_dom=getattr(args, "debug_dom", False))
        _print_json(result)
        return 0 if result.get("success") else 1

    if action == "browser-debug" and getattr(args, "browser_provider", None) == "udemy":
        from hermes_cli.learning_registry import debug_udemy_browser_dom

        result = debug_udemy_browser_dom(headless=not getattr(args, "headed", False), remote=getattr(args, "remote", False), cdp_url=getattr(args, "cdp_url", "http://127.0.0.1:9222"))
        _print_json(result)
        return 0 if result.get("success") else 1

    if action == "browser-status" and getattr(args, "browser_provider", None) == "udemy":
        from hermes_cli.learning_registry import udemy_browser_status

        _print_json(udemy_browser_status(remote=getattr(args, "remote", False), cdp_url=getattr(args, "cdp_url", "http://127.0.0.1:9222")))
        return 0

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

    browser_connect = learning_sub.add_parser("browser-connect", help="Open a provider browser login flow and save only cookie/session state")
    browser_connect.add_argument("browser_provider", choices=["udemy"], help="Browser learning provider")
    browser_connect.add_argument("--remote", action="store_true", help="Connect to an existing Chrome/Edge instance through Playwright CDP instead of launching a local browser")
    browser_connect.add_argument("--cdp-url", default="http://127.0.0.1:9222", help="Chrome DevTools Protocol endpoint for --remote mode (default: http://127.0.0.1:9222)")

    browser_sync = learning_sub.add_parser("browser-sync", help="Read provider course progress from an authenticated browser session into the Learning Registry")
    browser_sync.add_argument("browser_provider", choices=["udemy"], help="Browser learning provider")
    browser_sync.add_argument("--headed", action="store_true", help="Run browser visibly instead of headless for troubleshooting")
    browser_sync.add_argument("--remote", action="store_true", help="Connect to an existing Chrome/Edge instance through Playwright CDP instead of launching a local browser")
    browser_sync.add_argument("--cdp-url", default="http://127.0.0.1:9222", help="Chrome DevTools Protocol endpoint for --remote mode (default: http://127.0.0.1:9222)")
    browser_sync.add_argument("--debug-dom", action="store_true", help="Print redacted, safe DOM clues for Udemy selector troubleshooting without cookies, storage, screenshots, or account details")

    browser_debug = learning_sub.add_parser("browser-debug", help="Print redacted safe DOM clues for provider browser connector troubleshooting")
    browser_debug.add_argument("browser_provider", choices=["udemy"], help="Browser learning provider")
    browser_debug.add_argument("--headed", action="store_true", help="Run browser visibly instead of headless for troubleshooting")
    browser_debug.add_argument("--remote", action="store_true", help="Connect to an existing Chrome/Edge instance through Playwright CDP instead of launching a local browser")
    browser_debug.add_argument("--cdp-url", default="http://127.0.0.1:9222", help="Chrome DevTools Protocol endpoint for --remote mode (default: http://127.0.0.1:9222)")

    browser_status = learning_sub.add_parser("browser-status", help="Show provider browser connector status")
    browser_status.add_argument("browser_provider", choices=["udemy"], help="Browser learning provider")
    browser_status.add_argument("--remote", action="store_true", help="Show status for remote CDP mode instead of local storage-state mode")
    browser_status.add_argument("--cdp-url", default="http://127.0.0.1:9222", help="Chrome DevTools Protocol endpoint for --remote mode (default: http://127.0.0.1:9222)")
    learning_parser.set_defaults(func=_handle_learning)
