"""CLI wiring for Hermes Finance Registry Plaid integration."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def _print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def _handle_finance(args: argparse.Namespace) -> int:
    action = getattr(args, "finance_action", None)
    if action == "plaid":
        plaid_action = getattr(args, "plaid_action", None)
        from hermes_cli.plaid_connector import PlaidConnector

        connector = PlaidConnector()
        if plaid_action == "link-token":
            _print_json(connector.create_link_token())
            return 0
        if plaid_action == "exchange-token":
            _print_json(connector.exchange_public_token(args.public_token, store=True))
            return 0
        print("Missing plaid subcommand", file=sys.stderr)
        return 2
    if action == "sync":
        if not getattr(args, "sandbox", False):
            print("Refusing sync without --sandbox. Production account sync is not enabled.", file=sys.stderr)
            return 2
        from hermes_cli.plaid_connector import PlaidConnector

        _print_json(PlaidConnector().sync_to_finance_registry())
        return 0
    if action == "sync-status":
        from hermes_cli.finance_registry import latest_finance_sync_status

        _print_json(latest_finance_sync_status())
        return 0
    if action == "disconnect":
        from hermes_cli.plaid_connector import PlaidConnector

        _print_json(PlaidConnector().disconnect())
        return 0
    print("Missing finance subcommand", file=sys.stderr)
    return 2


def register_cli(subparsers: argparse._SubParsersAction) -> None:
    finance_parser = subparsers.add_parser(
        "finance",
        help="Manage the local Finance Registry and read-only Plaid sandbox sync",
        description=(
            "Finance Registry commands. Plaid integration is read-only and sandbox-only; "
            "dashboard metrics are derived from the local registry, never Plaid directly."
        ),
    )
    finance_sub = finance_parser.add_subparsers(dest="finance_action")

    plaid_parser = finance_sub.add_parser("plaid", help="Plaid Sandbox setup commands")
    plaid_sub = plaid_parser.add_subparsers(dest="plaid_action")
    plaid_sub.add_parser("link-token", help="Create a Plaid Sandbox Link token")
    exchange = plaid_sub.add_parser("exchange-token", help="Exchange a Plaid Sandbox public token and store the encrypted access token")
    exchange.add_argument("public_token", help="Plaid Sandbox public token from Link")

    sync = finance_sub.add_parser("sync", help="Sync Plaid Sandbox data into the Finance Registry")
    sync.add_argument("--sandbox", action="store_true", help="Required safety flag; production sync is disabled")

    finance_sub.add_parser("sync-status", help="Show latest finance sync status")
    finance_sub.add_parser("disconnect", help="Remove Plaid item and local encrypted access token")
    finance_parser.set_defaults(func=_handle_finance)
