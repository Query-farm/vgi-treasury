# Treasury debt components notebook

[Debt components and report changes](01_debt_components_and_report_changes.ipynb) reconciles total public debt with publicly held debt and intragovernmental holdings, then decomposes changes between reported dates. Exact USD cents remain in SQL; the two charts explicitly scale levels to trillions and changes to billions.

## Run from this directory

Install [uv](https://docs.astral.sh/uv/) and Git. The locked notebook environment uses Python 3.13 or 3.14 and Haybarn 2.0.0rc11; the worker uses Python 3.13. First use needs network access for dependencies, the published VGI extension and the pinned Git worker. Recorded analysis then uses only the bundled public response and a loopback server. This directory can be copied alone; no worker checkout or local build is needed.

```bash
uv sync --frozen
uv run --frozen python execute.py
```

The visible literal launcher fetches public Git revision `d5466e080cc8d241ced42b6d82d509c0b70766dc` with VGI SDK 0.51.1 / RPC 0.53.1. Rerun the default, experiment and explicit live validation after changing a pin.

For interactive use, register this environment and select it in Jupyter:

```bash
uv run --frozen python -m ipykernel install --user --name vgi-treasury-notebooks --display-name 'Python (treasury notebooks)'
```

Restart and run all after changing parameters. Connection and domain SQL remain visible; Python imports, plotting, interpretation source and cleanup are folded. The runner creates a temporary kernel with this directory as cwd and saves only successful outputs. Overrides require a separate destination; unknown parameters and source-directory output destinations are rejected.

## Recorded public response and explicit live mode

The default `DATA_MODE = "recorded"` uses the original official [Debt to the Penny API](https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny) response for **2024-01-02 through 2024-01-31**, captured on **2026-11-14**. It contains 21 records. [Provenance](fixtures/provenance.json) records the exact request parameters, UTC capture time, response hash and coverage; [the raw JSON](fixtures/debt-january-2024.json) retains original currency strings, metadata and links. These amounts are public Treasury records, not synthetic examples.

[recorded_api.py](recorded_api.py) serves the recorded rows through the worker's supported `TREASURY_API_BASE_URL` override and explicit loopback-HTTP opt-in. It filters the recorded date range, preserves row content, and generates pagination envelopes for the requested page size. Unsupported routes, sorts or bounds are rejected. Inherited Treasury settings are cleared for this run and restored on cleanup. Recorded mode does not contact Treasury; the real released worker still performs HTTP, pagination checks, typed decimal conversion and VGI output.

Live mode selects only the official HTTPS endpoint, removes the loopback opt-in, and never falls back to recorded rows:

```bash
uv run --frozen python execute.py --parameters '{"DATA_MODE":"live"}' --output-dir validation/live
```

It uses the same bounded historical window, not the current date. Live labels show the run start time; separate pages are not an atomic snapshot, and equal-count revisions may escape consistency detection. TLS certificate verification remains enabled. If your Python runtime needs an approved CA bundle, set its standard `SSL_CERT_FILE` environment variable; the notebook does not modify system trust or ship a machine-specific certificate path.

## Focused experiment

```bash
uv run --frozen python execute.py --parameters '{"END_DATE":"2024-01-19"}' --output-dir validation/longer-window
```

`END_DATE` accepts ISO dates from 2024-01-03 through 2024-01-31; default is 2024-01-12. The fixed start is 2024-01-02, and bounds are inclusive source record dates. Keep recorded mode for the experiment. Extending the endpoint adds returned reports and pages; compare the net component contributions and endpoint difference without presuming a direction. The shared prefix through January 12 must retain its exact records and differences. Restore 2024-01-12 for the default.

Every retrieval uses four rows per page, deterministic `record_date,src_line_nbr` ordering and `max_rows := 0`, streaming all matches inside the bounded range. An explicit cap would return a prefix; SQL LIMIT is not a source cap. Source calls are materialized once with visible CTAS, then captured displays query local tables.

The source unit is **USD**, and all three accounting amounts are `DECIMAL(38,2)`. Displayed amount strings preserve cents through pandas; independent SQL casts compare every original currency string with its typed value. Only presentation ratios use floating-point trillions/billions. Debt stocks are not annual spending or deficits. Adjacent-report changes can span multiple calendar days and are not normalized daily rates. The first report's change remains NULL; weekends and nonreporting dates are not filled. Connecting lines guide the eye and do not create observations.

Twelve SQL invariants cover keys, dates, units, decimal types, complete components, exact identities, source-string round trips, missing first difference, component changes and telescoping sums. Recorded mode also checks the raw response hash, expected selected row count and complete page sequence. The notebook does not infer fiscal causes, future borrowing or sustainability from these arithmetic identities.

Saved outputs embed both charts. Logs, chart PNGs and experiment copies are ignored under `validation/`; copies include assets, raw response, source helper and locked environment. [STANDARD.md](STANDARD.md) records presentation conventions.

`make check` passed: source Ruff/format, strict mypy, pydoclint, 97 pytest tests, 115 stdio SQL assertions, 115 launch assertions, 79 HTTP assertions, metadata 100/100 L2 with zero findings, and stock DuckDB 2.0.0 checks (18 stdio, 20 authenticated HTTP). No engine rebuild, worker change or root lock modification was needed.

Validation on 2026-11-14 executed the recorded default, a notebook-only 2024-01-19 experiment, and explicit live mode. The live default's exact-dollar display matched the capture. The longer recorded run increased reports from 9 to 13 and pages from 3 to 4, preserving the shared exact-dollar prefix. All six rendered charts and three runner guards were reviewed. This is recorded validation evidence, not a guarantee that future live responses remain unchanged.
