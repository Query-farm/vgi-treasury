# vgi-treasury

Query public US Treasury Fiscal Data from DuckDB through a Python VGI worker.
Exact decimal amounts, source units and complete original records are retained.

## Install and query

Requires Python 3.13 or newer. Install a wheel from GitHub Releases, or run
`make build` in the locked source checkout.

```sql
SET allow_extension_repositories = 'allowed';
CREATE EXTENSION REPOSITORY IF NOT EXISTS query_farm
    WITH PREFIX 'https://duckdb-extensions.query.farm';
INSTALL vgi FROM query_farm;
LOAD vgi FROM query_farm;
ATTACH 'treasury' (TYPE vgi, LOCATION '/absolute/path/to/.venv/bin/vgi-treasury-worker');

SELECT record_date, tot_pub_debt_out_amt, amount_units
FROM treasury.main.debt_to_penny(start_date := '2024-01-01', end_date := '2024-01-31')
ORDER BY record_date;

SELECT dataset, endpoint, amount_units
FROM treasury.main.datasets() ORDER BY dataset;
```

The official Fiscal Data API is public and requires no upstream API key. HTTP
worker authentication is configured separately, as described below.

## Functions

All functions are in `treasury.main`. SQL NULL arguments are rejected.

| Function | Source and purpose |
| --- | --- |
| `datasets(query := '')` | Local catalog of six typed datasets; optional case-insensitive substring search |
| `fields(endpoint)` | Live field labels, source types and format descriptors |
| `records(endpoint, ...)` | Original JSON rows from any valid relative Fiscal Data v1/v2 endpoint |
| `debt_to_penny(...)` | Total public debt, debt held by the public and intragovernmental holdings |
| `operating_cash_balance(...)` | Daily Treasury Statement operating cash accounts |
| `deposits_withdrawals(...)` | Daily deposits and withdrawals by source classification |
| `public_debt_transactions(...)` | Daily public debt issues, redemptions and net changes |
| `monthly_statement(...)` | Monthly Treasury Statement Table 1 rows and hierarchy |
| `average_interest_rates(...)` | Interest rates by debt security description |

`datasets()` is a curated catalog, not an exhaustive upstream endpoint listing.
Use `fields()` and `records()` for other documented Fiscal Data endpoints.

Typed data functions and `records()` accept these named arguments:

| Argument | Default | Meaning |
| --- | --- | --- |
| `start_date`, `end_date` | `''` | Inclusive `record_date` bounds in YYYY-MM-DD format |
| `filters_json` | `'[]'` | Array of field/op/value objects; operators eq, lt, lte, gt, gte, in |
| `sort_fields` | `'record_date,src_line_nbr'` | Comma-separated fields; `-` prefix selects descending order |
| `page_size` | `1000` | Fixed source page size, 1–1000 |
| `max_rows` | `0` | Explicit output cap up to 10 million; zero streams all matches |
| `start_page` | `1` | One-based starting page using the chosen page size |

```sql
SELECT record_date, transaction_type, transaction_catg, transaction_today_amt
FROM treasury.main.deposits_withdrawals(
    start_date := '2024-01-01', end_date := '2024-01-31',
    filters_json := '[{"field":"transaction_type","op":"eq","value":"Deposits"}]')
ORDER BY record_date, src_line_nbr;

SELECT field_name, source_type, source_format
FROM treasury.main.fields('v1/accounting/mts/mts_table_9') ORDER BY field_name;

SELECT record_date, record_json
FROM treasury.main.records('v1/accounting/mts/mts_table_9',
    start_date := '2024-01-01', end_date := '2024-01-31', max_rows := 10)
ORDER BY record_date;
```

Filter values are strings or integers; `in` takes an array. Delimiter characters,
duplicate JSON keys and unsupported operators fail before requesting data. Generic
endpoints may require a different `sort_fields` value. Include keys that uniquely
order records. Function arguments are pushed upstream; SQL WHERE clauses are local.

## Values, units and completeness

- Currency uses DECIMAL(38,2), whole-million DTS amounts use DECIMAL(38,0), and
  interest rates use DECIMAL(38,6). Conversion never rounds excess precision or
  passes through floating point. Rates remain percentages, not fractions.
- Debt-to-the-penny amounts are USD. Daily Treasury Statement amounts are USD
  millions. `amount_units` records the scale; values are not multiplied or rescaled.
- Monthly statement API fields are preserved as raw **API currency units**. The
  Treasury website describes display values in millions, while API responses can
  contain unscaled currency amounts. Inspect `fields()` and `source_json` when
  reconciling API output with published reports; the worker does not infer a conversion.
