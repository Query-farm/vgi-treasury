"""Fiscal Data precision, pagination and authentication through real worker processes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from vgi.arguments import Arguments
from vgi.client import Client
from vgi.invocation import BindResponse

from test.mock_api.api_server import ApiServer
from treasury_worker.api import endpoint, filters_json, sort_fields
from treasury_worker.auth import validate_http_auth
from treasury_worker.functions import State, convert
from treasury_worker.meta import column
from treasury_worker.transport import ApiError


@pytest.fixture()
def api(monkeypatch: pytest.MonkeyPatch) -> Iterator[ApiServer]:
    server = ApiServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("TREASURY_API_BASE_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("TREASURY_ALLOW_INSECURE_HTTP", "1")
    monkeypatch.setenv("TREASURY_MIN_INTERVAL_SECONDS", "0")
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture()
def treasury_client(api: ApiServer) -> Iterator[Client]:
    with Client([sys.executable, "-m", "treasury_worker.worker"], pool=None) as client:
        yield client


def table(client: Client, name: str, *positional: Any, **named: Any) -> pa.Table:
    bound: list[BindResponse] = []
    batches = list(
        client.table_function(
            function_name=name,
            schema_path=["main"],
            bind_result_callback=bound.append,
            arguments=Arguments(
                positional=tuple(pa.scalar(v) for v in positional), named={k: pa.scalar(v) for k, v in named.items()}
            ),
        )
    )
    return pa.Table.from_batches(batches, schema=bound[-1].output_schema)


def test_discovery_is_local_and_fields_are_live(treasury_client: Client, api: ApiServer) -> None:
    assert table(treasury_client, "datasets").num_rows == 6
    assert table(treasury_client, "datasets", query="penny")["dataset"].to_pylist() == ["debt_to_penny"]
    assert not api.requests
    result = table(treasury_client, "fields", "v2/accounting/od/debt_to_penny")
    types = dict(zip(result["field_name"].to_pylist(), result["source_type"].to_pylist(), strict=True))
    assert types["tot_pub_debt_out_amt"] == "CURRENCY"
    assert api.requests[-1]["query"]["page[size]"] == "1"


def test_precision_and_multiple_pages(treasury_client: Client, api: ApiServer) -> None:
    result = table(treasury_client, "debt_to_penny", page_size=2)
    assert result.num_rows == 5
    assert result["tot_pub_debt_out_amt"][0].as_py() == Decimal("37000000000000.35")
    assert result["tot_pub_debt_out_amt"][4].as_py() == Decimal("37000000000000.39")
    assert result["record_date"][0].as_py() == date(2024, 1, 2)
    assert [r["query"]["page[number]"] for r in api.requests] == ["1", "2", "3"]
    assert json.loads(result["source_json"][0].as_py())["tot_pub_debt_out_amt"] == "37000000000000.35"


def test_output_cap_keeps_page_size_constant(treasury_client: Client, api: ApiServer) -> None:
    result = table(treasury_client, "debt_to_penny", page_size=2, max_rows=3)
    assert result.num_rows == 3
    assert [r["query"]["page[size]"] for r in api.requests] == ["2", "2"]
    assert result["record_date"][-1].as_py() == date(2024, 1, 4)


def test_filters_sorting_empty_and_start_page(treasury_client: Client) -> None:
    filtered = table(
        treasury_client,
        "debt_to_penny",
        start_date="2024-01-03",
        end_date="2024-01-05",
        sort_fields="-record_date,src_line_nbr",
        page_size=1,
    )
    assert filtered["record_date"].to_pylist() == [date(2024, 1, 5), date(2024, 1, 4), date(2024, 1, 3)]
    assert table(treasury_client, "debt_to_penny", start_date="2100-01-01").num_rows == 0
    assert table(treasury_client, "debt_to_penny", start_page=2, page_size=2).num_rows == 3
    assert table(treasury_client, "debt_to_penny", start_page=10, page_size=2).num_rows == 0


def test_cash_nulls_and_source_units(treasury_client: Client) -> None:
    result = table(treasury_client, "operating_cash_balance", page_size=1)
    assert result["close_today_bal"][0].as_py() is None
    assert result["amount_units"][0].as_py() == "USD millions"
    assert result["open_today_bal"][0].as_py() == Decimal("100")
    result = table(
        treasury_client,
        "deposits_withdrawals",
        filters_json='[{"field":"transaction_type","op":"eq","value":"Deposits"}]',
    )
    assert result.num_rows == 3
    assert result["transaction_type"].to_pylist() == ["Deposits"] * 3


@pytest.mark.parametrize("name", ["public_debt_transactions", "monthly_statement", "average_interest_rates"])
def test_other_typed_tables(treasury_client: Client, name: str) -> None:
    assert table(treasury_client, name, page_size=2).num_rows == 5


def test_generic_records_preserve_source_nulls(treasury_client: Client) -> None:
    result = table(treasury_client, "records", "v1/accounting/dts/operating_cash_balance", page_size=2)
    assert json.loads(result["record_json"][0].as_py())["close_today_bal"] == "null"


@pytest.mark.parametrize(
    "mode,match",
    [
        ("STALLED", "short or empty"),
        ("CHANGED", "count changed|pagination"),
        ("REPEAT", "repeated"),
        ("WRONG_PAGE", "different page"),
        ("BAD_CURRENCY", "invalid debt_held"),
        ("DRIFT", "missing declared fields"),
    ],
)
def test_invalid_pages_fail(treasury_client: Client, api: ApiServer, mode: str, match: str) -> None:
    api.mode = mode
    with pytest.raises(Exception, match=match):
        table(treasury_client, "debt_to_penny", page_size=1)


def test_retries_and_redirect_rejection(treasury_client: Client, api: ApiServer) -> None:
    api.mode = "RETRY"
    assert table(treasury_client, "debt_to_penny", max_rows=1).num_rows == 1
    assert api.attempts == 2
    api.mode = "REDIRECT"
    with pytest.raises(Exception, match="HTTP 302"):
        table(treasury_client, "debt_to_penny", max_rows=1)


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com",
        "v2/../private",
        "v2/accounting/od/debt?secret=x",
        "v2/accounting/od/%2e%2e",
        "/v2/accounting/od/debt",
    ],
)
def test_invalid_endpoints(value: str) -> None:
    with pytest.raises(ApiError):
        endpoint(value)


@pytest.mark.parametrize(
    "value",
    [
        "{}",
        '[{"field":"record_date","op":"eq","value":"2024-01-01,other:eq:x"}]',
        '[{"field":"x","op":"unknown","value":"x"}]',
        '[{"field":"x","op":"in","value":[]}]',
        '[{"field":"x","field":"y","op":"eq","value":"z"}]',
        '[{"field":"x","op":"eq","value":true}]',
    ],
)
def test_invalid_filters(value: str) -> None:
    with pytest.raises(ApiError):
        filters_json(value)


def test_filter_in_and_parenthesized_account_names() -> None:
    assert filters_json('[{"field":"record_fiscal_year","op":"in","value":[2023,2024]}]') == [
        "record_fiscal_year:in:(2023,2024)"
    ]
    assert filters_json('[{"field":"account_type","op":"eq","value":"Treasury General Account (TGA)"}]') == [
        "account_type:eq:Treasury General Account (TGA)"
    ]
    with pytest.raises(ApiError):
        sort_fields("record_date,record_date")


@pytest.mark.parametrize("value", ["1.001", "NaN", "Infinity", "1,000", 1.1, True])
def test_decimal_conversion_never_rounds_or_coerces(value: Any) -> None:
    with pytest.raises(ApiError):
        convert(value, column("amount", pa.decimal128(38, 2), "Test amount"))


def test_state_roundtrip_contains_no_source_rows() -> None:
    state = State(page_number=3, emitted=4, total=5, previous_digest="hash")
    assert State.deserialize_from_bytes(state.serialize_to_bytes()) == state
    assert set(state.__dataclass_fields__) == {"page_number", "emitted", "total", "previous_digest", "done"}


def test_invalid_date_bounds_make_no_request(treasury_client: Client, api: ApiServer) -> None:
    with pytest.raises(Exception, match="start_date must"):
        table(treasury_client, "debt_to_penny", start_date="2024-02-01", end_date="2024-01-01")
    assert table(treasury_client, "datasets", query="penny")["dataset"].to_pylist() == ["debt_to_penny"]
    assert not api.requests


WORKER_TOKEN = "fixture-only-worker-token-with-32-characters"


@pytest.fixture()
def treasury_http(api: ApiServer, tmp_path: Path) -> Iterator[str]:
    port_file = tmp_path / "port"
    environment = os.environ.copy()
    environment.update(VGI_BEARER_TOKENS=f"{WORKER_TOKEN}=analyst", VGI_PROXY_PROOF_MODE="off")
    environment.pop("VGI_JWT_ISSUER", None)
    with (tmp_path / "server.log").open("w+") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "treasury_worker.worker", "--http", "--port", "0", "--port-file", str(port_file)],
            stdout=log,
            stderr=log,
            env=environment,
        )
        try:
            deadline = time.monotonic() + 20
            while not port_file.exists():
                assert process.poll() is None, "HTTP worker exited before publishing its port"
                if time.monotonic() >= deadline:
                    pytest.fail("HTTP worker did not start within 20 seconds")
                time.sleep(0.05)
            location = "http://127.0.0.1:" + port_file.read_text().strip()
            while True:
                try:
                    with urllib.request.urlopen(location + "/health", timeout=0.5) as response:
                        if response.status == 200:
                            break
                except (urllib.error.URLError, TimeoutError):
                    if process.poll() is not None or time.monotonic() >= deadline:
                        pytest.fail("HTTP worker did not become ready")
                    time.sleep(0.05)
            yield location
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            log.seek(0)
            messages = log.read()
            assert WORKER_TOKEN not in messages


@pytest.mark.parametrize("token", [None, "incorrect-token"])
def test_http_rpc_rejects_missing_or_wrong_bearer(treasury_http: str, api: ApiServer, token: str | None) -> None:
    headers = {"Authorization": "Bearer " + token} if token else {}
    request = urllib.request.Request(treasury_http + "/__describe__", headers=headers)
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(request, timeout=5)
    assert exc.value.code == 401
    exc.value.close()
    with (
        pytest.raises(Exception, match="authentication rejected"),
        Client(transport="http", base_url=treasury_http, bearer_token=token, pool=None) as client,
    ):
        table(client, "datasets")
    assert api.requests == []


def test_http_bearer_authenticated_pages_and_secrets(treasury_http: str, api: ApiServer) -> None:
    with Client(transport="http", base_url=treasury_http, bearer_token=WORKER_TOKEN, pool=None) as client:
        result = table(client, "debt_to_penny", page_size=1)
    assert result.num_rows == 5
    assert len(api.requests) == 5
    assert all(WORKER_TOKEN not in str(query) for query in api.requests)


def test_http_health_remains_available_without_bearer(treasury_http: str) -> None:
    with urllib.request.urlopen(treasury_http + "/health", timeout=5) as response:
        assert response.status == 200


@pytest.mark.parametrize(
    "value",
    [
        "",
        " ",
        ",",
        WORKER_TOKEN,
        "=analyst",
        f"{WORKER_TOKEN}=",
        "short=analyst",
        f"{WORKER_TOKEN}=analyst,",
        f"{WORKER_TOKEN}=analyst,{WORKER_TOKEN}=other",
    ],
)
def test_bad_bearer_configuration_fails_without_exposing_token(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("VGI_BEARER_TOKENS", value)
    with pytest.raises(ValueError, match="Invalid VGI_BEARER_TOKENS") as exc:
        validate_http_auth()
    assert WORKER_TOKEN not in str(exc.value)


def test_bearer_configuration_accepts_multiple_principals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VGI_BEARER_TOKENS", f"{WORKER_TOKEN}=analyst,{WORKER_TOKEN}-second=service")
    validate_http_auth()
    monkeypatch.delenv("VGI_BEARER_TOKENS")
    validate_http_auth()


def test_bad_bearer_configuration_stops_http_startup(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment["VGI_BEARER_TOKENS"] = WORKER_TOKEN
    port_file = tmp_path / "port"
    result = subprocess.run(
        [sys.executable, "-m", "treasury_worker.worker", "--http", "--port-file", str(port_file)],
        capture_output=True,
        text=True,
        env=environment,
        timeout=10,
    )
    assert result.returncode != 0
    assert "Invalid VGI_BEARER_TOKENS" in result.stderr
    assert WORKER_TOKEN not in result.stderr + result.stdout
    assert not port_file.exists()
