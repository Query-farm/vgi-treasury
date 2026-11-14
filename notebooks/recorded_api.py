"""Explicit recorded-public or live source configuration for the unchanged worker."""

import copy
import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlencode, urlsplit

OFFICIAL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
ROUTE = "/v2/accounting/od/debt_to_penny"


class TreasurySource:
    """Own a bounded recorded-response server or select the official public API."""

    def __init__(self, mode):
        self.mode = mode
        self.manifest = json.loads(Path("fixtures/provenance.json").read_text())
        raw = Path("fixtures/debt-january-2024.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != self.manifest["sha256"]:
            raise ValueError("Recorded response hash mismatch")
        self.recorded = json.loads(raw)
        if len(self.recorded["data"]) != self.manifest["rows"]:
            raise ValueError("Recorded row count mismatch")
        self.requests = []
        self.server = None
        self.previous = {k: v for k, v in os.environ.items() if k.startswith("TREASURY_")}
        for key in self.previous:
            os.environ.pop(key, None)
        os.environ.update(TREASURY_TIMEOUT_SECONDS="15", TREASURY_MAX_ATTEMPTS="2", TREASURY_RETRY_BUDGET_SECONDS="30")
        if mode == "live":
            os.environ["TREASURY_API_BASE_URL"] = OFFICIAL
            return
        if mode != "recorded":
            raise ValueError("DATA_MODE must be recorded or live")
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                try:
                    parsed = urlsplit(self.path)
                    query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                    if parsed.path != ROUTE or set(query) - {"filter", "sort", "format", "page[number]", "page[size]"}:
                        raise ValueError("Unsupported recorded request")
                    if query.get("sort") != "record_date,src_line_nbr" or query.get("format") != "json":
                        raise ValueError("Use the notebook's stable sort and JSON format")
                    parts = query.get("filter", "").split(",")
                    if (
                        len(parts) != 2
                        or not parts[0].startswith("record_date:gte:")
                        or not parts[1].startswith("record_date:lte:")
                    ):
                        raise ValueError("Recorded requests require both inclusive date bounds")
                    start, end = parts[0].split(":", 2)[2], parts[1].split(":", 2)[2]
                    if not owner.manifest["coverage_start"] <= start <= end <= owner.manifest["coverage_end"]:
                        raise ValueError("Requested dates exceed recorded coverage")
                    size, number = int(query["page[size]"]), int(query["page[number]"])
                    if not 1 <= size <= 1000 or number < 1:
                        raise ValueError("Invalid page")
                    rows = [r for r in owner.recorded["data"] if start <= r["record_date"] <= end]
                    rows.sort(key=lambda r: (r["record_date"], int(r["src_line_nbr"])))
                    selected = rows[(number - 1) * size : number * size]
                    meta = copy.deepcopy(owner.recorded["meta"])
                    meta.update(
                        count=len(selected), **{"total-count": len(rows), "total-pages": (len(rows) + size - 1) // size}
                    )
                    links = {
                        "self": "?" + urlencode({"page[number]": number, "page[size]": size}),
                        "next": None if number * size >= len(rows) else "?page[number]=" + str(number + 1),
                    }
                    result = {"data": selected, "meta": meta, "links": links}
                    status = 200
                    owner.requests.append(
                        {
                            "page": number,
                            "page_size": size,
                            "rows": len(selected),
                            "total": len(rows),
                            "start": start,
                            "end": end,
                        }
                    )
                except (ValueError, KeyError):
                    result = {"error": "Request is outside this recording's supported date/sort contract"}
                    status = 400
                body = json.dumps(result).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        os.environ.update(
            TREASURY_API_BASE_URL=f"http://127.0.0.1:{self.server.server_port}",
            TREASURY_ALLOW_INSECURE_HTTP="1",
            TREASURY_MIN_INTERVAL_SECONDS="0",
        )

    def close(self):
        """Stop replay and restore inherited Treasury-specific configuration."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=5)
        for key in list(os.environ):
            if key.startswith("TREASURY_"):
                os.environ.pop(key, None)
        os.environ.update(self.previous)
