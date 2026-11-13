"""Treasury Fiscal Data request validation and pagination integrity."""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any
from urllib.parse import parse_qs, urlsplit

from vgi.catalog import SecretTypeSpec

from .transport import ApiError, Config, request_json

# The official API is public. HTTP worker authentication is configured separately.
API_SECRET_TYPES: list[SecretTypeSpec] = []
FIELD_PATTERN = r"[a-z][a-z0-9_]{0,63}"
ENDPOINT_PATTERN = r"^v[12]/(?:[a-z][a-z0-9_]*/){1,4}[a-z][a-z0-9_]*$"


def endpoint(value: str) -> str:
    """Restrict SQL endpoint arguments to relative Fiscal Data routes."""
    if re.fullmatch(ENDPOINT_PATTERN, value) is None:
        raise ApiError(
            "endpoint must be a relative Fiscal Data v1/v2 path, without URLs, traversal or query parameters"
        )
    return value


def iso_date(value: str, name: str) -> date:
    """Validate a strict calendar date without echoing malformed input."""
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed
    except (TypeError, ValueError):
        raise ApiError(f"{name} must be a valid YYYY-MM-DD date") from None


def sort_fields(value: str) -> str:
    """Validate a bounded list of source sort fields and directions."""
    fields = value.split(",")
    if not 1 <= len(fields) <= 20 or any(re.fullmatch("-?" + FIELD_PATTERN, f) is None for f in fields):
        raise ApiError(
            "sort_fields must contain comma-separated field names, optionally prefixed by '-' for descending"
        )
    if len({f.removeprefix("-") for f in fields}) != len(fields):
        raise ApiError("sort_fields must not repeat a field")
    return value


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate JSON object keys."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _filter_value(value: Any, *, in_list: bool = False) -> str:
    """Encode a scalar without allowing injection into Fiscal Data filter syntax."""
    if type(value) not in (str, int):
        raise ValueError
    text = str(value)
    forbidden = ",:" + ("()" if in_list else "")
    if not text or len(text) > 1000 or any(c in text for c in forbidden) or any(ord(c) < 32 for c in text):
        raise ValueError
    return text


def filters_json(value: str) -> list[str]:
    """Build upstream filters from explicit field/operator/value objects."""
    try:
        if len(value) > 20000:
            raise ValueError
        parsed = json.loads(value, object_pairs_hook=_unique)
        if not isinstance(parsed, list) or len(parsed) > 50:
            raise ValueError
        filters = []
        for item in parsed:
            if not isinstance(item, dict) or set(item) != {"field", "op", "value"}:
                raise ValueError
            field, op, raw = item["field"], item["op"], item["value"]
            if not isinstance(field, str) or re.fullmatch(FIELD_PATTERN, field) is None:
                raise ValueError
            if not isinstance(op, str) or op not in {"eq", "lt", "lte", "gt", "gte", "in"}:
                raise ValueError
            if op == "in":
                if not isinstance(raw, list) or not 1 <= len(raw) <= 100:
                    raise ValueError
                encoded = "(" + ",".join(_filter_value(v, in_list=True) for v in raw) + ")"
            else:
                encoded = _filter_value(raw)
            filters.append(f"{field}:{op}:{encoded}")
        return filters
    except (ValueError, TypeError, RecursionError):
        raise ApiError(
            "filters_json must be an array of field/op/value objects; operators: eq, lt, lte, gt, gte, in. "
            "Values must be strings or integers without comma/colon delimiters; in requires a nonempty array"
        ) from None


def integer(value: Any, name: str) -> int:
    """Require a nonnegative JSON integer, accepting documented numeric text."""
    if type(value) is int and value >= 0:
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,15}", value):
        return int(value)
    raise ApiError(f"Treasury response has invalid {name}")


def page(route: str, query: dict[str, str], number: int, size: int) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
    """Fetch one page and validate metadata without following server-provided links."""
    params = {**query, "format": "json", "page[number]": str(number), "page[size]": str(size)}
    body = request_json(endpoint(route), list(params.items()), Config.from_env())
    rows, meta, links = body.get("data"), body.get("meta"), body.get("links")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ApiError("Treasury response has invalid data records")
    if not isinstance(meta, dict) or not isinstance(links, dict):
        raise ApiError("Treasury response is missing pagination metadata")
    total = integer(meta.get("total-count"), "total-count")
    count = integer(meta.get("count"), "count")
    pages = integer(meta.get("total-pages"), "total-pages")
    offset = (number - 1) * size
    if count != len(rows) or count > size or (rows and offset + count > total):
        raise ApiError("Treasury returned inconsistent pagination counts")
    if (total and pages != (total + size - 1) // size) or (not total and pages not in {0, 1}):
        raise ApiError("Treasury returned inconsistent total-pages")
    if len(rows) != min(size, max(0, total - offset)):
        raise ApiError("Treasury returned a short or empty page before the advertised result count")
    current = links.get("self")
    if not isinstance(current, str):
        raise ApiError("Treasury response is missing the current page link")
    current_query = urlsplit(current).query or current.lstrip("?&")
    current_params = parse_qs(current_query)
    if current_params.get("page[number]") != [str(number)] or current_params.get("page[size]") != [str(size)]:
        raise ApiError("Treasury returned a different page than requested")
    return rows, meta, total
