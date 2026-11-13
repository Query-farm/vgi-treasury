"""Typed Treasury fiscal tables, endpoint discovery and bounded pagination."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from typing import Annotated, Any, ClassVar

import pyarrow as pa
from vgi.arguments import Arg
from vgi.invocation import BindResponse
from vgi.table_function import BindParams, OutputCollector, ProcessParams, TableFunctionGenerator, init_single_worker
from vgi_rpc import ArrowSerializableDataclass

from .api import ENDPOINT_PATTERN, endpoint, filters_json, iso_date, page, sort_fields
from .meta import column, function_meta
from .schemas import DATASETS
from .transport import ApiError

DATASET_SCHEMA = pa.schema(
    [
        column("dataset", pa.string(), "Name of a typed worker function.", nullable=False),
        column("endpoint", pa.string(), "Relative Fiscal Data route for fields or records.", nullable=False),
        column("title", pa.string(), "Dataset title."),
        column("amount_units", pa.string(), "Source amount scale; generic API amounts are not rescaled."),
        column("description", pa.string(), "Scope and interpretation notes."),
    ]
)
FIELD_SCHEMA = pa.schema(
    [
        column("field_name", pa.string(), "Source API field name.", nullable=False),
        column("label", pa.string(), "Source field label."),
        column("source_type", pa.string(), "Treasury's type identifier, such as DATE or CURRENCY."),
        column("source_format", pa.string(), "Source display-format descriptor; not an inferred scale conversion."),
    ]
)
RECORD_SCHEMA = pa.schema(
    [
        column("record_date", pa.date32(), "Source record date when present; not necessarily the observation period."),
        column(
            "record_json",
            pa.string(),
            "Complete original row with exact source strings and null markers.",
            nullable=False,
        ),
    ]
)


@dataclass(frozen=True, kw_only=True)
class BaseArgs:
    """No required arguments for local dataset discovery."""


@dataclass(frozen=True, kw_only=True)
class DatasetArgs(BaseArgs):
    """Case-insensitive search within the local dataset catalog."""

    query: Annotated[
        str,
        Arg(
            "query",
            default="",
            doc="Case-insensitive substring matched against each catalog entry; empty returns every entry.",
        ),
    ]


@dataclass(frozen=True, kw_only=True)
class PageArgs(BaseArgs):
    """Upstream filters, stable sorting and a bounded page cursor."""

    start_date: Annotated[
        str,
        Arg("start_date", default="", doc="Inclusive record_date lower bound, YYYY-MM-DD; empty leaves it unbounded."),
    ]
    end_date: Annotated[
        str,
        Arg("end_date", default="", doc="Inclusive record_date upper bound, YYYY-MM-DD; empty leaves it unbounded."),
    ]
    filters_json: Annotated[
        str,
        Arg(
            "filters_json",
            default="[]",
            doc=(
                "Array of field/op/value objects; operators eq, lt, lte, gt, gte and in. Values are "
                "strings/integers; in takes an array."
            ),
        ),
    ]
    sort_fields: Annotated[
        str,
        Arg(
            "sort_fields",
            default="record_date,src_line_nbr",
            doc=(
                "Comma-separated source sort fields; prefix '-' for descending. Include a unique "
                "tie-breaker for stable pagination."
            ),
        ),
    ]
    page_size: Annotated[
        int,
        Arg(
            "page_size",
            default=1000,
            ge=1,
            le=1000,
            doc="Rows requested per API page; remains fixed throughout pagination.",
        ),
    ]
    max_rows: Annotated[
        int,
        Arg("max_rows", default=0, ge=0, le=10000000, doc="Explicit output cap; zero streams all matching records."),
    ]
    start_page: Annotated[
        int,
        Arg(
            "start_page",
            default=1,
            ge=1,
            le=10000000,
            doc="One-based upstream page to start from, using the selected page_size.",
        ),
    ]


@dataclass(frozen=True, kw_only=True)
class EndpointArgs(BaseArgs):
    """A relative public Fiscal Data endpoint."""

    endpoint: Annotated[
        str,
        Arg(
            0,
            pattern=ENDPOINT_PATTERN,
            doc=(
                "Relative Fiscal Data endpoint, e.g. v2/accounting/od/debt_to_penny. Absolute URLs "
                "and traversal are forbidden."
            ),
        ),
    ]


@dataclass(frozen=True, kw_only=True)
class RecordsArgs(PageArgs):
    """Generic JSON records from any valid public endpoint."""

    endpoint: Annotated[
        str,
        Arg(
            0, pattern=ENDPOINT_PATTERN, doc="Relative public Fiscal Data endpoint; use fields() to inspect its schema."
        ),
    ]


@dataclass(kw_only=True)
class State(ArrowSerializableDataclass):
    """Portable counters and a page digest; no credentials or source records."""

    page_number: int = 1
    emitted: int = 0
    total: int = -1
    previous_digest: str = ""
    done: bool = False


def source_json(value: Any) -> str:
    """Serialize source metadata without accepting non-finite JSON numbers."""
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError, OverflowError):
        raise ApiError("Treasury response contains invalid JSON values") from None


def convert(value: Any, field: pa.Field[Any]) -> Any:
    """Convert source values strictly, retaining exact currency and source nulls."""
    if value is None or value == "null":
        if not field.nullable:
            raise ApiError(f"Treasury response is missing required {field.name}")
        return None
    try:
        if pa.types.is_date32(field.type):
            return iso_date(value, field.name)
        if pa.types.is_decimal(field.type):
            if not isinstance(value, str) or re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value) is None:
                raise ValueError
            number = Decimal(value)
            with localcontext() as context:
                context.prec = 40
                quantized = number.quantize(Decimal(1).scaleb(-field.type.scale))
            if number != quantized or len(quantized.as_tuple().digits) > field.type.precision:
                raise ValueError
            return quantized
        if pa.types.is_integer(field.type):
            if type(value) not in (str, int) or re.fullmatch(r"-?\d+", str(value)) is None:
                raise ValueError
            return int(value)
        if not isinstance(value, str):
            raise ValueError
        return value
    except (TypeError, ValueError, OverflowError, InvalidOperation):
        raise ApiError(f"Treasury response has invalid {field.name}") from None


def typed_rows(raw: list[dict[str, Any]], schema: pa.Schema, units: str) -> list[dict[str, Any]]:
    """Preserve all source fields while refusing silent schema drift in typed functions."""
    result = []
    for row in raw:
        missing = set(schema.names) - {"source_json", "amount_units"} - set(row)
        if missing:
            raise ApiError("Treasury response is missing declared fields; inspect fields() for upstream schema changes")
        result.append(
            {
                field.name: source_json(row)
                if field.name == "source_json"
                else units
                if field.name == "amount_units"
                else convert(row[field.name], field)
                for field in schema
            }
        )
    return result


@init_single_worker
class FiscalFunction[T: BaseArgs](TableFunctionGenerator[T, State]):
    """One validated API page per Arrow batch, with resumable HTTP state."""

    FIXED_SCHEMA: ClassVar[pa.Schema]
    DATASET: ClassVar[str] = ""

    @classmethod
    def on_bind(cls, params: BindParams[T]) -> BindResponse:
        """Validate all caller-controlled query syntax without network work at bind."""
        args = params.args
        if isinstance(args, PageArgs):
            if args.start_date:
                iso_date(args.start_date, "start_date")
            if args.end_date:
                iso_date(args.end_date, "end_date")
            if args.start_date and args.end_date and args.start_date > args.end_date:
                raise ApiError("start_date must not be after end_date")
            filters_json(args.filters_json)
            sort_fields(args.sort_fields)
        if isinstance(args, (RecordsArgs, EndpointArgs)):
            endpoint(args.endpoint)
        return BindResponse(output_schema=cls.FIXED_SCHEMA)

    @classmethod
    def initial_state(cls, params: ProcessParams[T]) -> State:
        """Create a small page cursor independent of any server process."""
        return State(page_number=params.args.start_page if isinstance(params.args, PageArgs) else 1)

    @classmethod
    def fetch(cls, args: T, state: State) -> list[dict[str, Any]]:
        """Read and validate a page of typed or generic Fiscal Data records."""
        if not isinstance(args, PageArgs):
            raise NotImplementedError
        route = args.endpoint if isinstance(args, RecordsArgs) else DATASETS[cls.DATASET].endpoint
        filters = filters_json(args.filters_json)
        if args.start_date:
            filters.append("record_date:gte:" + args.start_date)
        if args.end_date:
            filters.append("record_date:lte:" + args.end_date)
        query = {"sort": sort_fields(args.sort_fields)}
        if filters:
            query["filter"] = ",".join(filters)
        raw, _metadata, total = page(route, query, state.page_number, args.page_size)
        if state.total != -1 and state.total != total:
            raise ApiError("Treasury result count changed during pagination; retry with a fixed historical date window")
        digest = hashlib.sha256(source_json(raw).encode()).hexdigest()
        if raw and digest == state.previous_digest:
            raise ApiError("Treasury repeated an API page; refusing duplicate results")
        state.previous_digest = digest
        state.total = total
        state.done = state.page_number * args.page_size >= total
        state.page_number += 1
        selected = raw[: max(0, args.max_rows - state.emitted)] if args.max_rows else raw
        if isinstance(args, RecordsArgs):
            rows = [
                {
                    "record_date": convert(row.get("record_date"), RECORD_SCHEMA.field("record_date")),
                    "record_json": source_json(row),
                }
                for row in selected
            ]
        else:
            rows = typed_rows(selected, cls.FIXED_SCHEMA, DATASETS[cls.DATASET].amount_units)
        state.emitted += len(rows)
        if args.max_rows and state.emitted >= args.max_rows:
            state.done = True
        return rows

    @classmethod
    def process(cls, params: ProcessParams[T], state: State, out: OutputCollector) -> None:
        """Emit one page; subsequent calls resume using the serialized cursor."""
        if state.done:
            out.finish()
            return
        rows = cls.fetch(params.args, state)
        try:
            batch = pa.RecordBatch.from_pylist(rows, schema=params.output_schema)
        except (pa.ArrowException, ValueError, OverflowError):
            raise ApiError("Treasury response cannot be represented by the declared schema") from None
        out.emit(batch)


class Datasets(FiscalFunction[DatasetArgs]):
    """Discover curated typed endpoints without a network request."""

    FIXED_SCHEMA = DATASET_SCHEMA
    Meta = function_meta(
        "datasets",
        "Discover fiscal datasets",
        (
            "Search the worker's curated typed endpoints, amount scales and interpretation notes. "
            "This local catalog is not an exhaustive listing of every Treasury API dataset; use "
            "records() for other relative Fiscal Data routes."
        ),
        DATASET_SCHEMA,
        "SELECT dataset, endpoint, amount_units FROM treasury.main.datasets() ORDER BY dataset",
    )

    @classmethod
    def fetch(cls, args: DatasetArgs, state: State) -> list[dict[str, Any]]:
        """Return the versioned catalog shipped with the worker."""
        state.done = True
        return [
            {
                "dataset": name,
                "endpoint": info.endpoint,
                "title": info.title,
                "amount_units": info.amount_units,
                "description": info.description,
            }
            for name, info in DATASETS.items()
            if args.query.casefold() in (name + " " + info.title + " " + info.description).casefold()
        ]


class Fields(FiscalFunction[EndpointArgs]):
    """Inspect live source labels, types and formatting metadata."""

    FIXED_SCHEMA = FIELD_SCHEMA
    Meta = function_meta(
        "fields",
        "Inspect endpoint fields",
        (
            "Read live field metadata for a relative Fiscal Data endpoint. Fetches a single "
            "source row to obtain metadata; it emits only field names, labels, source types and "
            "format descriptors."
        ),
        FIELD_SCHEMA,
        (
            "SELECT field_name, source_type, source_format FROM "
            "treasury.main.fields('v2/accounting/od/debt_to_penny') ORDER BY field_name"
        ),
    )

    @classmethod
    def fetch(cls, args: EndpointArgs, state: State) -> list[dict[str, Any]]:
        """Read field descriptors from one bounded source page."""
        _rows, metadata, _total = page(args.endpoint, {}, 1, 1)
        labels, types, formats = (metadata.get(name) for name in ("labels", "dataTypes", "dataFormats"))
        if not all(isinstance(value, dict) for value in (labels, types, formats)):
            raise ApiError("Treasury response is missing field metadata")
        assert isinstance(labels, dict) and isinstance(types, dict) and isinstance(formats, dict)
        if set(labels) != set(types) or set(labels) != set(formats):
            raise ApiError("Treasury field metadata keys are inconsistent")
        result = []
        for name in labels:
            values = [labels[name], types[name], formats[name]]
            if not isinstance(name, str) or any(not isinstance(v, str) for v in values):
                raise ApiError("Treasury response has invalid field metadata values")
            result.append(
                {"field_name": name, "label": labels[name], "source_type": types[name], "source_format": formats[name]}
            )
        state.done = True
        return result


class Records(FiscalFunction[RecordsArgs]):
    """Retrieve exact source JSON from endpoints beyond the curated typed catalog."""

    FIXED_SCHEMA = RECORD_SCHEMA
    Meta = function_meta(
        "records",
        "Read arbitrary fiscal records",
        (
            "Stream exact source records from any relative Fiscal Data v1/v2 route. record_json "
            "preserves every field; inspect fields() before extracting values. The default sort "
            "assumes record_date and src_line_nbr; choose sort_fields for endpoints with "
            "different keys."
        ),
        RECORD_SCHEMA,
        (
            "SELECT record_date, record_json FROM "
            "treasury.main.records('v2/accounting/od/debt_to_penny', start_date := '2024-01-02', "
            "end_date := '2024-01-03') ORDER BY record_date"
        ),
    )


class DebtToPenny(FiscalFunction[PageArgs]):
    """Federal debt with exact cent precision."""

    DATASET = "debt_to_penny"
    FIXED_SCHEMA = DATASETS[DATASET].schema
    Meta = function_meta(
        DATASET,
        DATASETS[DATASET].title,
        DATASETS[DATASET].description,
        FIXED_SCHEMA,
        (
            "SELECT record_date, tot_pub_debt_out_amt FROM treasury.main.debt_to_penny(start_date "
            ":= '2024-01-02', end_date := '2024-01-03') ORDER BY record_date"
        ),
    )


class OperatingCashBalance(FiscalFunction[PageArgs]):
    """Operating cash balances with source amount units and account descriptions."""

    DATASET = "operating_cash_balance"
    FIXED_SCHEMA = DATASETS[DATASET].schema
    Meta = function_meta(
        DATASET,
        DATASETS[DATASET].title,
        DATASETS[DATASET].description,
        FIXED_SCHEMA,
        (
            "SELECT record_date, account_type, open_today_bal FROM "
            "treasury.main.operating_cash_balance(start_date := '2024-01-02', end_date := "
            "'2024-01-02') ORDER BY record_date, src_line_nbr"
        ),
    )


class DepositsWithdrawals(FiscalFunction[PageArgs]):
    """Daily cash deposits and withdrawals by source classification."""

    DATASET = "deposits_withdrawals"
    FIXED_SCHEMA = DATASETS[DATASET].schema
    Meta = function_meta(
        DATASET,
        DATASETS[DATASET].title,
        DATASETS[DATASET].description,
        FIXED_SCHEMA,
        (
            "SELECT transaction_type, transaction_catg, transaction_today_amt FROM "
            "treasury.main.deposits_withdrawals(start_date := '2024-01-02', end_date := "
            "'2024-01-02') ORDER BY src_line_nbr"
        ),
    )


class PublicDebtTransactions(FiscalFunction[PageArgs]):
    """Security issues and redemptions from the Daily Treasury Statement."""

    DATASET = "public_debt_transactions"
    FIXED_SCHEMA = DATASETS[DATASET].schema
    Meta = function_meta(
        DATASET,
        DATASETS[DATASET].title,
        DATASETS[DATASET].description,
        FIXED_SCHEMA,
        (
            "SELECT transaction_type, security_type, transaction_today_amt FROM "
            "treasury.main.public_debt_transactions(start_date := '2024-01-02', end_date := "
            "'2024-01-02') ORDER BY src_line_nbr"
        ),
    )


class MonthlyStatement(FiscalFunction[PageArgs]):
    """Monthly report rows retaining hierarchy, classifications and exact API amounts."""

    DATASET = "monthly_statement"
    FIXED_SCHEMA = DATASETS[DATASET].schema
    Meta = function_meta(
        DATASET,
        DATASETS[DATASET].title,
        DATASETS[DATASET].description,
        FIXED_SCHEMA,
        (
            "SELECT classification_desc, current_month_gross_rcpt_amt, "
            "current_month_gross_outly_amt FROM treasury.main.monthly_statement(start_date := "
            "'2024-01-31', end_date := '2024-01-31') WHERE data_type_cd='D' ORDER BY src_line_nbr"
        ),
    )


class AverageInterestRates(FiscalFunction[PageArgs]):
    """Average interest rates expressed as source percentages."""

    DATASET = "average_interest_rates"
    FIXED_SCHEMA = DATASETS[DATASET].schema
    Meta = function_meta(
        DATASET,
        DATASETS[DATASET].title,
        DATASETS[DATASET].description,
        FIXED_SCHEMA,
        (
            "SELECT security_desc, avg_interest_rate_amt FROM "
            "treasury.main.average_interest_rates(start_date := '2024-01-31', end_date := "
            "'2024-01-31') ORDER BY security_desc"
        ),
    )


FUNCTIONS: list[type[Any]] = [
    Datasets,
    Fields,
    Records,
    DebtToPenny,
    OperatingCashBalance,
    DepositsWithdrawals,
    PublicDebtTransactions,
    MonthlyStatement,
    AverageInterestRates,
]
