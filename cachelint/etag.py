"""Parsing and validation for the HTTP ETag header (RFC 9110 8.8.3).

entity-tag = [ weak ] opaque-tag
weak       = %s"W/"
opaque-tag = DQUOTE *etagc DQUOTE
etagc      = %x21 / %x23-7E / obs-text

Unlike a quoted-string, an entity-tag has no escaping mechanism, so a
backslash inside the quotes is just a plain character, not an escape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .parser import Issue

_WEAK_PREFIX = "W/"


def _is_etagc(ch: str) -> bool:
    code = ord(ch)
    return code == 0x21 or 0x23 <= code <= 0x7E or code >= 0x80


@dataclass
class ETagResult:
    raw: str
    weak: bool
    opaque_tag: Optional[str]
    issues: List[Issue] = field(default_factory=list)

    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    def warnings(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "warning"]


def parse_etag(value: str) -> ETagResult:
    raw = value.strip()
    issues: List[Issue] = []

    text = raw
    weak = False
    if text.startswith(_WEAK_PREFIX):
        weak = True
        text = text[len(_WEAK_PREFIX):]

    if len(text) < 2 or text[0] != '"' or text[-1] != '"':
        issues.append(Issue("error", f"{raw!r} is not a valid entity-tag: missing surrounding quotes"))
        return ETagResult(raw, weak, None, issues)

    inner = text[1:-1]
    for ch in inner:
        if not _is_etagc(ch):
            issues.append(
                Issue("error", f"entity-tag contains disallowed character {ch!r} (0x{ord(ch):02X})")
            )
            break

    return ETagResult(raw, weak, inner, issues)


def format_etag(result: ETagResult) -> str:
    lines = [f"ETag: {result.raw!r}"]
    lines.append(f"  weak: {result.weak}")
    if result.opaque_tag is not None:
        lines.append(f"  opaque-tag: {result.opaque_tag!r}")
    for i in result.issues:
        lines.append(f"  {i.severity}: {i.message}")
    return "\n".join(lines)


def etag_to_dict(result: ETagResult) -> dict:
    return {
        "raw": result.raw,
        "weak": result.weak,
        "opaque_tag": result.opaque_tag,
        "valid": not result.errors(),
        "issues": [{"severity": i.severity, "message": i.message} for i in result.issues],
    }
