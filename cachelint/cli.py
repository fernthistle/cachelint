"""Command-line entry point for cachelint."""

from __future__ import annotations

import argparse
import json
import sys

from .parser import format_result, parse_cache_control, to_dict


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cachelint",
        description="Parse and validate an HTTP Cache-Control header value.",
    )
    p.add_argument(
        "value",
        nargs="?",
        help="header value to parse; reads from stdin if omitted",
    )
    p.add_argument(
        "--context",
        choices=("request", "response"),
        default="response",
        help="which side of the exchange the header came from (default: response)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON instead of the human-readable report",
    )
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    value = args.value if args.value is not None else sys.stdin.read()
    value = value.strip()
    if not value:
        print("no header value given", file=sys.stderr)
        return 2

    result = parse_cache_control(value, context=args.context)

    if args.json:
        print(json.dumps(to_dict(result), indent=2))
    else:
        print(format_result(result))

    return 1 if result.errors() else 0


if __name__ == "__main__":
    raise SystemExit(main())
