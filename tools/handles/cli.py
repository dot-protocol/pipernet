"""
cli — Command-line interface for the handle substrate.

Subcommands:
  claim       — Claim a handle
  resolve     — Resolve a handle to its pubkey
  add-contact — Add a contact to your contact list
  remove-contact — Remove a contact
  list-contacts  — Show your contact list
  mentions    — Parse mentions from text

All commands sign and post to Oracle.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from handles import (
    claim_handle,
    resolve_handle,
    add_contact,
    remove_contact,
    list_contacts,
    parse_mentions,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def cmd_claim(args):
    """Claim a handle."""
    try:
        result = claim_handle(args.handle, note=args.note)
        print(f"✓ Claimed {result.handle}")
        print(f"  pubkey: {result.pubkey}")
        print(f"  claim_id: {result.claim_id}")
        print(f"  claimed_at: {result.claimed_at}")
    except Exception as e:
        print(f"✗ Failed to claim: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_resolve(args):
    """Resolve a handle to its pubkey."""
    try:
        result = resolve_handle(args.handle)
        if result:
            print(f"{result.pubkey}")
            if args.verbose:
                print(f"  handle: {result.handle}")
                print(f"  claim_id: {result.claim_id}")
                print(f"  claimed_at: {result.claimed_at}")
                print(f"  claimer: {result.claimer}")
        else:
            print(f"✗ {args.handle} is unclaimed or invalid", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"✗ Failed to resolve: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_add_contact(args):
    """Add a contact."""
    try:
        tags = args.tags.split(",") if args.tags else []
        obs_id = add_contact(args.contact, alias=args.alias, tags=tags)
        print(f"✓ Added contact {args.contact}")
        if args.alias:
            print(f"  alias: {args.alias}")
        if tags:
            print(f"  tags: {', '.join(tags)}")
        print(f"  obs_id: {obs_id}")
    except Exception as e:
        print(f"✗ Failed to add contact: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_remove_contact(args):
    """Remove a contact."""
    try:
        obs_id = remove_contact(args.contact, reason=args.reason)
        print(f"✓ Removed contact {args.contact}")
        print(f"  obs_id: {obs_id}")
    except Exception as e:
        print(f"✗ Failed to remove contact: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_list_contacts(args):
    """List contacts."""
    try:
        handle = args.handle or None
        contacts = list_contacts(handle)
        if not contacts:
            print("No contacts.")
            return
        for contact in contacts:
            alias_str = f" ({contact.alias})" if contact.alias else ""
            print(f"  {contact.contact}{alias_str}")
            if contact.tags:
                print(f"    tags: {', '.join(contact.tags)}")
            if contact.added_at:
                print(f"    added: {contact.added_at}")
    except Exception as e:
        print(f"✗ Failed to list contacts: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_mentions(args):
    """Parse mentions from text."""
    text = args.text
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read()
    if not text:
        print("✗ No text provided", file=sys.stderr)
        sys.exit(1)
    mentions = parse_mentions(text)
    if mentions:
        for mention in mentions:
            print(f"  @{mention}")
    else:
        print("No mentions found.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Pipernet handle substrate CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s claim --handle shannon --note "primary session"
  %(prog)s resolve --handle jared
  %(prog)s add-contact --contact jared --alias "Jared (iPhone)"
  %(prog)s list-contacts
  %(prog)s mentions "hey @shannon and @jared"
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # claim
    claim_parser = subparsers.add_parser("claim", help="Claim a handle")
    claim_parser.add_argument("--handle", required=True, help="Handle to claim")
    claim_parser.add_argument("--note", help="Optional public note")
    claim_parser.set_defaults(func=cmd_claim)

    # resolve
    resolve_parser = subparsers.add_parser("resolve", help="Resolve a handle")
    resolve_parser.add_argument("--handle", required=True, help="Handle to resolve")
    resolve_parser.add_argument("--verbose", "-v", action="store_true", help="Show full details")
    resolve_parser.set_defaults(func=cmd_resolve)

    # add-contact
    add_contact_parser = subparsers.add_parser("add-contact", help="Add a contact")
    add_contact_parser.add_argument("--contact", required=True, help="Contact handle")
    add_contact_parser.add_argument("--alias", help="Display alias")
    add_contact_parser.add_argument("--tags", help="Comma-separated tags")
    add_contact_parser.set_defaults(func=cmd_add_contact)

    # remove-contact
    remove_contact_parser = subparsers.add_parser("remove-contact", help="Remove a contact")
    remove_contact_parser.add_argument("--contact", required=True, help="Contact handle")
    remove_contact_parser.add_argument("--reason", help="Reason for removal")
    remove_contact_parser.set_defaults(func=cmd_remove_contact)

    # list-contacts
    list_contacts_parser = subparsers.add_parser("list-contacts", help="List contacts")
    list_contacts_parser.add_argument("--handle", help="Handle to list (default: current)")
    list_contacts_parser.set_defaults(func=cmd_list_contacts)

    # mentions
    mentions_parser = subparsers.add_parser("mentions", help="Parse mentions")
    mentions_parser.add_argument("text", nargs="?", help="Text to parse (reads stdin if omitted)")
    mentions_parser.set_defaults(func=cmd_mentions)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
