"""CLI for the BizClinik wrapper.

Usage:
    python -m bizclinik <command> <workbook.xlsx> [options]

Commands:
    info         Show company info and KPI summary
    sheets       List sheet names
    list         Dump module records as JSON (--module inventory|suppliers|customers|operating|coa|company)
    export       Export module to CSV/JSON (--module ... --out path)
    kpis         Print KPI summary as JSON
    stock        Print current stock balance per product code
    pnl          Compute P&L from first principles (--from/--to/--after-vat)
    balance      Derive Balance Sheet (--as-of)
    quotation    Generate a Sales Quotation .xlsx from a JSON spec (--spec file.json --out file.xlsx)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from .financials import balance_sheet, profit_and_loss
from .models import CompanyInfo
from .quotation import (
    Quotation,
    QuotationLine,
    QuotationParty,
    write_quotation_xlsx,
)
from .workbook import BizClinikWorkbook


def _default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    return str(o)


def _dump(data) -> None:
    json.dump(data, sys.stdout, indent=2, default=_default, ensure_ascii=False)
    sys.stdout.write("\n")


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d").date()


# ---- handlers --------------------------------------------------------------


def cmd_info(wb: BizClinikWorkbook, _args) -> int:
    _dump({"company": wb.company().to_dict(), "kpis": wb.kpis()})
    return 0


def cmd_kpis(wb: BizClinikWorkbook, _args) -> int:
    _dump(wb.kpis())
    return 0


def cmd_list(wb: BizClinikWorkbook, args) -> int:
    _dump(wb._records_for(args.module))
    return 0


def cmd_export(wb: BizClinikWorkbook, args) -> int:
    if not args.out:
        print("--out is required for export", file=sys.stderr)
        return 2
    out = Path(args.out)
    fmt = args.format or out.suffix.lstrip(".").lower() or "csv"
    path = wb.export_json(args.module, out) if fmt == "json" \
        else wb.export_csv(args.module, out)
    print(str(path))
    return 0


def cmd_stock(wb: BizClinikWorkbook, _args) -> int:
    _dump(wb.stock_balance())
    return 0


def cmd_sheets(wb: BizClinikWorkbook, _args) -> int:
    _dump(wb.sheet_names)
    return 0


def cmd_pnl(wb: BizClinikWorkbook, args) -> int:
    report = profit_and_loss(
        wb,
        period_start=_parse_date(args.date_from),
        period_end=_parse_date(args.date_to),
        use_after_vat=args.after_vat,
    )
    _dump(report.to_dict())
    return 0


def cmd_balance(wb: BizClinikWorkbook, args) -> int:
    report = balance_sheet(wb, as_of=_parse_date(args.as_of))
    _dump(report.to_dict())
    return 0


def cmd_quotation(wb: BizClinikWorkbook, args) -> int:
    if not args.spec or not args.out:
        print("--spec and --out are required for quotation", file=sys.stderr)
        return 2
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    company = wb.company()
    # Allow overriding company fields from spec.
    company_override = spec.get("company") or {}
    for k, v in company_override.items():
        if hasattr(company, k):
            setattr(company, k, v)
    cust = spec.get("customer") or {}
    quote = Quotation(
        company=company,
        customer=QuotationParty(
            name=cust["name"],
            address=cust.get("address"),
            email=cust.get("email"),
            phone=cust.get("phone"),
        ),
        ref_no=spec["ref_no"],
        issue_date=_parse_date(spec.get("issue_date")) or date.today(),
        valid_until=_parse_date(spec.get("valid_until")),
        lines=[
            QuotationLine(
                code=l.get("code"),
                description=l["description"],
                qty=float(l.get("qty") or 0),
                rate=float(l.get("rate") or 0),
                vat_rate=float(l.get("vat_rate") or 0),
            )
            for l in spec.get("lines", [])
        ],
        notes=spec.get("notes"),
        currency=spec.get("currency", "₦"),
    )
    out = write_quotation_xlsx(quote, args.out)
    print(str(out))
    return 0


# ---- parser ----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bizclinik",
                                description="BizClinik accounting workbook wrapper")
    p.add_argument("command",
                   choices=["info", "list", "kpis", "export", "stock", "sheets",
                            "pnl", "balance", "quotation"])
    p.add_argument("workbook", help="Path to the BizClinik .xlsx file")
    p.add_argument("--module", default="customers",
                   help="inventory|suppliers|customers|operating|coa|company")
    p.add_argument("--out", help="Output path")
    p.add_argument("--format", choices=["csv", "json"], help="Export format")
    p.add_argument("--from", dest="date_from", help="P&L period start (YYYY-MM-DD)")
    p.add_argument("--to", dest="date_to", help="P&L period end (YYYY-MM-DD)")
    p.add_argument("--after-vat", action="store_true",
                   help="Use Total After VAT amounts in P&L")
    p.add_argument("--as-of", help="Balance Sheet as-of date (YYYY-MM-DD)")
    p.add_argument("--spec", help="Quotation spec JSON file")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    wb = BizClinikWorkbook(args.workbook, read_only=True)
    handlers = {
        "info": cmd_info,
        "list": cmd_list,
        "kpis": cmd_kpis,
        "export": cmd_export,
        "stock": cmd_stock,
        "sheets": cmd_sheets,
        "pnl": cmd_pnl,
        "balance": cmd_balance,
        "quotation": cmd_quotation,
    }
    return handlers[args.command](wb, args)


if __name__ == "__main__":
    raise SystemExit(main())
