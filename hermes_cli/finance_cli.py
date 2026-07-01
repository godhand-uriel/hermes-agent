"""CLI wiring for Hermes Finance Registry Plaid integration."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


def _print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def _handle_finance(args: argparse.Namespace) -> int:
    action = getattr(args, "finance_action", None)
    if action == "plaid":
        plaid_action = getattr(args, "plaid_action", None)
        if plaid_action == "validate-production-config":
            from hermes_cli.plaid_connector import validate_production_config

            _print_json(validate_production_config())
            return 0
        from hermes_cli.plaid_connector import PlaidConnector

        connector = PlaidConnector()
        if plaid_action == "link-token":
            _print_json(connector.create_link_token())
            return 0
        if plaid_action == "exchange-token":
            _print_json(connector.exchange_public_token(args.public_token, store=True))
            return 0
        if plaid_action == "reconnect-token":
            _print_json(connector.create_link_token(user_id="hermes-finance-reconnect"))
            return 0
        print("Missing plaid subcommand", file=sys.stderr)
        return 2
    if action == "sync":
        from hermes_cli.plaid_connector import PlaidConnector

        if getattr(args, "sandbox", False):
            os.environ["PLAID_ENV"] = "sandbox"
        if getattr(args, "production", False) and os.environ.get("PLAID_ENV", "").strip().lower() != "production":
            print("Refusing production finance sync unless PLAID_ENV=production is already set.", file=sys.stderr)
            return 2
        _print_json(PlaidConnector().sync_to_finance_registry())
        return 0
    if action == "schedule":
        from hermes_cli.finance_registry import configure_finance_sync_schedule, finance_sync_schedule

        if getattr(args, "cadence", None):
            _print_json(configure_finance_sync_schedule(cadence=args.cadence, enabled=args.cadence != "manual"))
        else:
            _print_json(finance_sync_schedule())
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
        help="Manage the local Finance Registry and read-only Plaid sync",
        description=(
            "Finance Registry commands. Plaid integration is read-only; "
            "dashboard metrics are derived from the local registry, never Plaid directly. "
            "Select sandbox or production only through PLAID_ENV/configuration."
        ),
    )
    finance_sub = finance_parser.add_subparsers(dest="finance_action")

    plaid_parser = finance_sub.add_parser("plaid", help="Plaid Link setup commands")
    plaid_sub = plaid_parser.add_subparsers(dest="plaid_action")
    plaid_sub.add_parser("link-token", help="Create a Plaid Link token for the configured PLAID_ENV")
    plaid_sub.add_parser("validate-production-config", help="Validate production Plaid config without contacting Plaid or creating tokens")
    plaid_sub.add_parser("reconnect-token", help="Create a Plaid Link token for reconnect/update mode")
    exchange = plaid_sub.add_parser("exchange-token", help="Exchange a Plaid public token server-side and store the encrypted access token")
    exchange.add_argument("public_token", help="Plaid public token from Link")

    sync = finance_sub.add_parser("sync", help="Sync configured Plaid Items into the Finance Registry")
    sync_env = sync.add_mutually_exclusive_group()
    sync_env.add_argument("--sandbox", action="store_true", help="Force a sandbox sync without changing stored production credentials")
    sync_env.add_argument("--production", action="store_true", help="Allow production sync only when PLAID_ENV=production is already set")

    schedule = finance_sub.add_parser("schedule", help="Show or configure Finance Registry automatic sync cadence")
    schedule.add_argument("cadence", nargs="?", choices=["manual", "hourly", "every_6_hours", "every_12_hours", "daily"], help="Sync cadence; omit to show current schedule")

    finance_sub.add_parser("sync-status", help="Show latest finance sync status")
    finance_sub.add_parser("disconnect", help="Remove Plaid item and local encrypted access token")
    finance_parser.set_defaults(func=_handle_finance)
