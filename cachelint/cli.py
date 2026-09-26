"""Command-line entry point for cachelint."""

from __future__ import annotations

import argparse
import json
import sys

from .dates import age_to_dict, expires_to_dict, format_age, format_expires, parse_age, parse_expires
from .etag import etag_to_dict, format_etag, parse_etag
from .parser import format_result, parse_cache_control, to_dict
from .vary import format_vary, parse_vary, vary_to_dict


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cachelint",
        description="Parse and validate an HTTP cache header value.",
    )
    p.add_argument(
        "value",
        nargs="?",
        help="header value to parse; reads from stdin if omitted",
    )
    p.add_argument(
        "--header",
        choices=("cache-control", "expires", "age", "vary", "etag"),
        default="cache-control",
        help="which header the value came from (default: cache-control)",
    )
    p.add_argument(
        "--context",
        choices=("request", "response"),
        default="response",
        help="which side of the exchange the header came from; only used "
        "for --header cache-control (default: response)",
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

    if args.header == "cache-control":
        result = parse_cache_control(value, context=args.context)
        print(json.dumps(to_dict(result), indent=2) if args.json else format_result(result))
    elif args.header == "expires":
        result = parse_expires(value)
        print(json.dumps(expires_to_dict(result), indent=2) if args.json else format_expires(result))
    elif args.header == "age":
        result = parse_age(value)
        print(json.dumps(age_to_dict(result), indent=2) if args.json else format_age(result))
    elif args.header == "vary":
        result = parse_vary(value)
        print(json.dumps(vary_to_dict(result), indent=2) if args.json else format_vary(result))
    else:
        result = parse_etag(value)
        print(json.dumps(etag_to_dict(result), indent=2) if args.json else format_etag(result))

    return 1 if result.errors() else 0


if __name__ == "__main__":
    raise SystemExit(main())
