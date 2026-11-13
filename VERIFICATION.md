# Release verification

Verified 2026-11-13 on macOS arm64 with Python 3.14.4. Installed artifact checks
also use Python 3.13.16.

- Starter: Query-farm/vgi-starter-python at `9cca9105474d6e0052b8e343c8ea21f3d1a7503c`.
  Its baseline passed before adaptation; original assertions remain in the suite.
- Runtime: vgi-python 0.51.1 / vgi-rpc 0.53.1; starter SDK constraints retained.
- `make check`: Ruff formatting/lint, strict mypy, pydoclint, 97 pytest tests;
  Haybarn 2.0.0rc11 SQL checks: 115 stdio assertions, 115 launch, 79 HTTP, zero skips.
- Metadata: strict `fail_on = "info"`, no waivers, 100/100 L2, zero findings.
  Behavioral probes use offline fixtures.
- Stock DuckDB 2.0.0 / signed Query.Farm VGI extension `e75482339d`:
  18 stdio checks and 20 HTTP checks, including authentication, exact currency,
  multi-page caps, source filters, nulls and all nine functions.
- Live official API: nine checks passed, including every typed endpoint, live
  field metadata, generic MTS Table 9 records and local discovery. The local uv
  Python trust store required `SSL_CERT_FILE=/opt/homebrew/etc/openssl@3/cert.pem`;
  certificate verification stayed enabled. No upstream credentials are required.
- `uv build`, `twine check`, isolated wheel and sdist installation: each artifact
  repeats the 18 stdio and 20 authenticated HTTP checks outside this checkout.

Reports are generated under ignored `build/`. CI repeats quality checks on
Python 3.13/3.14, SQL transport checks on Linux/Windows, stock DuckDB, installed
artifacts and Docker health checks. Releases are gated by CI; wheel and source
artifacts are Sigstore-signed and the wheel carries a provenance attestation.

MTS raw API currency units are deliberately not relabeled as millions. Source
schema drift and incomplete pagination fail. Concurrent equal-count revisions
are not an atomic snapshot and cannot always be detected.

The optional L3 agent evaluation could not complete because its external agent
backend rejected the evaluation prompt. No L3 assurance is claimed. An optional
documentation review identified scope wording, which was clarified before release.
