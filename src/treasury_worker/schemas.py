"""Explicit Fiscal Data schemas derived from official API metadata, verified November 2026."""

from __future__ import annotations

from dataclasses import dataclass

import pyarrow as pa

from .meta import column


@dataclass(frozen=True)
class Dataset:
    """A supported endpoint with source units and an explicit typed schema."""

    endpoint: str
    title: str
    amount_units: str
    description: str
    schema: pa.Schema


DATASETS = {
    "debt_to_penny": Dataset(
        endpoint="v2/accounting/od/debt_to_penny",
        title="Federal debt to the penny",
        amount_units="USD",
        description=(
            "Daily debt held by the public, intragovernmental holdings and total public debt; exact API amounts."
        ),
        schema=pa.schema(
            [
                column(
                    "record_date",
                    pa.date32(),
                    "Record Date. Source report/record date, not necessarily the period described by every row.",
                    nullable=False,
                ),
                column(
                    "debt_held_public_amt",
                    pa.decimal128(38, 2),
                    "Debt Held by the Public. Exact source amount; USD; no rescaling.",
                    nullable=True,
                ),
                column(
                    "intragov_hold_amt",
                    pa.decimal128(38, 2),
                    "Intragovernmental Holdings. Exact source amount; USD; no rescaling.",
                    nullable=True,
                ),
                column(
                    "tot_pub_debt_out_amt",
                    pa.decimal128(38, 2),
                    "Total Public Debt Outstanding. Exact source amount; USD; no rescaling.",
                    nullable=True,
                ),
                column("src_line_nbr", pa.int64(), "Source Line Number.", nullable=True),
                column("record_fiscal_year", pa.int64(), "Fiscal Year.", nullable=True),
                column("record_fiscal_quarter", pa.int64(), "Fiscal Quarter Number.", nullable=True),
                column("record_calendar_year", pa.int64(), "Calendar Year.", nullable=True),
                column("record_calendar_quarter", pa.int64(), "Calendar Quarter Number.", nullable=True),
                column("record_calendar_month", pa.int64(), "Calendar Month Number.", nullable=True),
                column("record_calendar_day", pa.int64(), "Calendar Day Number.", nullable=True),
                column(
                    "source_json",
                    pa.string(),
                    "Complete original row preserving source text and any additional fields.",
                ),
                column("amount_units", pa.string(), "Source amount scale for this endpoint; not a conversion factor."),
            ]
        ),
    ),
    "operating_cash_balance": Dataset(
        endpoint="v1/accounting/dts/operating_cash_balance",
        title="Operating cash balance",
        amount_units="USD millions",
        description=(
            "Daily Treasury operating cash balances. Since April 2022 some closing fields are "
            "null; account_type distinguishes opening and closing balance rows."
        ),
        schema=pa.schema(
            [
                column(
                    "record_date",
                    pa.date32(),
                    "Record Date. Source report/record date, not necessarily the period described by every row.",
                    nullable=False,
                ),
                column("account_type", pa.string(), "Type of Account.", nullable=True),
                column(
                    "close_today_bal",
                    pa.decimal128(38, 0),
                    "Closing Balance Today. Exact source amount; USD millions; no rescaling.",
                    nullable=True,
                ),
                column(
                    "open_today_bal",
                    pa.decimal128(38, 0),
                    "Opening Balance Today. Exact source amount; USD millions; no rescaling.",
                    nullable=True,
                ),
                column(
                    "open_month_bal",
                    pa.decimal128(38, 0),
                    "Opening Balance This Month. Exact source amount; USD millions; no rescaling.",
                    nullable=True,
                ),
                column(
                    "open_fiscal_year_bal",
                    pa.decimal128(38, 0),
                    "Opening Balance This Fiscal Year. Exact source amount; USD millions; no rescaling.",
                    nullable=True,
                ),
                column("table_nbr", pa.string(), "Table Number.", nullable=True),
                column("table_nm", pa.string(), "Table Name.", nullable=True),
                column("sub_table_name", pa.string(), "Sub Table Name.", nullable=True),
                column("src_line_nbr", pa.int64(), "Source Line Number.", nullable=True),
                column("record_fiscal_year", pa.int64(), "Fiscal Year.", nullable=True),
                column("record_fiscal_quarter", pa.int64(), "Fiscal Quarter Number.", nullable=True),
                column("record_calendar_year", pa.int64(), "Calendar Year.", nullable=True),
                column("record_calendar_quarter", pa.int64(), "Calendar Quarter Number.", nullable=True),
                column("record_calendar_month", pa.int64(), "Calendar Month Number.", nullable=True),
                column("record_calendar_day", pa.int64(), "Calendar Day Number.", nullable=True),
                column(
                    "source_json",
                    pa.string(),
                    "Complete original row preserving source text and any additional fields.",
                ),
                column("amount_units", pa.string(), "Source amount scale for this endpoint; not a conversion factor."),
            ]
        ),
    ),
    "deposits_withdrawals": Dataset(
        endpoint="v1/accounting/dts/deposits_withdrawals_operating_cash",
        title="Cash deposits and withdrawals",
        amount_units="USD millions",
        description=(
            "Daily Treasury cash deposits and withdrawals, including month-to-date and "
            "fiscal-year-to-date figures. Categories and totals may overlap; filter before "
            "aggregation."
        ),
        schema=pa.schema(
            [
                column(
                    "record_date",
                    pa.date32(),
                    "Record Date. Source report/record date, not necessarily the period described by every row.",
                    nullable=False,
                ),
                column("account_type", pa.string(), "Type of Account.", nullable=True),
                column("transaction_type", pa.string(), "Transaction Type.", nullable=True),
                column("transaction_catg", pa.string(), "Transaction Category.", nullable=True),
                column("transaction_catg_desc", pa.string(), "Transaction Category Description.", nullable=True),
                column(
                    "transaction_today_amt",
                    pa.decimal128(38, 0),
                    "Transactions Today. Exact source amount; USD millions; no rescaling.",
                    nullable=True,
                ),
                column(
                    "transaction_mtd_amt",
                    pa.decimal128(38, 0),
                    "Transactions Month to Date. Exact source amount; USD millions; no rescaling.",
                    nullable=True,
                ),
                column(
                    "transaction_fytd_amt",
                    pa.decimal128(38, 0),
                    "Transactions Fiscal Year to Date. Exact source amount; USD millions; no rescaling.",
                    nullable=True,
                ),
                column("table_nbr", pa.string(), "Table Number.", nullable=True),
                column("table_nm", pa.string(), "Table Name.", nullable=True),
                column("src_line_nbr", pa.int64(), "Source Line Number.", nullable=True),
                column("record_fiscal_year", pa.int64(), "Fiscal Year.", nullable=True),
                column("record_fiscal_quarter", pa.int64(), "Fiscal Quarter Number.", nullable=True),
                column("record_calendar_year", pa.int64(), "Calendar Year.", nullable=True),
                column("record_calendar_quarter", pa.int64(), "Calendar Quarter Number.", nullable=True),
                column("record_calendar_month", pa.int64(), "Calendar Month Number.", nullable=True),
                column("record_calendar_day", pa.int64(), "Calendar Day Number.", nullable=True),
                column(
                    "source_json",
                    pa.string(),
                    "Complete original row preserving source text and any additional fields.",
                ),
                column("amount_units", pa.string(), "Source amount scale for this endpoint; not a conversion factor."),
            ]
        ),
    ),
    "public_debt_transactions": Dataset(
        endpoint="v1/accounting/dts/public_debt_transactions",
        title="Public debt transactions",
        amount_units="USD millions",
        description=(
            "Public debt issues and redemptions by security type in USD millions. "
            "transaction_type distinguishes Issues and Redemptions; security_market distinguishes Marketable and "
            "Nonmarketable. security_type retains source classifications such as Bills, Notes, Bonds and Government "
            "Account Series; inspect distinct values in your date window rather than assuming a fixed enumeration. "
            "transaction_today_amt is daily, transaction_mtd_amt is month-to-date, and transaction_fytd_amt is "
            "fiscal-year-to-date. These are overlapping measures; do not sum them together or sum cumulative values "
            "across dates. For operating cash use operating_cash_balance(); for deposits and withdrawals use "
            "deposits_withdrawals()."
        ),
        schema=pa.schema(
            [
                column(
                    "record_date",
                    pa.date32(),
                    "Record Date. Source report/record date, not necessarily the period described by every row.",
                    nullable=False,
                ),
                column("transaction_type", pa.string(), "Transaction Type.", nullable=True),
                column("security_market", pa.string(), "Security Marketability.", nullable=True),
                column("security_type", pa.string(), "Security Type.", nullable=True),
                column("security_type_desc", pa.string(), "Security Type Description.", nullable=True),
                column(
                    "transaction_today_amt",
                    pa.decimal128(38, 0),
                    "Transactions Today. Exact source amount; USD millions; no rescaling.",
                    nullable=True,
                ),
                column(
                    "transaction_mtd_amt",
                    pa.decimal128(38, 0),
                    "Transactions Month to Date. Exact source amount; USD millions; no rescaling.",
                    nullable=True,
                ),
                column(
                    "transaction_fytd_amt",
                    pa.decimal128(38, 0),
                    "Transactions Fiscal Year to Date. Exact source amount; USD millions; no rescaling.",
                    nullable=True,
                ),
                column("table_nbr", pa.string(), "Table Number.", nullable=True),
                column("table_nm", pa.string(), "Table Name.", nullable=True),
                column("src_line_nbr", pa.int64(), "Source Line Number.", nullable=True),
                column("record_fiscal_year", pa.int64(), "Fiscal Year.", nullable=True),
                column("record_fiscal_quarter", pa.int64(), "Fiscal Quarter Number.", nullable=True),
                column("record_calendar_year", pa.int64(), "Calendar Year.", nullable=True),
                column("record_calendar_quarter", pa.int64(), "Calendar Quarter Number.", nullable=True),
                column("record_calendar_month", pa.int64(), "Calendar Month Number.", nullable=True),
                column("record_calendar_day", pa.int64(), "Calendar Day Number.", nullable=True),
                column(
                    "source_json",
                    pa.string(),
                    "Complete original row preserving source text and any additional fields.",
                ),
                column("amount_units", pa.string(), "Source amount scale for this endpoint; not a conversion factor."),
            ]
        ),
    ),
    "monthly_statement": Dataset(
        endpoint="v1/accounting/mts/mts_table_1",
        title="Monthly Treasury receipts and outlays",
        amount_units="API currency units",
        description=(
            "Monthly Treasury Statement table 1, including headers and subtotals. record_date "
            "identifies the report; classification_desc and record_type_cd identify the "
            "represented period. Raw API amounts are not scaled to the website display."
        ),
        schema=pa.schema(
            [
                column(
                    "record_date",
                    pa.date32(),
                    "Record Date. Source report/record date, not necessarily the period described by every row.",
                    nullable=False,
                ),
                column("parent_id", pa.string(), "Parent ID.", nullable=True),
                column("classification_id", pa.string(), "Classification ID.", nullable=True),
                column("classification_desc", pa.string(), "Classification Description.", nullable=True),
                column(
                    "current_month_gross_rcpt_amt",
                    pa.decimal128(38, 2),
                    "Current Month Gross Receipts Amount. Exact source amount; API currency units; no rescaling.",
                    nullable=True,
                ),
                column(
                    "current_month_gross_outly_amt",
                    pa.decimal128(38, 2),
                    "Current Month Gross Outlay Amount. Exact source amount; API currency units; no rescaling.",
                    nullable=True,
                ),
                column(
                    "current_month_dfct_sur_amt",
                    pa.decimal128(38, 2),
                    "Current Month Deficit Surplus Amount. Exact source amount; API currency units; no rescaling.",
                    nullable=True,
                ),
                column("table_nbr", pa.string(), "Table Number.", nullable=True),
                column("src_line_nbr", pa.int64(), "Source Line Number.", nullable=True),
                column("print_order_nbr", pa.string(), "Print Order Sequence Number.", nullable=True),
                column("line_code_nbr", pa.string(), "Line Code Number.", nullable=True),
                column("data_type_cd", pa.string(), "Data Type Code.", nullable=True),
                column("record_type_cd", pa.string(), "Record Type Code.", nullable=True),
                column("sequence_level_nbr", pa.string(), "Sequence Level Number.", nullable=True),
                column("sequence_number_cd", pa.string(), "Sequence Number Code.", nullable=True),
                column("record_fiscal_year", pa.int64(), "Fiscal Year.", nullable=True),
                column("record_fiscal_quarter", pa.int64(), "Fiscal Quarter Number.", nullable=True),
                column("record_calendar_year", pa.int64(), "Calendar Year.", nullable=True),
                column("record_calendar_quarter", pa.int64(), "Calendar Quarter Number.", nullable=True),
                column("record_calendar_month", pa.int64(), "Calendar Month Number.", nullable=True),
                column("record_calendar_day", pa.int64(), "Calendar Day Number.", nullable=True),
                column(
                    "source_json",
                    pa.string(),
                    "Complete original row preserving source text and any additional fields.",
                ),
                column("amount_units", pa.string(), "Source amount scale for this endpoint; not a conversion factor."),
            ]
        ),
    ),
    "average_interest_rates": Dataset(
        endpoint="v2/accounting/od/avg_interest_rates",
        title="Average interest rates",
        amount_units="percent",
        description=(
            "Monthly average interest rates on outstanding Treasury securities; values are percentages, not fractions."
        ),
        schema=pa.schema(
            [
                column(
                    "record_date",
                    pa.date32(),
                    "Record Date. Source report/record date, not necessarily the period described by every row.",
                    nullable=False,
                ),
                column("security_type_desc", pa.string(), "Security Type Description.", nullable=True),
                column("security_desc", pa.string(), "Security Description.", nullable=True),
                column(
                    "avg_interest_rate_amt",
                    pa.decimal128(38, 6),
                    "Average Interest Rate Amount. Exact source amount; percent; no rescaling.",
                    nullable=True,
                ),
                column("src_line_nbr", pa.int64(), "Source Line Number.", nullable=True),
                column("record_fiscal_year", pa.int64(), "Fiscal Year.", nullable=True),
                column("record_fiscal_quarter", pa.int64(), "Fiscal Quarter Number.", nullable=True),
                column("record_calendar_year", pa.int64(), "Calendar Year.", nullable=True),
                column("record_calendar_quarter", pa.int64(), "Calendar Quarter Number.", nullable=True),
                column("record_calendar_month", pa.int64(), "Calendar Month Number.", nullable=True),
                column("record_calendar_day", pa.int64(), "Calendar Day Number.", nullable=True),
                column(
                    "source_json",
                    pa.string(),
                    "Complete original row preserving source text and any additional fields.",
                ),
                column("amount_units", pa.string(), "Source amount scale for this endpoint; not a conversion factor."),
            ]
        ),
    ),
}
