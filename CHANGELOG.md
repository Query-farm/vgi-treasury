# Changelog

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
