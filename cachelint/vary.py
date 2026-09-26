"""Parsing and validation for the HTTP Vary header.

Vary is a comma-separated list of field-names, or the single special value
"*" (RFC 9110 12.5.5, referenced by RFC 9111 4.1). "*" can't be mixed with
field-names - it isn't a wildcard alongside a list, it means the cache key
can't be expressed as a set of field-names at all, so any other entry in the
same header is redundant with it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .parser import _TOKEN_RE, Issue


@dataclass
class VaryResult:
    raw: str
    wildcard: bool
    field_names: List[str] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)

    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    def warnings(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "warning"]


def parse_vary(value: str) -> VaryResult:
    raw = value.strip()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    issues: List[Issue] = []

    if not parts:
        issues.append(Issue("error", "Vary has no field-names"))
        return VaryResult(raw, False, [], issues)

    if "*" in parts:
        if len(parts) > 1:
            issues.append(Issue("error", "'*' cannot be combined with other field-names"))
        return VaryResult(raw, True, [], issues)

    seen = set()
    field_names: List[str] = []
    for part in parts:
        if not _TOKEN_RE.fullmatch(part):
            issues.append(Issue("error", f"{part!r} is not a valid field-name"))
            continue
        lowered = part.lower()
        if lowered in seen:
            issues.append(Issue("warning", f"field-name {part!r} repeated"))
        seen.add(lowered)
        field_names.append(part)

    return VaryResult(raw, False, field_names, issues)


def format_vary(result: VaryResult) -> str:
    lines = [f"Vary: {result.raw!r}"]
    if result.wildcard:
        lines.append("  *: cache key can't be expressed as a set of field-names")
    else:
        lines.append(f"  field-names: {', '.join(result.field_names) or '(none)'}")
    for i in result.issues:
        lines.append(f"  {i.severity}: {i.message}")
    return "\n".join(lines)


def vary_to_dict(result: VaryResult) -> dict:
    return {
        "raw": result.raw,
        "wildcard": result.wildcard,
        "field_names": result.field_names,
        "valid": not result.errors(),
        "issues": [{"severity": i.severity, "message": i.message} for i in result.issues],
    }
