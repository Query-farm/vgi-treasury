# Changelog

## 0.1.1 (unreleased)

- The catalog comment (the one-line description directories show, VGI001) is now
  a short plain-text sentence of at most 300 characters saying what data the
  worker covers. The long-form Markdown documentation remains in the catalog's
  `vgi.doc_md` tag and agent guidance in `vgi.doc_llm`.

## 0.1.0 (unreleased)

Initial worker generated from the VGI starter template.

- Composed examples: debt_to_penny × public_debt_transactions (daily debt change
  reconciled with issues minus redemptions), operating_cash_balance × debt_to_penny
  (TGA cash as a share of debt) and records × fields (a raw record labelled field by
  field), plus a composed agent task, SQL tests and a README example.
- Fix: live HTTPS requests failed certificate verification on Python builds whose
  OpenSSL CA bundle lacks the Treasury chain's root (uv's standalone Python on macOS);
  requests now verify against the operating system trust store via truststore.

Targets: vgi-python 0.51 · VGI protocol 3.3 · Haybarn 2.0.0rc11 · vgi-lint-check 2.x (unpinned)
