"""Parsing and validation for the HTTP Cache-Control header (RFC 9111).

The header looks simple (a comma-separated list of tokens) but the details
that trip people up are: which directives take a delta-seconds argument vs.
an optional one, which ones are only meaningful on a request or a response,
and that no-cache/private carry an optional quoted list of field names on
responses but never on requests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

_TOKEN_RE = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")

# name -> (argument kind, contexts where the directive has defined meaning)
# argument kind is one of:
#   "none"             - no argument allowed
#   "delta-seconds"    - argument required, must be a non-negative integer
#   "opt-delta-seconds" - argument optional, must be a non-negative integer if present
#   "opt-field-names"  - argument optional, must be a quoted comma list if present
_KNOWN_DIRECTIVES = {
    "max-age": ("delta-seconds", {"request", "response"}),
    "max-stale": ("opt-delta-seconds", {"request"}),
    "min-fresh": ("delta-seconds", {"request"}),
    "no-cache": ("opt-field-names", {"request", "response"}),
    "no-store": ("none", {"request", "response"}),
    "no-transform": ("none", {"request", "response"}),
    "only-if-cached": ("none", {"request"}),
    "must-revalidate": ("none", {"response"}),
    "must-understand": ("none", {"response"}),
    "private": ("opt-field-names", {"response"}),
    "proxy-revalidate": ("none", {"response"}),
    "public": ("none", {"response"}),
    "s-maxage": ("delta-seconds", {"response"}),
    "stale-while-revalidate": ("delta-seconds", {"response"}),
    "stale-if-error": ("delta-seconds", {"response"}),
    "immutable": ("none", {"response"}),
}


@dataclass
class Directive:
    name: str
    raw_name: str
    argument: Optional[str] = None
    field_names: Optional[List[str]] = None


@dataclass
class Issue:
    severity: str  # "error" or "warning"
    message: str


@dataclass
class ParseResult:
    directives: List[Directive]
    issues: List[Issue]
    context: str

    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    def warnings(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "warning"]


def parse_cache_control(value: str, context: str = "response") -> ParseResult:
    if context not in ("request", "response"):
        raise ValueError("context must be 'request' or 'response'")

    issues: List[Issue] = []
    directives: List[Directive] = []
    seen = set()

    for part in _split_directives(value):
        raw_name, raw_arg = _split_name_value(part)
        if not raw_name:
            issues.append(Issue("error", f"empty directive near {part!r}"))
            continue
        if not _TOKEN_RE.fullmatch(raw_name):
            issues.append(Issue("error", f"{raw_name!r} is not a valid token"))
            continue

        name = raw_name.lower()
        if name in seen:
            issues.append(Issue("warning", f"directive {name!r} repeated"))
        seen.add(name)

        spec = _KNOWN_DIRECTIVES.get(name)
        if spec is None:
            issues.append(Issue("warning", f"unknown directive {name!r}"))
            argument = _unquote(raw_arg) if raw_arg is not None else None
            directives.append(Directive(name, raw_name, argument, None))
            continue

        kind, contexts = spec
        if context not in contexts:
            issues.append(
                Issue("warning", f"{name!r} has no defined meaning in a {context} header")
            )

        # no-cache carries field-names only on responses; on a request it is
        # a plain flag, same as no-store.
        effective_kind = "none" if name == "no-cache" and context == "request" else kind

        argument = None
        field_names = None

        if effective_kind == "none":
            if raw_arg is not None:
                issues.append(Issue("error", f"{name!r} does not take an argument"))
        elif effective_kind == "delta-seconds":
            if raw_arg is None:
                issues.append(Issue("error", f"{name!r} requires a delta-seconds argument"))
            else:
                argument = _check_delta_seconds(raw_arg, name, issues)
        elif effective_kind == "opt-delta-seconds":
            if raw_arg is not None:
                argument = _check_delta_seconds(raw_arg, name, issues)
        elif effective_kind == "opt-field-names":
            if raw_arg is not None:
                field_names = _parse_field_names(raw_arg, name, issues)

        directives.append(Directive(name, raw_name, argument, field_names))

    return ParseResult(directives, issues, context)


def format_result(result: ParseResult) -> str:
    lines = [f"Cache-Control ({result.context}):"]
    if not result.directives:
        lines.append("  (no directives)")
    for d in result.directives:
        piece = f"  {d.name}"
        if d.argument is not None:
            piece += f" = {d.argument}"
        if d.field_names is not None:
            shown = ", ".join(d.field_names) if d.field_names else "(none)"
            piece += f" -> fields: {shown}"
        lines.append(piece)

    if result.errors():
        lines.append("errors:")
        for i in result.errors():
            lines.append(f"  - {i.message}")
    if result.warnings():
        lines.append("warnings:")
        for i in result.warnings():
            lines.append(f"  - {i.message}")
    if not result.issues:
        lines.append("valid, no issues found")
    return "\n".join(lines)


def to_dict(result: ParseResult) -> dict:
    return {
        "context": result.context,
        "valid": not result.errors(),
        "directives": [
            {"name": d.name, "argument": d.argument, "field_names": d.field_names}
            for d in result.directives
        ],
        "issues": [{"severity": i.severity, "message": i.message} for i in result.issues],
    }


def _split_directives(value: str) -> List[str]:
    parts = []
    current: List[str] = []
    in_quotes = False
    for ch in value:
        if ch == '"':
            in_quotes = not in_quotes
            current.append(ch)
        elif ch == "," and not in_quotes:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def _split_name_value(part: str):
    in_quotes = False
    for i, ch in enumerate(part):
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == "=" and not in_quotes:
            return part[:i].strip(), part[i + 1 :].strip()
    return part.strip(), None


def _unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1]
    return text


def _check_delta_seconds(raw_arg: str, name: str, issues: List[Issue]) -> str:
    text = _unquote(raw_arg)
    if not text.isdigit():
        issues.append(
            Issue("error", f"{name!r} argument {raw_arg!r} is not a non-negative integer")
        )
    return text


def _parse_field_names(raw_arg: str, name: str, issues: List[Issue]) -> List[str]:
    text = raw_arg.strip()
    if not (len(text) >= 2 and text[0] == '"' and text[-1] == '"'):
        issues.append(Issue("error", f"{name!r} field-names argument must be a quoted string"))
        return []
    inner = text[1:-1]
    return [f.strip() for f in inner.split(",") if f.strip()]
