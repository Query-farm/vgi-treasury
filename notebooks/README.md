# Treasury Fiscal Data notebooks

Read the saved results on GitHub or choose **Open in Colab** at the top of each notebook.

| Notebook | Question | Default → experiment |
|---|---|---|
| [01 · Debt components and report changes](01_debt_components_and_report_changes.ipynb) | Do exact debt stocks and their component changes reconcile? | END_DATE January 12 → January 19, 2024 |
| [02 · Cash-flow boundaries](02_cash_flows_have_different_boundaries.ipynb) | Do net cash and net debt issuance describe the same accounting scope? | LAST_REPORT January 10 → January 12, 2024 |
| [03 · Report dates and measurements](03_one_report_date_many_measurements.ipynb) | Which fiscal months and rate summaries belong in a comparison? | REPORT_DATE January 31 → February 29, 2024 |

**All saved analytical amounts are original public Treasury data, not synthetic fixtures.** Recorded responses are served locally through the real released worker; generated pagination envelopes preserve source rows. Notebook 01 retains the existing exact-dollar debt narrative and SQL. The new stories preserve whole-million rounding residuals, distinguish cash-flow scopes, select monthly hierarchy explicitly, and separate component percentages from published rate aggregates.

## Run from this directory

Install [uv](https://docs.astral.sh/uv/). Initial packages, verified public companions, the VGI extension and Git-tag worker need internet. The shared base supports Python 3.11–3.14 kernels; uv provisions the worker's separate Python 3.13+ environment. No worker checkout, local build or globally registered kernel is required.

```sh
uv sync --locked --extra runner
uv run --locked --extra runner vgi-notebooks
uv run --locked --extra runner vgi-notebooks 01_debt_components_and_report_changes.ipynb --parameters '{"END_DATE":"2024-01-19"}' --output-dir validation/longer-debt
uv run --locked --extra runner vgi-notebooks 02_cash_flows_have_different_boundaries.ipynb --parameters '{"LAST_REPORT":"2024-01-12"}' --output-dir validation/longer-cash
uv run --locked --extra runner vgi-notebooks 03_one_report_date_many_measurements.ipynb --parameters '{"REPORT_DATE":"2024-02-29"}' --output-dir validation/february
```

Interactive Jupyter uses this environment's kernel and this directory as cwd. Restart and Run All after changing parameters. Colab installs only the shared base, preserving compatible preloaded data/plotting and kernel libraries; `[runner]` is for local publication. Shared tools provide canonical branding, SVG charts, isolated SQL sessions, verified companions, coverage receipts and atomic execution. Parameter overrides require a separate output directory; failed runs preserve the last successful notebook.

Each notebook visibly launches the clean release:

```sql
INSTALL vgi FROM community;
LOAD vgi;
ATTACH 'treasury' (TYPE vgi,
 LOCATION 'uvx --from git+https://github.com/Query-farm/vgi-treasury@v0.1.0 vgi-treasury-worker');
```

Release v0.1.0 resolves to `d5466e080cc8d241ced42b6d82d509c0b70766dc`. Reviewed current public main is `e27520088422ac6b5698c117908a9e8c36a63f62`; both actual catalogs have the same nine signatures. Main adds metadata examples and a truststore-based HTTPS context after the release. The notebook deliberately uses the release's original runtime; it does not claim those changes are already released. No transitive `--with` overrides are required. Notebook dependencies are locked separately from the worker's declared dependency ranges.

## Recorded public data and live access

The unchanged [debt provenance](fixtures/provenance.json) and [raw response](fixtures/debt-january-2024.json) cover 21 January 2024 reports, captured November 14, 2026. The [additional capture manifest](fixtures/discovery-provenance.json) records exact official requests, UTC times, HTTP status, hashes and row counts for five original responses: 20 cash rows, 905 deposit/withdrawal rows and 115 debt-transaction rows across January 8–12, plus 41 monthly-statement rows and 34 rate rows across January/February reports. Raw bytes, metadata and source strings remain intact.

`recorded_api.py` serves the unchanged debt recording. `multi_recorded_api.py` serves the additional recordings, checks every file hash and advertised total, accepts only known endpoints and bounded date/sort contracts, and re-paginates rows without changing values. `fields()` receives captured metadata from a single recorded row; it does not establish when those labels became available historically. Requests are audited without credentials. Both helpers temporarily replace inherited Treasury settings and restore them at cleanup.

The official Fiscal Data service requires **no upstream API key**. Shared `connect(globals())` creates an empty temporary SQL-secret directory before ATTACH, disables persistence and default INI connection autoload, and verifies an empty inventory; these notebooks create no secrets. Cleanup checks it is still empty, closes the connection/store and stops the loopback service. No user's saved credentials are read or changed.

Notebook 01 retains explicit live mode with no silent fallback:

```sh
uv run --locked --extra runner vgi-notebooks 01_debt_components_and_report_changes.ipynb --parameters '{"DATA_MODE":"live"}' --output-dir validation/live
```

Live mode selects only the official HTTPS endpoint and disables loopback opt-in. The historical range stays bounded; responses may be revised, pages are not atomic, and equal-count revisions may escape detection. TLS verification remains enabled. If your Python runtime needs an approved CA bundle, configure its standard `SSL_CERT_FILE`; no machine-specific path or global trust change is shipped. A separate released-worker live probe succeeded for January 2–3 on this host. The full live notebook also passed all twelve checks for nine January 2–12 reports; its exact-dollar table and result summary matched the recorded default. This live verification used shared 0.3.29 before the registry-only 0.3.30 update. Future live results are separate from saved recorded defaults; failure never substitutes replay data.

## Interpretation boundaries

01 keeps `DECIMAL(38,2)` USD amounts exact and displays money as strings to preserve cents through pandas. Charts alone use trillions/billions. Debt stocks are not spending or deficits; adjacent-report changes can span several calendar days. The first change remains NULL; missing dates are not filled. Twelve original invariants and the exact HTTP page audit remain.

02 uses whole **USD millions**. In these records, legacy `close_today_bal` is NULL; the value on the explicitly labeled TGA Closing Balance row is in `open_today_bal`. Total deposit/withdrawal rows are selected separately from detail rows to prevent double counting. Cash closing-minus-opening differs from published deposits-minus-withdrawals by at most one million in this capture; the residual is retained, consistent with independently rounded reporting, not forced to zero. Net issues-minus-redemptions has a different scope from net cash. No fiscal cause is inferred from their difference.

03 joins monthly details to fiscal-year parent headers and keeps year-to-date totals as checks. Record date is a report identifier, not the represented period of every row. Raw and typed monthly records are reconciled, including NULL headers and source field descriptors. Monthly values remain **API currency units**, scaled by 10⁹ only for plotting; CURRENCY metadata does not establish the website's scale. Rate values remain percentages on outstanding securities. An equal-weight average across component classes is a different statistic from the published aggregate; required principal weights are absent. No interest expense, new-issue price, forecast or sustainability calculation is claimed.

## Coverage and validation

Actual release and current runtime catalogs contain **nine named functions**, with no tables/views. All nine receive meaningful SQL/result interpretation across the three stories: datasets, fields, records, debt_to_penny, operating_cash_balance, deposits_withdrawals, public_debt_transactions, monthly_statement and average_interest_rates. The curated `datasets()` list is not a full upstream endpoint inventory. `coverage.json` retains full native catalogs, current source differences, editorial mappings and raw-JSON execution receipts; current-interface coverage remains separate from exact release-runtime evidence.

Each default and meaningful parameter experiment is executed; one fresh preloaded Python 3.12 notebook-only run tests their common launch and companion-download path. Actual hosted Colab is untested. Every figure is reviewed in both variants, with published SVGs checked in GitHub's renderer. Review PNGs, execution logs and experimental notebooks are ignored. The [shared standard](https://github.com/Query-farm/vgi-example-notebooks/blob/main/docs/standard.md) replaces local copies of runner, presentation helpers and standards.

Unchanged current source CI [43615390721](https://github.com/Query-farm/vgi-treasury/actions/runs/43615390721) is reused, alongside actual released-worker SQL and focused new replay-helper checks. No worker source, root lock, engine build, source test suite, deployment or container publication is part of this notebook-only update.

Shared tools are pinned to [v0.3.30](https://github.com/Query-farm/vgi-example-notebooks/releases/tag/v0.3.30). The `treasury` registry verifies ten companions at public revision `8c193efbca17a1633bbcf95d8fb7e36868e95a26`: two replay helpers, six original public response files and two provenance manifests.
