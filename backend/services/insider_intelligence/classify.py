"""Classify parsed ownership rows and decide which may count as a discretionary signal.

Only a voluntary open-market purchase or sale of non-derivative stock can be a signal. Grants and
other acquisitions from the issuer, exercises, tax withholding, gifts, plan trades (Rule 10b5-1
or standing instructions), sales to cover taxes, sales tied to a same-day exercise, and
offering/private transactions never are.
When the evidence is ambiguous the row keeps its category but gets an issue, and any row with an
issue is excluded from signals.

Limits (SEC forms do not carry this information reliably):
- Code P/S means "open market or private". Private deals are only caught when a footnote says so.
- Plan trades are caught from the Rule 10b5-1 checkbox (forms since April 2023) and footnote or
  remarks text. A plan trade disclosed nowhere in the filing cannot be detected.
"""

import re
from collections import defaultdict
from datetime import date
from decimal import Decimal

from backend.services.insider_intelligence.parser import ParsedFiling, Row


# SEC transaction codes (Form 4 general instruction 8).
CODE_DESCRIPTIONS = {
    "P": "Open market or private purchase",
    "S": "Open market or private sale",
    "V": "Transaction voluntarily reported earlier than required",
    "A": "Grant, award or other acquisition from the issuer (Rule 16b-3(d))",
    "D": "Disposition to the issuer (Rule 16b-3(e))",
    "F": "Payment of exercise price or tax liability by delivering or withholding securities",
    "I": "Discretionary transaction under an employee benefit plan (Rule 16b-3(f))",
    "M": "Exercise or conversion of an exempt derivative security",
    "C": "Conversion of derivative security",
    "E": "Expiration of short derivative position",
    "H": "Expiration or cancellation of long derivative position with value received",
    "O": "Exercise of out-of-the-money derivative security",
    "X": "Exercise of in-the-money or at-the-money derivative security",
    "G": "Bona fide gift",
    "L": "Small acquisition (Rule 16a-6)",
    "W": "Acquisition or disposition by will or laws of descent",
    "Z": "Deposit into or withdrawal from voting trust",
    "J": "Other acquisition or disposition (see footnotes)",
    "K": "Transaction in equity swap or similar instrument",
    "U": "Disposition in a change-of-control tender",
}
_CODE_CATEGORY = {
    "A": "acquisition_from_issuer",  # grants and awards, and shares bought from the issuer
    "D": "disposition_to_issuer",
    "F": "tax_withholding",
    "M": "option_exercise",
    "X": "option_exercise",
    "O": "option_exercise",
    "C": "conversion",
    "G": "gift",
    "W": "inheritance",
}
EXERCISE_CODES = frozenset({"M", "X", "O"})

_PLAN = re.compile(r"10b5[\s-]*1", re.IGNORECASE)
# A sentence that names Rule 10b5-1 only to exclude it ("except pursuant to approved 10b5-1
# plans", "was not made pursuant to a 10b5-1 plan") does not say the trade was a plan trade.
_PLAN_NOT_AFFIRMED = re.compile(
    r"\b(?:except|unless|other than)\b"
    r"|\bnot\s+(?:been\s+)?(?:made|effected|executed|entered|sold|purchased)?\s*"
    r"(?:pursuant to|under|in connection with|part of)\b",
    re.IGNORECASE,
)
_INSTRUCTIONS = re.compile(
    r"pursuant to (?:[\w-]+\s+){0,4}instructions|pre-?arranged|pre-?established", re.IGNORECASE
)
_SELL_TO_COVER = re.compile(
    r"sell[\s-]to[\s-]cover"
    r"|\bto (?:cover|satisfy|pay|fund)\b[^.|]{0,100}(?:tax|withholding)"
    r"|withheld[^.|]{0,60}tax|tax[\s-]withholding",
    re.IGNORECASE,
)
_NOT_OPEN_MARKET = re.compile(
    r"public offering|underwrit|private placement|privately[\s-]negotiated"
    r"|private (?:sale|purchase|transaction)|tender offer|repurchase"
    r"|directly from the (?:issuer|company)"
    r"|(?:sold|transferred) (?:back )?to the (?:issuer|company)\b"
    r"|dividend reinvestment|employee stock purchase plan|\bESPP\b|401\(k\)"
    r"|distribution[\s-]in[\s-]kind|pro[\s-]rata",
    re.IGNORECASE,
)


