"""Parsing and validation for the HTTP Expires and Age headers (RFC 9111).

Expires carries an HTTP-date; Age carries a delta-seconds integer. Both end
up feeding into freshness calculations alongside Cache-Control, but that
combination is for the later report-merging step - this module only handles
each header on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional

from .parser import Issue

# RFC 9111 1.2.2: delta-seconds is a non-negative integer, and a sender that
# has to represent a value larger than 2**31 - 1 seconds is expected to clamp
# it to that limit instead of overflowing.
_DELTA_SECONDS_MAX = 2147483648


@dataclass
class ExpiresResult:
    raw: str
    when: Optional[datetime]
    expired: bool
    issues: List[Issue]

    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    def warnings(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "warning"]


@dataclass
class AgeResult:
    raw: str
    seconds: Optional[int]
    issues: List[Issue]

    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    def warnings(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "warning"]


def parse_expires(value: str, now: Optional[datetime] = None) -> ExpiresResult:
    raw = value.strip()
    now = now or datetime.now(timezone.utc)

    when = _parse_http_date(raw)
    if when is None:
        issues = [
            Issue(
                "warning",
                f"{raw!r} is not a valid HTTP-date; treating as already expired "
                "per RFC 9111 5.3",
            )
        ]
        return ExpiresResult(raw, None, True, issues)

    return ExpiresResult(raw, when, when <= now, [])


def parse_age(value: str) -> AgeResult:
    raw = value.strip()

    if not raw.isdigit():
        return AgeResult(raw, None, [Issue("error", f"{raw!r} is not a non-negative integer")])

    seconds = int(raw)
    if seconds <= _DELTA_SECONDS_MAX:
        return AgeResult(raw, seconds, [])

    issues = [
        Issue(
            "warning",
            f"{seconds} overflows the delta-seconds range; a sender should have "
            f"clamped this to {_DELTA_SECONDS_MAX}",
        )
    ]
    return AgeResult(raw, _DELTA_SECONDS_MAX, issues)


def format_expires(result: ExpiresResult) -> str:
    lines = [f"Expires: {result.raw!r}"]
    if result.when is not None:
        lines.append(f"  parsed: {result.when.isoformat()}")
    lines.append(f"  expired: {result.expired}")
    for i in result.issues:
        lines.append(f"  {i.severity}: {i.message}")
    return "\n".join(lines)


def format_age(result: AgeResult) -> str:
    lines = [f"Age: {result.raw!r}"]
    if result.seconds is not None:
        lines.append(f"  seconds: {result.seconds}")
    for i in result.issues:
        lines.append(f"  {i.severity}: {i.message}")
    return "\n".join(lines)


def expires_to_dict(result: ExpiresResult) -> dict:
    return {
        "raw": result.raw,
        "parsed": result.when.isoformat() if result.when else None,
        "expired": result.expired,
        "valid": not result.errors(),
        "issues": [{"severity": i.severity, "message": i.message} for i in result.issues],
    }


def age_to_dict(result: AgeResult) -> dict:
    return {
        "raw": result.raw,
        "seconds": result.seconds,
        "valid": not result.errors(),
        "issues": [{"severity": i.severity, "message": i.message} for i in result.issues],
    }


def _parse_http_date(raw: str) -> Optional[datetime]:
    # "0" is the classic legacy way of spelling "already expired"; RFC 9111
    # 5.3 calls it out by name alongside other invalid date formats.
    if not raw or raw == "0":
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        # HTTP-date is always GMT; parsedate_to_datetime returns a naive
        # datetime when the string carries no offset, which is exactly the
        # case for a well-formed IMF-fixdate.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
