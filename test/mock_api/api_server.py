"""Synthetic Fiscal Data pages using field metadata observed from the official API."""

from __future__ import annotations

import copy
import json
import re
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

API_KEY = "public-api-no-upstream-key"  # No upstream key is needed by Treasury.
FIXTURES = json.loads((Path(__file__).parent / "fixtures.json").read_text())


class ApiServer(ThreadingHTTPServer):
    """A local paginated API with explicit corruption and retry controls."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), Handler)
        self.requests: list[dict[str, Any]] = []
        self.mode = ""
        self.attempts = 0


def matches(row: dict[str, str], expression: str, types: dict[str, str]) -> bool:
    """Evaluate the documented subset of filters used by offline contracts."""
    for clause in re.split(r",(?![^()]*\))", expression):
        field, op, value = clause.split(":", 2)
        left: Any = row.get(field, "null")
        right: Any = value
        if op == "in":
            if left not in value.strip("()").split(","):
                return False
            continue
        if types.get(field) not in {"STRING", "DATE"} and left != "null" and value != "null":
            left, right = Decimal(left), Decimal(value)
        if not {
            "eq": left == right,
            "gte": left >= right,
            "gt": left > right,
            "lt": left < right,
            "lte": left <= right,
        }[op]:
            return False
    return True


class Handler(BaseHTTPRequestHandler):
    """Serve deterministic Fiscal Data envelopes without writing request logs."""

    server: ApiServer

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass

    def send_json(self, status: int, body: Any, headers: dict[str, str] | None = None) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        endpoint = url.path.lstrip("/")
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        self.server.requests.append({"endpoint": endpoint, "query": query})
        self.server.attempts += 1
        mode = self.server.mode
        if mode == "RETRY" and self.server.attempts == 1:
            self.send_json(429, {}, {"Retry-After": "0"})
            return
        if mode == "REDIRECT":
            self.send_json(302, {}, {"Location": "https://example.invalid/"})
            return
        if endpoint not in FIXTURES:
            self.send_json(404, {"error": "Unknown endpoint"})
            return
        fixture = copy.deepcopy(FIXTURES[endpoint])
        rows, meta = fixture["data"], fixture["meta"]
        types = meta["dataTypes"]
        if query.get("filter"):
            rows = [r for r in rows if matches(r, query["filter"], types)]
        for field in reversed(query.get("sort", "record_date,src_line_nbr").split(",")):
            name = field.removeprefix("-")
            rows.sort(
                key=lambda r: (
                    int(r[name])
                    if types.get(name) in {"INTEGER", "YEAR", "MONTH", "DAY", "QUARTER"}
                    else r.get(name, "")
                ),
                reverse=field.startswith("-"),
            )
        size, number = int(query.get("page[size]", 100)), int(query.get("page[number]", 1))
        total = len(rows)
        selected = rows[(number - 1) * size : number * size]
        if mode == "STALLED":
            selected = []
        if mode == "CHANGED" and number > 1:
            total += 1
        if mode == "REPEAT" and number > 1:
            selected = rows[:size]
        if mode == "BAD_CURRENCY" and selected:
            money = next(name for name, kind in types.items() if kind.startswith("CURRENCY"))
            selected[0][money] = "NaN"
        if mode == "DRIFT" and selected:
            selected[0].pop("src_line_nbr")
        meta.update(count=len(selected), **{"total-count": total, "total-pages": (total + size - 1) // size})
        self_page = number + 1 if mode == "WRONG_PAGE" else number
        links = {
            "self": "&" + urlencode({"page[number]": self_page, "page[size]": size}),
            "next": "&page[number]=" + str(number + 1) if number * size < total else None,
        }
        self.send_json(200, {"data": selected, "meta": meta, "links": links})


if __name__ == "__main__":
    server = ApiServer()
    print(f"PORT:{server.server_port}", flush=True)
    server.serve_forever()
