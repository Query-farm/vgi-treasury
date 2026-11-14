"""Serve bounded original public Treasury captures; never synthesize source rows."""

import copy
import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlencode, urlsplit


class RecordedFiscalSource:
    """Replay verified captures on loopback with generated pagination envelopes."""

    def __init__(self):
        root = Path(__file__).parent / "fixtures"
        self.manifest = json.loads((root / "discovery-provenance.json").read_text())
        self.routes = {}
        for capture in self.manifest["captures"]:
            raw = (root / capture["file"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != capture["sha256"]:
                raise ValueError("Recorded Treasury response hash mismatch")
            body = json.loads(raw)
            if len(body["data"]) != capture["rows"]:
                raise ValueError("Recorded row count mismatch")
            route = self.routes.setdefault(
                "/" + capture["endpoint"],
                {"name": capture["name"], "data": [], "meta": body["meta"], "capture": capture},
            )
            route["data"].extend(body["data"])
        for route in self.routes.values():
            if len(route["data"]) != route["capture"]["total_rows"]:
                raise ValueError("Capture does not contain every advertised row")
        self.previous = {k: v for k, v in os.environ.items() if k.startswith("TREASURY_")}
        self.requests = []
        self.closed = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                try:
                    parsed = urlsplit(self.path)
                    query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                    if parsed.path not in owner.routes or set(query) - {
                        "filter",
                        "sort",
                        "format",
                        "page[number]",
                        "page[size]",
                    }:
                        raise ValueError("Unsupported recorded request")
                    route = owner.routes[parsed.path]
                    size, number = int(query["page[size]"]), int(query["page[number]"])
                    if query.get("format") != "json" or not 1 <= size <= 1000 or number < 1:
                        raise ValueError("Unsupported pagination")
                    rows = route["data"]
                    if "filter" not in query:
                        if set(query) != {"format", "page[number]", "page[size]"} or (number, size) != (1, 1):
                            raise ValueError("Only fields() may inspect the unfiltered metadata")
                        start, end, purpose = None, None, "fields"
                    else:
                        parts = query["filter"].split(",")
                        if (
                            len(parts) != 2
                            or not parts[0].startswith("record_date:gte:")
                            or not parts[1].startswith("record_date:lte:")
                        ):
                            raise ValueError("Both inclusive date bounds are required")
                        start, end = parts[0].split(":", 2)[2], parts[1].split(":", 2)[2]
                        capture = route["capture"]
                        if not capture["coverage_start"] <= start <= end <= capture["coverage_end"]:
                            raise ValueError("Date bounds exceed the capture")
                        if query.get("sort") != "record_date,src_line_nbr":
                            raise ValueError("Stable source-line sort required")
                        rows = [r for r in rows if start <= r["record_date"] <= end]
                        purpose = "records"
                    rows = sorted(rows, key=lambda r: (r["record_date"], int(r["src_line_nbr"])))
                    selected = rows[(number - 1) * size : number * size]
                    meta = copy.deepcopy(route["meta"])
                    meta.update(
                        count=len(selected), **{"total-count": len(rows), "total-pages": (len(rows) + size - 1) // size}
                    )
                    body = {
                        "data": selected,
                        "meta": meta,
                        "links": {
                            "self": "?" + urlencode({"page[number]": number, "page[size]": size}),
                            "next": None if number * size >= len(rows) else "?page[number]=" + str(number + 1),
                        },
                    }
                    owner.requests.append(
                        {
                            "dataset": route["name"],
                            "purpose": purpose,
                            "page": number,
                            "page_size": size,
                            "rows": len(selected),
                            "total": len(rows),
                            "start": start,
                            "end": end,
                        }
                    )
                    status = 200
                except (KeyError, ValueError):
                    status, body = 400, {"error": "Request is outside the recorded data contract"}
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        for key in self.previous:
            os.environ.pop(key, None)
        os.environ.update(
            TREASURY_API_BASE_URL=f"http://127.0.0.1:{self.server.server_port}",
            TREASURY_ALLOW_INSECURE_HTTP="1",
            TREASURY_MIN_INTERVAL_SECONDS="0",
            TREASURY_MAX_ATTEMPTS="1",
            TREASURY_TIMEOUT_SECONDS="10",
        )

    def audit(self, scans):
        """Check each materialized scan's complete page sequence, including duplicate typed/raw reads."""
        expected = []
        for name, start, end, size, purpose in scans:
            route = next(r for r in self.routes.values() if r["name"] == name)
            rows = (
                route["data"] if purpose == "fields" else [r for r in route["data"] if start <= r["record_date"] <= end]
            )
            pages = 1 if purpose == "fields" else max(1, (len(rows) + size - 1) // size)
            for number in range(1, pages + 1):
                expected.append(
                    {
                        "dataset": name,
                        "purpose": purpose,
                        "page": number,
                        "page_size": size,
                        "rows": min(size, max(0, len(rows) - (number - 1) * size)),
                        "total": len(rows),
                        "start": start,
                        "end": end,
                    }
                )
        assert sorted(map(json.dumps, self.requests)) == sorted(map(json.dumps, expected)), (
            "Unexpected HTTP scan or page"
        )
        return len(self.requests)

    def close(self):
        """Restore source configuration and stop the loopback server once."""
        if self.closed:
            return
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        for key in list(os.environ):
            if key.startswith("TREASURY_"):
                os.environ.pop(key, None)
        os.environ.update(self.previous)
        self.closed = True