- Source `"null"` and JSON null become SQL NULL. Every typed row also has
  `source_json`, retaining exact original strings and every field. Generic rows use
  `record_json`. Missing declared fields, invalid values and schema drift fail.
- `record_date` is a source record/report date. Monthly statement classifications,
  hierarchy and source period fields are retained; do not treat every row as an
  independent monthly observation or sum headers and subtotals together. Cash
  balance account definitions have changed over time; nullable closing-balance
  fields are preserved without inferring replacements from other accounts.
- Each API page becomes one Arrow batch. Page size remains fixed even when the
  output cap ends partway through a page. Counts, page numbers, repeated pages and
  source total changes are checked. Inconsistent or partial pages fail visibly.
- An explicit `max_rows` cap intentionally returns a prefix. SQL LIMIT alone is
  not an upstream cap. Separate requests are not an atomic snapshot; equal-count
  concurrent revisions cannot always be detected. Use historical date windows,
  deterministic sorting and bounded queries for reproducible extracts.

## HTTP authentication and deployment

```sh
export VGI_BEARER_TOKENS="$(openssl rand -hex 32)=analyst"
vgi-treasury-worker --http --host 127.0.0.1 --port 8000
```

Store persistent tokens in your secret manager. Tokens contain 32–4096 characters;
multiple principals use `token1=principal1,token2=principal2`. Empty or malformed
configuration fails startup without exposing its contents. Omitting the variable
leaves HTTP unauthenticated for local development. Each principal can access the
whole catalog, and `/health` remains public. Terminate TLS at your service ingress.

```sql
INSTALL httpfs FROM core;
LOAD httpfs;
ATTACH 'treasury' (TYPE vgi, LOCATION 'https://your-worker.example',
                   bearer_token 'your-worker-bearer-token');
```

Bearer tokens never go to Treasury. Continuation state contains only counters and
page digests. Worker stdout is reserved for Arrow RPC. A nonroot Docker image is
defined in `Dockerfile`; build with `docker build -t vgi-treasury .` and supply
secrets through your deployment platform. HTTP uses port 8000; `docker run -i
vgi-treasury stdio` selects stdio.

## Operations

| Environment variable | Default |
| --- | --- |
| `TREASURY_TIMEOUT_SECONDS` | 30 (0.1–120) |
| `TREASURY_MAX_ATTEMPTS` | 4 (1–6) |
| `TREASURY_RETRY_BUDGET_SECONDS` | 120 (1–600) |
| `TREASURY_MIN_INTERVAL_SECONDS` | 0.5 |
| `TREASURY_MAX_RESPONSE_BYTES` | 16777216 (1 KiB–64 MiB) |
| `TREASURY_API_BASE_URL` | `https://api.fiscaldata.treasury.gov/services/api/fiscal_service` |
| `TREASURY_ALLOW_INSECURE_HTTP` | unset; `1` permits loopback fixture HTTP only |

Network failures, 429 and 5xx responses use bounded backoff with jitter.
`Retry-After` is honored; a wait exceeding the retry budget fails without retrying
early. Redirects are refused. Request spacing is process-local; coordinate quotas
across replicas. The read budget is checked between chunks; blocking socket work
can extend wall time by its timeout. Responses have a byte limit, and there is no
persistent cache. API base URLs are trusted operator settings. Standard Python
TLS verification is enabled; configure `SSL_CERT_FILE` with your approved CA
bundle when your environment needs a custom trust store. Environment files are
not loaded automatically.

## Verification and releases

```sh
make check          # Static checks, pytest, three SQL transports, metadata, stock DuckDB
make smoke-live     # Official public Fiscal Data API checks
make package        # Wheel and source distribution
uvx twine check dist/*
python3 ci/verify-artifacts.py --python 3.13
make lint-ai        # Optional external-agent metadata evaluation
```

Metadata assurance uses local fixtures and retains strict `fail_on = "info"`
without waivers. Stock DuckDB checks include missing/wrong bearer rejection and
multi-page authenticated HTTP queries. Wheel and source installs are checked
outside the source checkout. See [VERIFICATION.md](VERIFICATION.md) for measured
results and limitations. CI gates releases, signs artifacts with Sigstore, and
attests wheel provenance. Upstream data licensing remains separate from this
worker's 0BSD software license.

Sources: [Fiscal Data API documentation](https://fiscaldata.treasury.gov/api-documentation/),
[Debt to the Penny](https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/),
[Daily Treasury Statement](https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/),
[Monthly Treasury Statement](https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/).