def affirms_10b5_1(text: str) -> bool:
    """True if some sentence states the trade was made under a Rule 10b5-1 plan."""
    return any(
        _PLAN.search(sentence) and not _PLAN_NOT_AFFIRMED.search(sentence)
        for sentence in re.split(r"(?<=[.;|])\s+", text)
    )


def classify_filing(filing: ParsedFiling, filed_date: date) -> None:
    """Set category, plan flags, issues and signal on every row of the filing."""
    trades = [r for r in filing.rows if not r.is_holding and r.code in ("P", "S")]
    any_row_affirms = any(affirms_10b5_1(r.footnotes) for r in trades)
    remarks_affirm = affirms_10b5_1(filing.remarks)
    exercise_days = _exercise_and_sell_days(filing)

    for r in filing.rows:
        if r.is_holding:
            r.category = "holding"
            continue
        if r.transaction_date is None:
            r.issues.append("missing_transaction_date")
        elif r.transaction_date > filed_date:
            r.issues.append("transaction_date_after_filing")
        if r.code in ("P", "S"):
            _set_plan(r, filing.aff10b5one, any_row_affirms, remarks_affirm)
            _classify_trade(r, r.transaction_date in exercise_days)
        elif r.code in CODE_DESCRIPTIONS:
            r.category = _CODE_CATEGORY.get(r.code, "other")
        else:
            r.category = "unknown"
            r.issues.append("unknown_transaction_code")


def _exercise_and_sell_days(filing: ParsedFiling) -> set[date | None]:
    """Days on which the shares sold do not exceed the shares received by exercise."""
    exercised: dict[date | None, Decimal] = defaultdict(Decimal)
    sold: dict[date | None, Decimal] = defaultdict(Decimal)
    for r in filing.rows:
        if r.table == "non_derivative" and not r.is_holding and r.shares:
            if r.code in EXERCISE_CODES and r.acquired_disposed == "A":
                exercised[r.transaction_date] += r.shares
            elif r.code == "S":
                sold[r.transaction_date] += r.shares
    return {day for day, shares in sold.items() if shares <= exercised[day]}


def _classify_trade(r: Row, exercise_and_sell_day: bool) -> None:
    buy = r.code == "P"
    if r.table == "derivative":
        r.category = "derivative_purchase" if buy else "derivative_sale"
    elif r.plan_10b5_1 or r.plan_basis:
        r.category = "planned_purchase" if buy else "planned_sale"
    elif not buy and _SELL_TO_COVER.search(r.transaction_footnotes):
        r.category = "sale_to_cover_taxes"
    elif _NOT_OPEN_MARKET.search(r.transaction_footnotes):
        r.category = "non_open_market_purchase" if buy else "non_open_market_sale"
    elif not buy and exercise_and_sell_day:
        r.category = "sale_linked_to_exercise"
    else:
        r.category = "open_market_purchase" if buy else "open_market_sale"
        _check_trade(r, buy)
        if not r.issues:
            r.signal = "discretionary_buy" if buy else "discretionary_sell"


def _set_plan(r: Row, checkbox: bool | None, any_row_affirms: bool, remarks_affirm: bool) -> None:
    if affirms_10b5_1(r.footnotes):
        r.plan_10b5_1, r.plan_basis = True, "footnote"
    elif remarks_affirm:
        r.plan_10b5_1, r.plan_basis = True, "remarks"
    elif checkbox and not any_row_affirms:
        # The checkbox covers the whole form; with no row singled out, assume every trade.
        r.plan_10b5_1, r.plan_basis = True, "checkbox"
    elif _INSTRUCTIONS.search(r.transaction_footnotes):
        r.plan_basis = "trading_instructions"
    elif checkbox:
        # Box is checked but footnotes single out other rows: cannot tell for this one.
        r.issues.append("plan_scope_ambiguous")


def _check_trade(r: Row, buy: bool) -> None:
    if not r.shares:
        r.issues.append("missing_shares")
    if r.price is None:
        r.issues.append("missing_price")
    elif r.price == 0:
        r.issues.append("zero_price")
    if r.acquired_disposed != ("A" if buy else "D"):
        r.issues.append("code_direction_mismatch")
    if r.equity_swap:
        r.issues.append("equity_swap")
